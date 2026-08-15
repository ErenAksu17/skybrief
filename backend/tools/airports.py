"""
Havaalanı / pist arama — ICAO'dan pist yönlerini bulur ve rüzgâra göre aktif pisti seçer.

Bu, "pist yönü bilinmiyor -> crosswind hesaplanamadı" data gap'ini kapatır:
kullanıcı pist vermezse, sistem havaalanının pistlerinden rüzgâra en uygun olanı
(rüzgâra karşı) otomatik seçer ve crosswind'i o pist için hesaplar.

Veri: backend/config/airports.yaml (curated; OurAirports ile genişletilebilir).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_AIRPORTS_FILE = Path(__file__).resolve().parent.parent / "config" / "airports.yaml"


@lru_cache(maxsize=1)
def _load() -> dict:
    return yaml.safe_load(_AIRPORTS_FILE.read_text(encoding="utf-8")) or {}


def runways(icao: str | None) -> list[float]:
    """ICAO için pist yön açılarını döndürür. Bilinmiyorsa boş liste."""
    if not icao:
        return []
    entry = _load().get(icao.upper())
    return list(entry["runways"]) if entry else []


def _angle_between(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def best_runway_for_wind(runway_headings: list[float], wind_dir_deg: float) -> float | None:
    """Rüzgâra en uygun pisti (rüzgâr yönüne en yakın = en çok ön rüzgâr) seçer.

    Rüzgâr FROM yönü olarak verilir; kalkışta rüzgâra karşı gidilir, yani pist yönü
    rüzgâr yönüne ne kadar yakınsa o kadar iyidir.
    """
    if not runway_headings:
        return None
    return min(runway_headings, key=lambda h: _angle_between(h, wind_dir_deg))


def resolve_runway(icao: str | None, provided_heading: float | None,
                   wind_dir_deg: float | None) -> float | None:
    """Kullanıcı pist verdiyse onu; vermediyse rüzgâra göre havaalanı pistinden seçileni döndürür.

    Havaalanı bilinmiyorsa veya rüzgâr yoksa None (crosswind hesaplanamaz -> data gap).
    """
    if provided_heading is not None:
        return provided_heading
    if wind_dir_deg is None:
        return None
    return best_runway_for_wind(runways(icao), wind_dir_deg)
