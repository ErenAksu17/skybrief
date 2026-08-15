"""
Naive (deterministik) sorgu ayrıştırıcı.

Faz 1'de LLM orchestrator henüz yok; bu ayrıştırıcı serbest metinden KOLAY kısımları
çıkarır (ICAO kodları, VFR/IFR, uçak tipi). Doğal dil ZAMAN ayrıştırma ("yarın öğleden
sonra") bilerek yapılmaz — o tam olarak LLM orchestrator'ın işidir (Faz 2). Zaman,
yapılandırılmış `departure_time` alanıyla verilir.

Not: ICAO'ların BÜYÜK harf yazılmasını bekler (naive). LLM eklenince bu modül devre dışı kalır.
"""

from __future__ import annotations

import re

_ICAO_RE = re.compile(r"\b([A-Z]{4})\b")
_AIRCRAFT_RE = re.compile(r"\b([A-Z]{1,2}\d{2,3})\b")   # C172, C152, PA28...


def parse_query(text: str) -> dict:
    """Serbest metinden çıkarılabilen alanları bir sözlük olarak döndürür."""
    out: dict = {}
    if not text:
        return out

    icaos = _ICAO_RE.findall(text)
    if icaos:
        out["departure_icao"] = icaos[0]
        if len(icaos) > 1:
            out["destination_icao"] = icaos[1]

    upper = text.upper()
    if "IFR" in upper:
        out["pilot_rule"] = "IFR"
    elif "VFR" in upper:
        out["pilot_rule"] = "VFR"

    aircraft = [a for a in _AIRCRAFT_RE.findall(text) if a not in icaos]
    if aircraft:
        out["aircraft_type"] = aircraft[0]

    return out
