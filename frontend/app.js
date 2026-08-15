/* SkyBrief frontend — /api/brief'e sorgu gönderir, brifingi gösterir. */

const API_BASE = "";   // backend frontend'i servis ediyor -> aynı origin

const VERDICT_TR = {
  FAVORABLE: "UYGUN",
  MARGINAL: "SINIRDA",
  UNFAVORABLE: "UYGUN DEĞİL",
  INSUFFICIENT_DATA: "YETERSİZ VERİ",
};

const form = document.getElementById("brief-form");
const btn = document.getElementById("submit-btn");
const placeholder = document.getElementById("placeholder");
const result = document.getElementById("result");

function val(id) {
  const v = document.getElementById(id).value.trim();
  return v === "" ? null : v;
}

function buildBody() {
  const body = {
    departure_icao: (val("dep") || "").toUpperCase() || null,
    destination_icao: (val("dst") || "").toUpperCase() || null,
    aircraft_type: val("aircraft"),
    pilot_rule: val("rule"),
    jurisdiction: val("juris"),
  };
  const t = val("time");
  if (t) body.departure_time = new Date(t).toISOString();
  const dr = val("dep-rwy"), sr = val("dst-rwy");
  if (dr !== null) body.departure_runway_heading = Number(dr);
  if (sr !== null) body.destination_runway_heading = Number(sr);
  return body;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  btn.disabled = true; btn.textContent = "Alınıyor…";
  try {
    const res = await fetch(`${API_BASE}/api/brief`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildBody()),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showError(err.detail || `Sunucu hatası (${res.status})`);
      return;
    }
    render(await res.json());
  } catch (err) {
    showError("Bağlantı hatası — backend çalışıyor mu?");
    console.error(err);
  } finally {
    btn.disabled = false; btn.textContent = "Brifing Al";
  }
});

function showError(msg) {
  placeholder.classList.add("hidden");
  result.classList.remove("hidden");
  result.innerHTML = `<div class="error">⚠ ${msg}</div>`;
}

const fmt = (v, u = "") => (v == null ? "—" : v + u);

function render(b) {
  placeholder.classList.add("hidden");
  result.classList.remove("hidden");

  const route = `${b.query.departure_icao ?? "?"} → ${b.query.destination_icao ?? "?"} · ${b.query.aircraft_type} · ${b.query.pilot_rule}`;

  const stations = (b.weather || []).map(stationCard).join("");

  const risks = (b.risk_factors || []).map(rf => `
    <div class="risk sev-${rf.severity}">
      <span class="dot"></span>
      <div>${rf.message}${rf.citation ? ` <span class="cite">[${rf.citation.source}]</span>` : ""}</div>
    </div>`).join("");

  const gaps = (b.data_gaps || []).map(g =>
    `<li><b>${g.field}</b> — ${g.reason}</li>`).join("");

  result.innerHTML = `
    <div class="verdict v-${b.overall}">
      <span class="v-label">${VERDICT_TR[b.overall] || b.overall}</span>
      <span class="v-route">${route}</span>
    </div>
    ${stations ? `<div class="stations">${stations}</div>` : ""}
    ${risks ? `<div class="section-title">Risk faktörleri</div>${risks}` : ""}
    ${gaps ? `<div class="section-title">Veri boşlukları (dürüstlük)</div><ul class="gaps">${gaps}</ul>` : ""}
    <div class="disclaimer">${b.disclaimer}</div>`;
}

function stationCard(wx) {
  const cat = wx.category || "—";
  const wind = wx.wind_dir_deg != null
    ? `${wx.wind_dir_deg}° @ ${fmt(wx.wind_speed_kt)} kt${wx.gust_kt ? " G" + wx.gust_kt : ""}`
    : (wx.wind_speed_kt != null ? `VRB @ ${wx.wind_speed_kt} kt` : "—");
  return `
    <div class="station">
      <div class="st-head">
        <span class="icao">${wx.station}</span>
        <span class="cat cat-${cat}">${cat}</span>
      </div>
      <div class="st-row"><span>Görüş</span><span>${fmt(wx.visibility_sm, " sm")}</span></div>
      <div class="st-row"><span>Tavan</span><span>${wx.ceiling_ft != null ? wx.ceiling_ft + " ft" : "yok"}</span></div>
      <div class="st-row"><span>Rüzgâr</span><span>${wind}</span></div>
      <div class="st-row"><span>Tip</span><span>${wx.kind}</span></div>
      ${wx.raw ? `<div class="st-raw mono">${wx.raw}</div>` : ""}
    </div>`;
}
