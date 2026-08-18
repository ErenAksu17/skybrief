import { useState, type FormEvent, type ReactNode } from "react"
import {
  Plane, PlaneTakeoff, PlaneLanding, Wind, Gauge, Navigation, Search,
  Compass, CheckCircle2, XCircle, AlertTriangle, HelpCircle, Clock, ArrowUpRight,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"

// ---------- Tipler (backend Briefing sözleşmesi) ----------
type Category = "VFR" | "MVFR" | "IFR" | "LIFR"
type Overall = "FAVORABLE" | "MARGINAL" | "UNFAVORABLE" | "INSUFFICIENT_DATA"

interface WxReport {
  station: string; kind: string; raw: string
  visibility_sm: number | null; ceiling_ft: number | null
  wind_dir_deg: number | null; wind_speed_kt: number | null; gust_kt: number | null
  category: Category | null
}
interface RiskFactor {
  code: string; severity: "info" | "caution" | "warning"; message: string
  value: number | string | null; citation: { source: string } | null
}
interface DataGap { field: string; reason: string }
interface Briefing {
  query: { departure_icao: string | null; destination_icao: string | null; aircraft_type: string; pilot_rule: string }
  overall: Overall; weather: WxReport[]; risk_factors: RiskFactor[]
  data_gaps: DataGap[]; disclaimer: string
}

// ---------- Sabitler / yardımcılar ----------
const VERDICT: Record<Overall, { tr: string; grad: string; ring: string; icon: typeof CheckCircle2 }> = {
  FAVORABLE:        { tr: "UYGUN",        grad: "from-emerald-500/20 to-emerald-500/5", ring: "border-emerald-500/50 text-emerald-300", icon: CheckCircle2 },
  MARGINAL:         { tr: "SINIRDA",      grad: "from-amber-500/20 to-amber-500/5",     ring: "border-amber-500/50 text-amber-300",   icon: AlertTriangle },
  UNFAVORABLE:      { tr: "UYGUN DEĞİL",  grad: "from-rose-500/20 to-rose-500/5",       ring: "border-rose-500/50 text-rose-300",     icon: XCircle },
  INSUFFICIENT_DATA:{ tr: "YETERSİZ VERİ",grad: "from-slate-500/20 to-slate-500/5",     ring: "border-slate-500/50 text-slate-300",   icon: HelpCircle },
}

const CAT_STYLE: Record<Category, string> = {
  VFR:  "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  MVFR: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  IFR:  "bg-amber-500/15 text-amber-300 border-amber-500/30",
  LIFR: "bg-rose-500/15 text-rose-300 border-rose-500/30",
}
const SEV_DOT: Record<RiskFactor["severity"], string> = {
  info: "bg-emerald-400", caution: "bg-amber-400", warning: "bg-rose-400",
}

const API_BASE = ""

async function getBrief(body: Record<string, unknown>): Promise<Briefing> {
  const res = await fetch(`${API_BASE}/api/brief`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  })
  if (!res.ok) {
    const e = await res.json().catch(() => ({}))
    throw new Error((e as { detail?: string }).detail || `Sunucu hatası (${res.status})`)
  }
  return res.json()
}

// ---------- Alt bileşenler ----------
function StationCard({ wx, role }: { wx: WxReport; role: "dep" | "dst" }) {
  const cat = wx.category ?? "—"
  const Icon = role === "dep" ? PlaneTakeoff : PlaneLanding
  const wind = wx.wind_dir_deg != null
    ? `${wx.wind_dir_deg}° / ${wx.wind_speed_kt ?? "—"} kt${wx.gust_kt ? " G" + wx.gust_kt : ""}`
    : wx.wind_speed_kt != null ? `VRB / ${wx.wind_speed_kt} kt` : "—"
  return (
    <Card className="border-white/10 bg-white/[0.03] backdrop-blur">
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Icon className="size-4 text-sky-400" />
            <span className="font-mono text-lg font-bold tracking-wide">{wx.station}</span>
          </div>
          <span className={`rounded-md border px-2 py-0.5 text-xs font-bold ${wx.category ? CAT_STYLE[wx.category] : "text-slate-400"}`}>{cat}</span>
        </div>
        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
          <Metric label="Görüş" value={wx.visibility_sm != null ? `${wx.visibility_sm}` : "—"} unit="sm" />
          <Metric label="Tavan" value={wx.ceiling_ft != null ? `${wx.ceiling_ft}` : "yok"} unit={wx.ceiling_ft != null ? "ft" : ""} />
          <Metric label="Rüzgâr" value={wind} unit="" />
        </div>
        {wx.raw && <p className="mt-3 rounded-md bg-black/30 p-2 font-mono text-[11px] leading-relaxed text-slate-400">{wx.raw}</p>}
      </CardContent>
    </Card>
  )
}

function Metric({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div className="rounded-lg bg-white/[0.03] px-1 py-2">
      <div className="text-sm font-semibold tabular-nums">{value}<span className="ml-0.5 text-[10px] font-normal text-slate-500">{unit}</span></div>
      <div className="mt-0.5 text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
    </div>
  )
}

// ---------- Ana bileşen ----------
export default function App() {
  const [dep, setDep] = useState("LTAC")
  const [dst, setDst] = useState("LTAI")
  const [aircraft, setAircraft] = useState("C172")
  const [rule, setRule] = useState("VFR")
  const [juris, setJuris] = useState("TR")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [brief, setBrief] = useState<Briefing | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setLoading(true); setError(null)
    try {
      const b = await getBrief({
        departure_icao: dep.toUpperCase() || null,
        destination_icao: dst.toUpperCase() || null,
        aircraft_type: aircraft, pilot_rule: rule, jurisdiction: juris,
      })
      setBrief(b)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bilinmeyen hata")
      setBrief(null)
    } finally { setLoading(false) }
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-slate-950 text-slate-100">
      {/* Arka plan parıltıları */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -left-40 -top-40 size-96 rounded-full bg-sky-500/20 blur-[120px]" />
        <div className="absolute right-0 top-1/3 size-96 rounded-full bg-indigo-600/20 blur-[120px]" />
        <div className="absolute bottom-0 left-1/3 size-96 rounded-full bg-cyan-500/10 blur-[120px]" />
      </div>

      {/* Header */}
      <header className="relative border-b border-white/10 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-xl bg-gradient-to-br from-sky-400 to-indigo-500 shadow-lg shadow-sky-500/30">
              <Plane className="size-5 text-white" />
            </div>
            <div>
              <h1 className="bg-gradient-to-r from-sky-300 to-indigo-300 bg-clip-text text-xl font-extrabold text-transparent">SkyBrief</h1>
              <p className="text-xs text-slate-400">Deterministik Uçuş Brifingi</p>
            </div>
          </div>
          <span className="rounded-full border border-amber-500/40 px-3 py-1 text-[11px] font-bold tracking-wide text-amber-300">
            ADVISORY · PIC KARAR VERİR
          </span>
        </div>
      </header>

      <main className="relative mx-auto grid max-w-6xl gap-6 px-6 py-8 lg:grid-cols-[380px_1fr]">
        {/* Form */}
        <Card className="h-fit border-white/10 bg-white/[0.04] backdrop-blur-xl">
          <CardContent className="p-6">
            <h2 className="mb-5 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-slate-300">
              <Compass className="size-4 text-sky-400" /> Uçuş Sorgusu
            </h2>
            <form onSubmit={submit} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Kalkış (ICAO)" icon={<PlaneTakeoff className="size-3.5" />}>
                  <Input value={dep} onChange={(e) => setDep(e.target.value)} maxLength={4}
                    placeholder="LTAC" required className="font-mono uppercase tracking-widest" />
                </Field>
                <Field label="Varış (ICAO)" icon={<PlaneLanding className="size-3.5" />}>
                  <Input value={dst} onChange={(e) => setDst(e.target.value)} maxLength={4}
                    placeholder="LTAI" required className="font-mono uppercase tracking-widest" />
                </Field>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Uçak" icon={<Plane className="size-3.5" />}>
                  <Select value={aircraft} onValueChange={(v) => { if (v) setAircraft(v) }}>
                    <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="C172">Cessna 172</SelectItem></SelectContent>
                  </Select>
                </Field>
                <Field label="Kural" icon={<Navigation className="size-3.5" />}>
                  <Select value={rule} onValueChange={(v) => { if (v) setRule(v) }}>
                    <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="VFR">VFR</SelectItem>
                      <SelectItem value="IFR">IFR</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
              </div>
              <Field label="Jurisdiction" icon={<Gauge className="size-3.5" />}>
                <Select value={juris} onValueChange={(v) => { if (v) setJuris(v) }}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="TR">TR (SERA)</SelectItem>
                    <SelectItem value="FAA">FAA</SelectItem>
                    <SelectItem value="EASA">EASA</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <Button type="submit" disabled={loading}
                className="w-full bg-gradient-to-r from-sky-500 to-indigo-500 font-semibold text-white shadow-lg shadow-sky-500/25 hover:from-sky-400 hover:to-indigo-400">
                {loading ? "Alınıyor…" : <><Search className="size-4" /> Brifing Al</>}
              </Button>
              <p className="text-[11px] text-slate-500">Örnek: LTAC → LTAI · veri: aviationweather.gov (METAR/TAF)</p>
            </form>
          </CardContent>
        </Card>

        {/* Sonuç */}
        <div className="min-h-[320px]">
          {!brief && !error && (
            <div className="flex h-full min-h-[320px] flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 text-center">
              <Compass className="mb-3 size-12 text-slate-600" />
              <p className="text-slate-400">Bir uçuş sorgusu gönderin.<br />Sonuç burada, kaynak-atıflı ve dürüst biçimde görünecek.</p>
            </div>
          )}

          {error && (
            <div className="flex items-center gap-3 rounded-2xl border border-rose-500/40 bg-rose-500/10 p-5 text-rose-200">
              <AlertTriangle className="size-5 shrink-0" /> <span>{error}</span>
            </div>
          )}

          {brief && <Result brief={brief} />}
        </div>
      </main>

      <footer className="relative mx-auto max-w-6xl px-6 pb-8 text-center text-xs text-slate-600">
        SkyBrief · deterministik motor · veri: NOAA/NWS aviationweather.gov · advisory-only
      </footer>
    </div>
  )
}

function Field({ label, icon, children }: { label: string; icon: ReactNode; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="flex items-center gap-1.5 text-xs text-slate-400">{icon}{label}</Label>
      {children}
    </div>
  )
}

function Result({ brief }: { brief: Briefing }) {
  const v = VERDICT[brief.overall]
  const VIcon = v.icon
  const q = brief.query
  return (
    <div className="space-y-4">
      {/* Verdict */}
      <div className={`flex items-center justify-between rounded-2xl border bg-gradient-to-r px-6 py-5 ${v.grad} ${v.ring}`}>
        <div className="flex items-center gap-3">
          <VIcon className="size-8" />
          <span className="text-2xl font-extrabold tracking-tight">{v.tr}</span>
        </div>
        <span className="font-mono text-sm opacity-80">{q.departure_icao ?? "?"} → {q.destination_icao ?? "?"} · {q.aircraft_type} · {q.pilot_rule}</span>
      </div>

      {/* İstasyonlar */}
      {brief.weather.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {brief.weather.map((wx, i) => <StationCard key={wx.station + i} wx={wx} role={i === 0 ? "dep" : "dst"} />)}
        </div>
      )}

      {/* Risk faktörleri */}
      {brief.risk_factors.length > 0 && (
        <Card className="border-white/10 bg-white/[0.03]">
          <CardContent className="p-5">
            <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              <Wind className="size-3.5" /> Risk Faktörleri
            </h3>
            <div className="space-y-1">
              {brief.risk_factors.map((rf, i) => (
                <div key={rf.code + i}>
                  {i > 0 && <Separator className="bg-white/5" />}
                  <div className="flex items-start gap-3 py-2 text-sm">
                    <span className={`mt-1.5 size-2 shrink-0 rounded-full ${SEV_DOT[rf.severity]}`} />
                    <span className="flex-1">{rf.message}
                      {rf.citation && <span className="ml-1 inline-flex items-center gap-0.5 text-xs text-sky-400"><ArrowUpRight className="size-3" />{rf.citation.source}</span>}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Veri boşlukları */}
      {brief.data_gaps.length > 0 && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/[0.06] p-4">
          <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-amber-300">
            <Clock className="size-3.5" /> Veri Boşlukları (dürüstlük)
          </h3>
          <ul className="space-y-1 text-xs text-amber-200/80">
            {brief.data_gaps.map((g, i) => (
              <li key={g.field + i}><span className="font-mono font-semibold text-amber-200">{g.field}</span> — {g.reason}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="px-1 text-[11px] leading-relaxed text-slate-500">{brief.disclaimer}</p>
    </div>
  )
}
