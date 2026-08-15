"""
Deterministik rules engine birim testleri.

Bu testler SkyBrief'in güvenlik çekirdeğini kanıtlar: LLM olmadan, tekrar üretilebilir.
"""

import math

import pytest

from backend.tools.rules import (
    FlightCategory,
    CheckStatus,
    classify_flight_category,
    crosswind_component,
    exceeds_crosswind_limit,
    evaluate_vfr_minima,
)
from backend.tools.config_lookup import load_aircraft, load_vfr_minima


# ----------------------------------------------------------------------------
# Uçuş kategorisi
# ----------------------------------------------------------------------------
class TestFlightCategory:
    def test_clear_vfr(self):
        r = classify_flight_category(ceiling_ft=5000, visibility_sm=10)
        assert r.category is FlightCategory.VFR

    def test_no_ceiling_is_unlimited(self):
        # Tavan raporlanmamış (clear) + iyi görüş -> VFR
        r = classify_flight_category(ceiling_ft=None, visibility_sm=10)
        assert r.category is FlightCategory.VFR

    def test_mvfr_by_visibility(self):
        r = classify_flight_category(ceiling_ft=5000, visibility_sm=4)
        assert r.category is FlightCategory.MVFR
        assert r.driven_by == "visibility"

    def test_ifr_by_ceiling(self):
        r = classify_flight_category(ceiling_ft=800, visibility_sm=10)
        assert r.category is FlightCategory.IFR
        assert r.driven_by == "ceiling"

    def test_lifr_by_visibility(self):
        r = classify_flight_category(ceiling_ft=5000, visibility_sm=0.5)
        assert r.category is FlightCategory.LIFR

    def test_worst_of_two_wins(self):
        # Görüş MVFR (4 sm) ama tavan IFR (800 ft) -> IFR (daha kötü) kazanır
        r = classify_flight_category(ceiling_ft=800, visibility_sm=4)
        assert r.category is FlightCategory.IFR

    @pytest.mark.parametrize("ceiling,expected", [
        (400, FlightCategory.LIFR),
        (500, FlightCategory.IFR),     # 500 -> IFR (500 <= x < 1000)
        (999, FlightCategory.IFR),
        (1000, FlightCategory.MVFR),
        (3000, FlightCategory.MVFR),
        (3001, FlightCategory.VFR),
    ])
    def test_ceiling_boundaries(self, ceiling, expected):
        r = classify_flight_category(ceiling_ft=ceiling, visibility_sm=10)
        assert r.category is expected

    def test_missing_visibility_returns_none(self):
        # Görüş bilinmiyorsa sınıflandırılamaz -> data gap
        r = classify_flight_category(ceiling_ft=5000, visibility_sm=None)
        assert r.category is None
        assert r.driven_by is None


# ----------------------------------------------------------------------------
# Rüzgâr bileşenleri
# ----------------------------------------------------------------------------
class TestCrosswind:
    def test_direct_headwind(self):
        # Rüzgâr pistle aynı yönde -> yan rüzgâr 0, ön rüzgâr tam
        w = crosswind_component(runway_heading_deg=240, wind_dir_deg=240, wind_speed_kt=20)
        assert w.crosswind_kt == 0.0
        assert w.headwind_kt == 20.0

    def test_direct_crosswind_90deg(self):
        w = crosswind_component(runway_heading_deg=240, wind_dir_deg=330, wind_speed_kt=20)
        assert w.crosswind_kt == 20.0
        assert abs(w.headwind_kt) < 0.01

    def test_45_degrees(self):
        w = crosswind_component(runway_heading_deg=360, wind_dir_deg=45, wind_speed_kt=20)
        expected = round(20 * math.sin(math.radians(45)), 1)   # ~14.1
        assert w.crosswind_kt == expected
        assert w.headwind_kt == expected

    def test_tailwind_is_negative_headwind(self):
        # Rüzgâr pistin tam tersinden -> ön rüzgâr negatif (kuyruk rüzgârı)
        w = crosswind_component(runway_heading_deg=360, wind_dir_deg=180, wind_speed_kt=15)
        assert w.headwind_kt == -15.0
        assert w.crosswind_kt == 0.0

    def test_angle_wraparound(self):
        # 350° rüzgâr, 010° pist -> aradaki açı 20° (360 sınırını doğru geç)
        w = crosswind_component(runway_heading_deg=10, wind_dir_deg=350, wind_speed_kt=30)
        assert w.angle_deg == 20.0

    def test_exceeds_limit(self):
        assert exceeds_crosswind_limit(16, 15) is True
        assert exceeds_crosswind_limit(15, 15) is False
        assert exceeds_crosswind_limit(14.9, 15) is False


# ----------------------------------------------------------------------------
# VFR minima
# ----------------------------------------------------------------------------
class TestVfrMinima:
    def test_pass(self):
        checks = evaluate_vfr_minima(visibility_sm=10, ceiling_ft=5000,
                                     vis_min_sm=3, ceiling_min_ft=1000)
        assert all(c.status is CheckStatus.PASS for c in checks)

    def test_visibility_fail(self):
        checks = evaluate_vfr_minima(visibility_sm=2, ceiling_ft=5000,
                                     vis_min_sm=3, ceiling_min_ft=1000)
        vis = next(c for c in checks if c.name == "visibility_sm")
        assert vis.status is CheckStatus.FAIL

    def test_ceiling_none_passes(self):
        # Tavan yok = sınırsız = geçer
        checks = evaluate_vfr_minima(visibility_sm=10, ceiling_ft=None,
                                     vis_min_sm=3, ceiling_min_ft=1000)
        ceil = next(c for c in checks if c.name == "ceiling_ft")
        assert ceil.status is CheckStatus.PASS

    def test_visibility_unknown(self):
        checks = evaluate_vfr_minima(visibility_sm=None, ceiling_ft=5000,
                                     vis_min_sm=3, ceiling_min_ft=1000)
        vis = next(c for c in checks if c.name == "visibility_sm")
        assert vis.status is CheckStatus.UNKNOWN


# ----------------------------------------------------------------------------
# Config yükleme
# ----------------------------------------------------------------------------
class TestConfig:
    def test_load_c172(self):
        ac = load_aircraft("C172")
        assert ac.max_demonstrated_crosswind_kt == 15
        assert "Cessna" in ac.type

    def test_load_missing_aircraft(self):
        with pytest.raises(FileNotFoundError):
            load_aircraft("B747")

    def test_load_minima_tr(self):
        m = load_vfr_minima("TR", airspace="G", day_night="day")
        assert m.visibility_min_sm > 0
        assert m.ceiling_min_ft > 0

    def test_load_minima_faa(self):
        m = load_vfr_minima("FAA", airspace="G", day_night="day")
        assert m.visibility_min_sm == 1

    def test_end_to_end_crosswind_vs_config(self):
        # Entegrasyon: config limiti + hesaplanan yan rüzgâr
        ac = load_aircraft("C172")
        w = crosswind_component(runway_heading_deg=240, wind_dir_deg=330, wind_speed_kt=18)
        assert exceeds_crosswind_limit(w.crosswind_kt, ac.max_demonstrated_crosswind_kt) is True
