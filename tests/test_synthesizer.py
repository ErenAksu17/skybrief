"""
Sentezleyici + guardrail testleri (deterministik, LLM'siz).

5 karar senaryosunu (FAVORABLE/MARGINAL/UNFAVORABLE/INSUFFICIENT) ve guardrail'in
uydurma sayıyı yakalamasını kanıtlar.
"""

from datetime import datetime, timezone

from backend.models import FlightQuery, RiskFactor, WxReport
from backend.synthesizer import (
    DISCLAIMER, Station, build_briefing, validate_no_fabrication,
)
from backend.tools.config_lookup import load_aircraft, load_vfr_minima

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
AC = load_aircraft("C172")
MINIMA = load_vfr_minima("TR", "G", "day")   # vis_min 3.1 sm, ceiling_min 1000 ft


def make_wx(icao, vis, ceiling, wdir, wspd, category):
    return WxReport(station=icao, kind="METAR", visibility_sm=vis, ceiling_ft=ceiling,
                    wind_dir_deg=wdir, wind_speed_kt=wspd, category=category)


def brief(stations, pilot="VFR"):
    q = FlightQuery(departure_icao="LTBA", destination_icao="LTAC",
                    aircraft_type="C172", pilot_rule=pilot, jurisdiction="TR")
    return build_briefing(q, stations, AC, MINIMA, now=NOW)


class TestOverall:
    def test_favorable(self):
        # İki istasyon da VFR, iyi rüzgâr (pistle hizalı) -> FAVORABLE
        st = [
            Station("departure", "LTBA", make_wx("LTBA", 10, 5000, 240, 10, "VFR"), runway_heading=240),
            Station("destination", "LTAC", make_wx("LTAC", 10, 4000, 20, 8, "VFR"), runway_heading=30),
        ]
        r = brief(st)
        assert r.briefing.overall == "FAVORABLE"
        assert r.briefing.disclaimer == DISCLAIMER
        assert validate_no_fabrication(r.briefing, r.allowed_values) == []

    def test_marginal_on_mvfr(self):
        st = [Station("departure", "LTBA", make_wx("LTBA", 4, 5000, 240, 10, "MVFR"), runway_heading=240)]
        r = brief(st)
        assert r.briefing.overall == "MARGINAL"

    def test_unfavorable_on_ifr_and_minima(self):
        # Tavan 800 -> IFR kategori + tavan minima (>=1000) FAIL
        st = [Station("departure", "LTBA", make_wx("LTBA", 10, 800, 240, 10, "IFR"), runway_heading=240)]
        r = brief(st)
        assert r.briefing.overall == "UNFAVORABLE"
        codes = {rf.code for rf in r.briefing.risk_factors}
        assert any("VFR_MINIMA_FAIL" in c for c in codes)

    def test_unfavorable_on_crosswind(self):
        # Hava VFR ama yan rüzgâr 20 kt > 15 kt POH limiti
        st = [Station("departure", "LTBA", make_wx("LTBA", 10, 5000, 330, 20, "VFR"), runway_heading=240)]
        r = brief(st)
        assert r.briefing.overall == "UNFAVORABLE"
        xw = next(rf for rf in r.briefing.risk_factors if rf.code.startswith("CROSSWIND"))
        assert xw.value == 20.0 and xw.severity == "warning"
        assert validate_no_fabrication(r.briefing, r.allowed_values) == []

    def test_insufficient_on_missing_wx(self):
        st = [
            Station("departure", "LTBA", make_wx("LTBA", 10, 5000, 240, 10, "VFR"), runway_heading=240),
            Station("destination", "LTAC", None),   # TAF penceresi dışı / veri yok
        ]
        r = brief(st)
        assert r.briefing.overall == "INSUFFICIENT_DATA"
        assert any(g.field == "destination_wx" for g in r.briefing.data_gaps)

    def test_insufficient_on_unknown_category(self):
        # Görüş None -> kategori None -> abstain
        st = [Station("departure", "LTBA", make_wx("LTBA", None, 5000, 240, 10, None), runway_heading=240)]
        r = brief(st)
        assert r.briefing.overall == "INSUFFICIENT_DATA"
        assert any("category" in g.field for g in r.briefing.data_gaps)


class TestDataGaps:
    def test_missing_runway_heading_is_gap_not_fatal(self):
        # Pist yönü yok -> crosswind hesaplanmaz ama uçuş INSUFFICIENT olmaz
        st = [Station("departure", "LTBA", make_wx("LTBA", 10, 5000, 240, 10, "VFR"), runway_heading=None)]
        r = brief(st)
        assert r.briefing.overall == "FAVORABLE"
        assert any(g.field == "departure_runway_heading" for g in r.briefing.data_gaps)

    def test_variable_wind_is_gap(self):
        st = [Station("departure", "LTBA", make_wx("LTBA", 10, 5000, None, None, "VFR"), runway_heading=240)]
        r = brief(st)
        assert any(g.field == "departure_wind" for g in r.briefing.data_gaps)


class TestGuardrail:
    def test_catches_fabricated_number(self):
        st = [Station("departure", "LTBA", make_wx("LTBA", 10, 5000, 240, 10, "VFR"), runway_heading=240)]
        r = brief(st)
        # LLM uydurmuş gibi izlenemeyen bir sayı enjekte et
        r.briefing.risk_factors.append(RiskFactor(
            code="FAKE", severity="warning", message="uydurma", value=987.0,
            source_tool="hallucination"))
        offenders = validate_no_fabrication(r.briefing, r.allowed_values)
        assert len(offenders) == 1 and offenders[0].code == "FAKE"

    def test_string_values_not_flagged(self):
        # Kategori gibi metin değerler guardrail'i tetiklemez
        st = [Station("departure", "LTBA", make_wx("LTBA", 10, 5000, 240, 10, "VFR"), runway_heading=240)]
        r = brief(st)
        assert validate_no_fabrication(r.briefing, r.allowed_values) == []
