"""
METAR/TAF parse testleri — ağdan bağımsız (örnek JSON ile).

Ağ çağrısı test etmeyiz (kırılgan olur); parse mantığını sabit örneklerle kanıtlarız.
"""

import asyncio
from datetime import datetime, timezone

import httpx

from backend.tools import weather
from backend.tools.weather import (
    parse_visibility_sm,
    parse_ceiling_ft,
    metar_to_wxreport,
    taf_periods_to_wxreports,
    select_taf_period,
)

# aviationweather.gov METAR JSON şekline benzer örnek
METAR_SAMPLE = {
    "icaoId": "LTBA", "obsTime": 1700000000,
    "wdir": 300, "wspd": 18, "wgst": 25, "visib": "4",
    "clouds": [
        {"cover": "FEW", "base": 2500},
        {"cover": "BKN", "base": 900},
        {"cover": "OVC", "base": 3000},
    ],
    "rawOb": "LTBA 010650Z 30018G25KT 4SM FEW025 BKN009 OVC030",
}

TAF_SAMPLE = {
    "icaoId": "LTAC", "rawTAF": "LTAC 010500Z 0106/0212 ...",
    "fcsts": [
        {"timeFrom": 1700000000, "timeTo": 1700003600, "wdir": 250, "wspd": 8,
         "visib": "6+", "clouds": [{"cover": "SCT", "base": 20000}]},
        {"timeFrom": 1700003600, "timeTo": 1700007200, "wdir": 270, "wspd": 12,
         "visib": "3", "clouds": [{"cover": "OVC", "base": 700}]},
    ],
}


class TestParseVisibility:
    def test_plus_notation(self):
        assert parse_visibility_sm("10+") == 10.0

    def test_numeric(self):
        assert parse_visibility_sm(6) == 6.0
        assert parse_visibility_sm("1.5") == 1.5

    def test_none_and_garbage(self):
        assert parse_visibility_sm(None) is None
        assert parse_visibility_sm("abc") is None


class TestParseCeiling:
    def test_picks_lowest_broken_or_overcast(self):
        assert parse_ceiling_ft(METAR_SAMPLE["clouds"]) == 900

    def test_few_sct_are_not_ceiling(self):
        clouds = [{"cover": "FEW", "base": 2500}, {"cover": "SCT", "base": 4000}]
        assert parse_ceiling_ft(clouds) is None

    def test_empty(self):
        assert parse_ceiling_ft([]) is None
        assert parse_ceiling_ft(None) is None


class TestMetarToWxReport:
    def test_fields_and_category(self):
        wx = metar_to_wxreport(METAR_SAMPLE)
        assert wx.station == "LTBA"
        assert wx.kind == "METAR"
        assert wx.visibility_sm == 4.0
        assert wx.ceiling_ft == 900
        assert wx.wind_dir_deg == 300
        assert wx.wind_speed_kt == 18
        assert wx.gust_kt == 25
        # görüş 4sm -> MVFR, tavan 900ft -> IFR; daha kötü olan IFR kazanır
        assert wx.category == "IFR"
        assert wx.issued == datetime.fromtimestamp(1700000000, tz=timezone.utc)

    def test_variable_wind(self):
        obj = dict(METAR_SAMPLE, wdir="VRB")
        wx = metar_to_wxreport(obj)
        assert wx.wind_dir_deg is None


class TestTaf:
    def test_parses_all_periods(self):
        periods = taf_periods_to_wxreports(TAF_SAMPLE)
        assert len(periods) == 2
        assert periods[0].kind == "TAF"
        assert periods[0].category == "VFR"     # 6+ görüş, tavan yok
        assert periods[1].ceiling_ft == 700
        assert periods[1].category == "IFR"     # tavan 700 -> IFR

    def test_select_period_inside_window(self):
        periods = taf_periods_to_wxreports(TAF_SAMPLE)
        when = datetime.fromtimestamp(1700005000, tz=timezone.utc)  # 2. dönem içi
        sel = select_taf_period(periods, when)
        assert sel is not None
        assert sel.ceiling_ft == 700

    def test_select_period_outside_window_returns_none(self):
        # İstenen zaman TAF penceresi dışında -> None (abstain sinyali)
        periods = taf_periods_to_wxreports(TAF_SAMPLE)
        when = datetime.fromtimestamp(1700100000, tz=timezone.utc)
        assert select_taf_period(periods, when) is None

    def test_naive_datetime_treated_as_utc(self):
        periods = taf_periods_to_wxreports(TAF_SAMPLE)
        when = datetime.fromtimestamp(1700001000, tz=timezone.utc).replace(tzinfo=None)
        sel = select_taf_period(periods, when)
        assert sel is not None  # tz'siz zaman UTC kabul edilir


class TestEmptyResponse:
    """Bilinmeyen ICAO'da API boş gövde döndürür -> çökme değil, dürüst 'veri yok'."""

    def test_empty_body_metar_returns_none(self):
        transport = httpx.MockTransport(lambda req: httpx.Response(200, text=""))

        async def go():
            async with httpx.AsyncClient(transport=transport) as client:
                return await weather.fetch_metar("ZZZZ", client)

        assert asyncio.run(go()) is None

    def test_empty_body_taf_returns_empty_list(self):
        transport = httpx.MockTransport(lambda req: httpx.Response(200, text=""))

        async def go():
            async with httpx.AsyncClient(transport=transport) as client:
                return await weather.fetch_taf("ZZZZ", client)

        assert asyncio.run(go()) == []
