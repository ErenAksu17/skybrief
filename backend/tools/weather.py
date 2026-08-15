"""
METAR/TAF istemcisi — aviationweather.gov Data API (ücretsiz, anahtarsız).

Sorumlulukları:
  1) Ham METAR/TAF verisini çek (JSON).
  2) İşimize yarayan alanları güvenli biçimde parse et (görüş, tavan, rüzgâr).
  3) WxReport nesnesine dönüştür; uçuş kategorisini rules engine ile hesapla.
  4) TAF için: tahmin dönemlerini ayrıştır ve istenen zamana denk geleni seç
     (denk gelmiyorsa None -> "insufficient data"/abstain).

Tasarım notu: Parse fonksiyonları ağdan bağımsızdır (saf) -> birim test edilebilir.
Ağ çağrıları (fetch_*) ince sarmalayıcılardır.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from backend.models import WxReport
from backend.tools.rules import classify_flight_category

BASE_URL = "https://aviationweather.gov/api/data"

# Tavan sayılan bulut örtüsü tipleri (broken/overcast/obscured).
_CEILING_COVERS = {"BKN", "OVC", "OVX"}


# ----------------------------------------------------------------------------
# Saf parse yardımcıları (ağ yok — test edilebilir)
# ----------------------------------------------------------------------------
def parse_visibility_sm(value) -> float | None:
    """aviationweather 'visib' alanını statute mile'a çevirir.

    Örnekler: 10 -> 10.0 ; "10+" -> 10.0 ; "6" -> 6.0 ; "1.5" -> 1.5 ; None -> None.
    Çözümlenemezse None (data gap).
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().rstrip("+").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_ceiling_ft(clouds) -> int | None:
    """Bulut katmanlarından tavanı bulur: en düşük BKN/OVC/OVX taban yüksekliği (ft).

    FEW/SCT tavan sayılmaz. Katman yoksa veya sadece FEW/SCT varsa -> None (tavan yok).
    """
    if not clouds:
        return None
    bases = [
        c["base"] for c in clouds
        if c.get("cover") in _CEILING_COVERS and c.get("base") is not None
    ]
    return int(min(bases)) if bases else None


def _parse_wind_dir(value) -> int | None:
    # "VRB" (değişken) veya None -> None; sayı -> int.
    if value is None or value == "VRB":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _epoch_to_dt(ts) -> datetime | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def metar_to_wxreport(obj: dict) -> WxReport:
    """Ham METAR JSON nesnesini WxReport'a çevirir ve kategoriyi hesaplar."""
    visibility = parse_visibility_sm(obj.get("visib"))
    ceiling = parse_ceiling_ft(obj.get("clouds"))
    cat = classify_flight_category(ceiling_ft=ceiling, visibility_sm=visibility)

    return WxReport(
        station=obj.get("icaoId", "?"),
        kind="METAR",
        issued=_epoch_to_dt(obj.get("obsTime")),
        raw=obj.get("rawOb", ""),
        visibility_sm=visibility,
        ceiling_ft=ceiling,
        wind_dir_deg=_parse_wind_dir(obj.get("wdir")),
        wind_speed_kt=obj.get("wspd"),
        gust_kt=obj.get("wgst"),
        category=cat.category.label if cat.category is not None else None,
    )


def taf_periods_to_wxreports(obj: dict) -> list[WxReport]:
    """TAF JSON nesnesini, her tahmin dönemi bir WxReport olacak şekilde ayrıştırır."""
    station = obj.get("icaoId", "?")
    raw = obj.get("rawTAF", "")
    reports: list[WxReport] = []
    for fc in obj.get("fcsts", []) or []:
        visibility = parse_visibility_sm(fc.get("visib"))
        ceiling = parse_ceiling_ft(fc.get("clouds"))
        cat = classify_flight_category(ceiling_ft=ceiling, visibility_sm=visibility)
        reports.append(WxReport(
            station=station,
            kind="TAF",
            valid_from=_epoch_to_dt(fc.get("timeFrom")),
            valid_to=_epoch_to_dt(fc.get("timeTo")),
            raw=raw,
            visibility_sm=visibility,
            ceiling_ft=ceiling,
            wind_dir_deg=_parse_wind_dir(fc.get("wdir")),
            wind_speed_kt=fc.get("wspd"),
            gust_kt=fc.get("wgst"),
            category=cat.category.label if cat.category is not None else None,
        ))
    return reports


def select_taf_period(periods: list[WxReport], when: datetime) -> WxReport | None:
    """Verilen zamanı (UTC) kapsayan TAF dönemini döndürür.

    Hiçbir dönem kapsamıyorsa None -> çağıran taraf 'insufficient data' işaretler (abstain).
    """
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    for p in periods:
        if p.valid_from and p.valid_to and p.valid_from <= when < p.valid_to:
            return p
    return None


# ----------------------------------------------------------------------------
# Ağ sarmalayıcıları
# ----------------------------------------------------------------------------
async def _get_json(path: str, params: dict, client: httpx.AsyncClient | None) -> list:
    own = client is None
    client = client or httpx.AsyncClient()
    try:
        resp = await client.get(f"{BASE_URL}/{path}", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        # API tek id için de liste döndürür; boşsa [].
        return data if isinstance(data, list) else [data]
    finally:
        if own:
            await client.aclose()


async def fetch_metar(icao: str, client: httpx.AsyncClient | None = None) -> WxReport | None:
    """Bir istasyonun en güncel METAR'ını çeker. Veri yoksa None."""
    rows = await _get_json("metar", {"ids": icao, "format": "json"}, client)
    return metar_to_wxreport(rows[0]) if rows else None


async def fetch_taf(icao: str, client: httpx.AsyncClient | None = None) -> list[WxReport]:
    """Bir istasyonun TAF tahmin dönemlerini çeker (WxReport listesi). Veri yoksa []."""
    rows = await _get_json("taf", {"ids": icao, "format": "json"}, client)
    return taf_periods_to_wxreports(rows[0]) if rows else []
