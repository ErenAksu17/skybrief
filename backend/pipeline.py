"""
Brifing pipeline — araçları bir araya getiren orkestrasyon (LLM'siz, Faz 1).

Akış:
  1) Config'i yükle (uçak limitleri + minima) — hızlı başarısızlık için önce.
  2) Kalkış/varış için hava verisini çek:
       - Zaman yakın/geçmiş ise METAR (mevcut koşullar)
       - Zaman gelecekte ise TAF + istenen zamana denk dönem (yoksa None -> abstain)
  3) İstasyonları kur ve deterministik synthesizer ile Briefing üret.

Ağ hataları istasyon bazında yutulur -> ilgili istasyon 'veri yok' data gap'i olur
(sistem sessizce çökmez, dürüstçe abstain eder).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from backend.models import FlightQuery
from backend.synthesizer import Station, SynthesisResult, build_briefing
from backend.tools import weather
from backend.tools.airports import resolve_runway
from backend.tools.config_lookup import load_aircraft, load_vfr_minima

# Jurisdiction -> minima config dosyası eşlemesi (EASA de SERA kullanır -> TR).
_JURISDICTION_FILE = {"TR": "TR", "EASA": "TR", "FAA": "FAA"}

# Bu kadar ileri bir zaman istenirse TAF'a geç (aksi halde METAR yeterli).
_TAF_HORIZON = timedelta(minutes=90)


async def _station_wx(icao: str | None, when: datetime, use_taf: bool,
                      client: httpx.AsyncClient):
    if not icao:
        return None
    try:
        if use_taf:
            periods = await weather.fetch_taf(icao, client)
            return weather.select_taf_period(periods, when)   # kapsamıyorsa None -> abstain
        return await weather.fetch_metar(icao, client)
    except httpx.HTTPError:
        return None   # ağ/HTTP hatası -> data gap olarak ele alınır


async def generate_briefing(query: FlightQuery,
                            departure_runway_heading: float | None = None,
                            destination_runway_heading: float | None = None,
                            now: datetime | None = None,
                            client: httpx.AsyncClient | None = None) -> SynthesisResult:
    now = now or datetime.now(timezone.utc)

    # 1) Config önce (bilinmeyen uçak/jurisdiction -> erken, anlamlı hata)
    aircraft = load_aircraft(query.aircraft_type)
    juris_file = _JURISDICTION_FILE.get(query.jurisdiction, "TR")
    minima = load_vfr_minima(juris_file, airspace="G", day_night="day")

    # 2) Referans zaman + METAR/TAF seçimi
    ref_time = query.departure_time or now
    use_taf = ref_time > now + _TAF_HORIZON

    own = client is None
    client = client or httpx.AsyncClient()
    try:
        dep_wx = await _station_wx(query.departure_icao, ref_time, use_taf, client)
        dst_wx = await _station_wx(query.destination_icao, ref_time, use_taf, client)
    finally:
        if own:
            await client.aclose()

    # 3) Pist yönünü çöz: kullanıcı vermediyse havaalanı DB'sinden rüzgâra göre seç.
    dep_rwy = resolve_runway(query.departure_icao, departure_runway_heading,
                             dep_wx.wind_dir_deg if dep_wx else None)
    dst_rwy = resolve_runway(query.destination_icao, destination_runway_heading,
                             dst_wx.wind_dir_deg if dst_wx else None)

    # 4) Sentez
    stations = [
        Station("departure", query.departure_icao, dep_wx, dep_rwy),
        Station("destination", query.destination_icao, dst_wx, dst_rwy),
    ]
    return build_briefing(query, stations, aircraft, minima, now=now)
