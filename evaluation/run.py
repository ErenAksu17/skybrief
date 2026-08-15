"""
SkyBrief değerlendirme (eval) harness'ı.

data/eval/questions.jsonl içindeki sabit hava senaryolarını deterministik pipeline'dan
geçirir ve beklenen sonuçlarla karşılaştırır. Canlı METAR KULLANMAZ (tekrar üretilebilirlik).

Ölçülen metrikler:
  • overall doğruluğu        — genel etiket beklenenle eşleşiyor mu
  • abstain precision/recall — INSUFFICIENT_DATA doğru zamanlarda mı üretiliyor
  • fabrication sayısı       — guardrail'i geçemeyen (izlenemeyen) sayısal iddia (hedef 0)

Çalıştırma:  python -m evaluation.run
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from backend.models import FlightQuery, WxReport
from backend.synthesizer import Station, build_briefing, validate_no_fabrication
from backend.tools.config_lookup import load_aircraft, load_vfr_minima
from backend.tools.rules import classify_flight_category

QUESTIONS = Path(__file__).resolve().parent.parent / "data" / "eval" / "questions.jsonl"
_JURISDICTION_FILE = {"TR": "TR", "EASA": "TR", "FAA": "FAA"}
_FIXED_NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


def _wx_from_fields(icao: str | None, f: dict | None) -> WxReport | None:
    """Sabit hava alanlarından WxReport üretir; kategoriyi rules engine ile hesaplar
    (kategori elle verilmez -> sınıflandırma yolu da test edilir)."""
    if icao is None or f is None:
        return None
    cat = classify_flight_category(ceiling_ft=f.get("ceiling_ft"),
                                   visibility_sm=f.get("visibility_sm"))
    return WxReport(
        station=icao, kind="METAR",
        visibility_sm=f.get("visibility_sm"), ceiling_ft=f.get("ceiling_ft"),
        wind_dir_deg=f.get("wind_dir_deg"), wind_speed_kt=f.get("wind_speed_kt"),
        gust_kt=f.get("gust_kt"),
        category=cat.category.label if cat.category is not None else None,
    )


@dataclass
class CaseResult:
    id: str
    expected: str
    got: str
    passed: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class EvalReport:
    cases: list[CaseResult]
    fabrication_total: int

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def overall_accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def abstain_metrics(self) -> tuple[float, float]:
        """(precision, recall) — INSUFFICIENT_DATA tahmini için."""
        A = "INSUFFICIENT_DATA"
        tp = sum(1 for c in self.cases if c.expected == A and c.got == A)
        fp = sum(1 for c in self.cases if c.expected != A and c.got == A)
        fn = sum(1 for c in self.cases if c.expected == A and c.got != A)
        prec = tp / (tp + fp) if (tp + fp) else 1.0
        rec = tp / (tp + fn) if (tp + fn) else 1.0
        return prec, rec


def run_eval(path: Path = QUESTIONS) -> EvalReport:
    cases: list[CaseResult] = []
    fabrication_total = 0

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        case = json.loads(line)
        q = FlightQuery(**case["query"])
        wx = case.get("wx", {})
        rwy = case.get("runways", {})
        stations = [
            Station("departure", q.departure_icao,
                    _wx_from_fields(q.departure_icao, wx.get("departure")),
                    rwy.get("departure")),
            Station("destination", q.destination_icao,
                    _wx_from_fields(q.destination_icao, wx.get("destination")),
                    rwy.get("destination")),
        ]
        aircraft = load_aircraft(q.aircraft_type)
        minima = load_vfr_minima(_JURISDICTION_FILE[q.jurisdiction], "G", "day")
        res = build_briefing(q, stations, aircraft, minima, now=_FIXED_NOW)
        b = res.briefing

        reasons: list[str] = []
        exp = case["expect"]
        if b.overall != exp["overall"]:
            reasons.append(f"overall: beklenen {exp['overall']}, gelen {b.overall}")

        gaps = {g.field for g in b.data_gaps}
        for g in case.get("must_gaps", []):
            if g not in gaps:
                reasons.append(f"eksik data gap: {g}")

        codes = {rf.code for rf in b.risk_factors}
        for r in case.get("must_risk", []):
            if r not in codes:
                reasons.append(f"eksik risk faktoru: {r}")

        fab = validate_no_fabrication(b, res.allowed_values)
        if fab:
            fabrication_total += len(fab)
            reasons.append(f"guardrail ihlali: {[rf.code for rf in fab]}")

        cases.append(CaseResult(case["id"], exp["overall"], b.overall,
                                passed=not reasons, reasons=reasons))

    return EvalReport(cases=cases, fabrication_total=fabrication_total)


def main() -> int:
    report = run_eval()
    print("=" * 62)
    print("SkyBrief EVAL — deterministik brifing pipeline")
    print("=" * 62)
    for c in report.cases:
        mark = "PASS" if c.passed else "FAIL"
        print(f"  [{mark}] {c.id}: {c.expected:17} -> {c.got}")
        for r in c.reasons:
            print(f"         ! {r}")
    prec, rec = report.abstain_metrics()
    print("-" * 62)
    print(f"  Toplam           : {report.passed}/{report.total} gecti "
          f"({report.overall_accuracy*100:.0f}%)")
    print(f"  Abstain precision: {prec*100:.0f}%   recall: {rec*100:.0f}%")
    print(f"  Fabrication      : {report.fabrication_total} (hedef 0)")
    print("=" * 62)
    return 0 if (report.passed == report.total and report.fabrication_total == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
