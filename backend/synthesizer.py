"""
Brifing sentezleyici + guardrail (deterministik).

Araç çıktılarını (WxReport'lar + config) alıp bir `Briefing` üretir:
  • risk faktörleri (kategori, VFR minima, crosswind)
  • data gap'ler (eksik ICAO/METAR, bilinmeyen görüş, TAF penceresi dışı, pist yönü yok)
  • genel etiket: FAVORABLE / MARGINAL / UNFAVORABLE / INSUFFICIENT_DATA (abstain)

Bu katmanda LLM YOKTUR — kararlar araç çıktılarından türetilir. Guardrail
(`validate_no_fabrication`), her sayısal iddianın gerçekten bir araç çıktısına
izlenebilir olduğunu doğrular; LLM tabanlı sentez eklendiğinde uydurmayı yakalar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.models import (
    Briefing, Citation, DataGap, FlightQuery, RiskFactor, WxReport,
)
from backend.tools.config_lookup import AircraftLimits, VfrMinima
from backend.tools.rules import (
    CheckStatus, FlightCategory, crosswind_component,
    evaluate_vfr_minima, exceeds_crosswind_limit,
)

DISCLAIMER = (
    "Bu brifing yalnızca bilgilendirme amaçlıdır (advisory) ve bir uçuş kararı değildir. "
    "Nihai karar sorumlu pilota (PIC) aittir; resmî METAR/TAF/NOTAM ve yayınları teyit edin."
)

_SEVERITY_BY_CATEGORY = {
    "VFR": "info", "MVFR": "caution", "IFR": "warning", "LIFR": "warning",
}
_LABEL_TO_CAT = {c.label: c for c in FlightCategory}


@dataclass
class Station:
    """Sentezleyiciye verilen tek istasyon girdisi (kalkış/varış)."""
    role: str                       # "departure" | "destination"
    icao: str | None
    wx: WxReport | None
    runway_heading: float | None = None


@dataclass
class SynthesisResult:
    briefing: Briefing
    allowed_values: set[float] = field(default_factory=set)   # guardrail izleme kümesi


def _add(values: set[float], *nums) -> None:
    for n in nums:
        if isinstance(n, (int, float)):
            values.add(round(float(n), 1))


def build_briefing(query: FlightQuery,
                   stations: list[Station],
                   aircraft: AircraftLimits,
                   minima: VfrMinima,
                   now: datetime | None = None) -> SynthesisResult:
    now = now or datetime.now(timezone.utc)
    risks: list[RiskFactor] = []
    gaps: list[DataGap] = []
    citations: list[Citation] = []
    allowed: set[float] = set()

    categories: list[FlightCategory] = []
    vfr_fail = False
    xwind_exceeds = False
    insufficient = False

    _add(allowed, aircraft.max_demonstrated_crosswind_kt,
         minima.visibility_min_sm, minima.ceiling_min_ft)

    for st in stations:
        # 1) Eksik ICAO -> kritik data gap
        if not st.icao:
            gaps.append(DataGap(field=f"{st.role}_icao", reason="Havaalanı belirtilmedi"))
            insufficient = True
            continue
        # 2) Hava raporu yok (veri yok veya TAF penceresi dışı) -> kritik data gap
        if st.wx is None:
            gaps.append(DataGap(field=f"{st.role}_wx",
                                reason="METAR/TAF verisi yok veya istenen zamanı kapsamıyor"))
            insufficient = True
            continue

        wx = st.wx
        _add(allowed, wx.visibility_sm, wx.ceiling_ft, wx.wind_dir_deg,
             wx.wind_speed_kt, wx.gust_kt)

        # 3) Kategori
        if wx.category is None:
            gaps.append(DataGap(field=f"{st.role}_category",
                                reason="Görüş verisi yok, kategori hesaplanamadı"))
            insufficient = True
        else:
            cat = _LABEL_TO_CAT[wx.category]
            categories.append(cat)
            risks.append(RiskFactor(
                code=f"WX_CATEGORY_{st.role.upper()}",
                severity=_SEVERITY_BY_CATEGORY[wx.category],
                message=f"{st.icao} uçuş kategorisi: {wx.category}",
                value=wx.category,
                source_tool="classify_flight_category",
            ))

        # 4) VFR minima (yalnızca VFR pilot)
        if query.pilot_rule == "VFR":
            checks = evaluate_vfr_minima(
                wx.visibility_sm, wx.ceiling_ft,
                minima.visibility_min_sm, minima.ceiling_min_ft)
            for c in checks:
                if c.status is CheckStatus.FAIL:
                    vfr_fail = True
                    risks.append(RiskFactor(
                        code=f"VFR_MINIMA_FAIL_{st.role.upper()}_{c.name.upper()}",
                        severity="warning",
                        message=f"{st.icao} {c.name}={c.actual} < gerekli {c.required} (VFR minima)",
                        value=c.actual,
                        source_tool="evaluate_vfr_minima",
                        citation=Citation(source=f"{minima.jurisdiction} VFR minima (config)"),
                    ))
                elif c.status is CheckStatus.UNKNOWN:
                    gaps.append(DataGap(field=f"{st.role}_{c.name}",
                                        reason="Minima kontrolü için veri eksik"))

        # 5) Crosswind (pist yönü + rüzgâr gerekli)
        if st.runway_heading is None:
            gaps.append(DataGap(field=f"{st.role}_runway_heading",
                                reason="Pist yönü bilinmiyor, crosswind hesaplanamadı"))
        elif wx.wind_dir_deg is None or wx.wind_speed_kt is None:
            gaps.append(DataGap(field=f"{st.role}_wind",
                                reason="Rüzgâr yönü/hızı yok (değişken?), crosswind hesaplanamadı"))
        else:
            w = crosswind_component(st.runway_heading, wx.wind_dir_deg, wx.wind_speed_kt)
            _add(allowed, w.crosswind_kt, w.headwind_kt, w.angle_deg)
            exceeds = exceeds_crosswind_limit(w.crosswind_kt, aircraft.max_demonstrated_crosswind_kt)
            xwind_exceeds = xwind_exceeds or exceeds
            risks.append(RiskFactor(
                code=f"CROSSWIND_{st.role.upper()}",
                severity="warning" if exceeds else "info",
                message=(f"{st.icao} yan rüzgâr {w.crosswind_kt} kt"
                         + (f" — POH limiti {aircraft.max_demonstrated_crosswind_kt} kt AŞILDI"
                            if exceeds else "")),
                value=w.crosswind_kt,
                source_tool="crosswind_component",
                citation=Citation(source=f"{aircraft.type} POH (config)") if exceeds else None,
            ))

    overall = _compute_overall(query, categories, vfr_fail, xwind_exceeds, insufficient)

    briefing = Briefing(
        query=query,
        generated_at=now,
        overall=overall,
        weather=[st.wx for st in stations if st.wx is not None],
        risk_factors=risks,
        data_gaps=gaps,
        citations=citations,
        disclaimer=DISCLAIMER,
    )
    return SynthesisResult(briefing=briefing, allowed_values=allowed)


def _compute_overall(query: FlightQuery,
                     categories: list[FlightCategory],
                     vfr_fail: bool,
                     xwind_exceeds: bool,
                     insufficient: bool) -> str:
    if insufficient or not categories:
        return "INSUFFICIENT_DATA"
    worst = max(categories)

    if query.pilot_rule == "VFR":
        if worst >= FlightCategory.IFR or vfr_fail or xwind_exceeds:
            return "UNFAVORABLE"
        if worst == FlightCategory.MVFR:
            return "MARGINAL"
        return "FAVORABLE"

    # IFR pilot: minima farklı; Faz 1'de sadeleştirilmiş
    if worst == FlightCategory.LIFR or xwind_exceeds:
        return "UNFAVORABLE"
    if worst == FlightCategory.IFR:
        return "MARGINAL"
    return "FAVORABLE"


# ----------------------------------------------------------------------------
# Guardrail: sayı-izlenebilirliği (LLM sentezi eklendiğinde uydurmayı yakalar)
# ----------------------------------------------------------------------------
def validate_no_fabrication(briefing: Briefing,
                            allowed_values: set[float],
                            tol: float = 0.15) -> list[RiskFactor]:
    """Her sayısal RiskFactor.value'nun bir araç çıktısına izlenebilir olduğunu doğrular.

    İzlenemeyen (uydurulmuş) sayısal değer içeren faktörleri döndürür. Boş liste = temiz.
    """
    offenders: list[RiskFactor] = []
    for rf in briefing.risk_factors:
        v = rf.value
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if not any(abs(float(v) - a) <= tol for a in allowed_values):
                offenders.append(rf)
    return offenders
