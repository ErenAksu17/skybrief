"""
Havaalanı/pist arama ve rüzgâra göre aktif pist seçimi testleri.
"""

from backend.tools.airports import (
    runways, best_runway_for_wind, resolve_runway,
)


class TestRunways:
    def test_known_airport(self):
        assert runways("LTAC") == [30, 210]

    def test_case_insensitive(self):
        assert runways("ltac") == [30, 210]

    def test_unknown_airport(self):
        assert runways("ZZZZ") == []

    def test_none(self):
        assert runways(None) == []


class TestBestRunway:
    def test_picks_runway_into_wind(self):
        # Rüzgâr 020'den; pistler 30/210 -> 30 seçilmeli (rüzgâra en yakın)
        assert best_runway_for_wind([30, 210], 20) == 30

    def test_picks_opposite_when_wind_reverses(self):
        assert best_runway_for_wind([30, 210], 200) == 210

    def test_empty(self):
        assert best_runway_for_wind([], 180) is None


class TestResolveRunway:
    def test_user_value_wins(self):
        # Kullanıcı açıkça pist verdiyse o kullanılır (DB'ye bakılmaz)
        assert resolve_runway("LTAC", 123, 20) == 123

    def test_auto_from_airport_and_wind(self):
        # Pist verilmedi -> LTAC pistlerinden rüzgâra göre seçilir
        assert resolve_runway("LTAC", None, 20) == 30

    def test_unknown_airport_returns_none(self):
        assert resolve_runway("ZZZZ", None, 20) is None

    def test_no_wind_returns_none(self):
        assert resolve_runway("LTAC", None, None) is None
