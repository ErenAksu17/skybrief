"""
Sorgu ayrıştırıcı + /api/brief uç noktası testleri.

Ağ, weather.fetch_metar/fetch_taf monkeypatch'lenerek izole edilir (deterministik).
"""

import pytest
from fastapi.testclient import TestClient

import backend.tools.weather as weather
from backend.main import app
from backend.models import WxReport
from backend.query_parser import parse_query

client = TestClient(app)


def _wx(icao, cat="VFR", vis=10, ceil=5000, wd=240, ws=10):
    return WxReport(station=icao, kind="METAR", visibility_sm=vis, ceiling_ft=ceil,
                    wind_dir_deg=wd, wind_speed_kt=ws, category=cat)


# ----------------------------------------------------------------------------
class TestParseQuery:
    def test_extracts_two_icaos(self):
        out = parse_query("LTBA LTAC C172 VFR")
        assert out["departure_icao"] == "LTBA"
        assert out["destination_icao"] == "LTAC"

    def test_extracts_aircraft_and_rule(self):
        out = parse_query("PA28 ile IFR ucus LTAI LTFM")
        assert out["aircraft_type"] == "PA28"
        assert out["pilot_rule"] == "IFR"

    def test_empty(self):
        assert parse_query("") == {}


# ----------------------------------------------------------------------------
class TestBriefEndpoint:
    def test_health(self):
        assert client.get("/api/health").json() == {"status": "ok"}

    def test_favorable_structured(self, monkeypatch):
        async def fake_metar(icao, c=None):
            return _wx(icao)
        monkeypatch.setattr(weather, "fetch_metar", fake_metar)

        r = client.post("/api/brief", json={
            "departure_icao": "LTBA", "destination_icao": "LTAC",
            "departure_runway_heading": 240, "destination_runway_heading": 30,
        })
        assert r.status_code == 200
        b = r.json()
        assert b["overall"] == "FAVORABLE"
        assert b["disclaimer"]
        assert len(b["weather"]) == 2

    def test_free_text_query(self, monkeypatch):
        async def fake_metar(icao, c=None):
            return _wx(icao)
        monkeypatch.setattr(weather, "fetch_metar", fake_metar)

        r = client.post("/api/brief", json={"query": "LTBA LTAC C172 VFR",
                                            "departure_runway_heading": 240})
        assert r.status_code == 200
        assert r.json()["query"]["departure_icao"] == "LTBA"

    def test_abstain_on_missing_destination(self, monkeypatch):
        async def fake_metar(icao, c=None):
            return None if icao == "LTAC" else _wx(icao)
        monkeypatch.setattr(weather, "fetch_metar", fake_metar)

        r = client.post("/api/brief", json={
            "departure_icao": "LTBA", "destination_icao": "LTAC",
        })
        assert r.json()["overall"] == "INSUFFICIENT_DATA"

    def test_unknown_aircraft_returns_400(self):
        # Config önce yüklendiği için ağa gitmeden 400 döner
        r = client.post("/api/brief", json={"departure_icao": "LTBA",
                                            "aircraft_type": "B747"})
        assert r.status_code == 400
