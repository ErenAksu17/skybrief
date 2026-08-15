"""
Config okuyucu — uçak limitleri ve VFR minimalarını YAML'dan yükler.

NEDEN config: Güvenlik eşikleri (crosswind limiti, minima) koda gömülmez;
jurisdiction'a göre değişir ve domain uzmanı (pilot) tarafından doğrulanmalıdır.
Kod bu değerleri okur, matematiği rules.py yapar.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

# backend/tools/config_lookup.py  ->  backend/config/
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


@dataclass(frozen=True)
class AircraftLimits:
    type: str
    max_demonstrated_crosswind_kt: float
    service_ceiling_ft: int
    vfr_fuel_reserve_min: int


def load_aircraft(type_code: str) -> AircraftLimits:
    path = CONFIG_DIR / "aircraft" / f"{type_code}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Uçak config bulunamadı: {type_code} ({path})")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return AircraftLimits(
        type=data["type"],
        max_demonstrated_crosswind_kt=data["max_demonstrated_crosswind_kt"],
        service_ceiling_ft=data["service_ceiling_ft"],
        vfr_fuel_reserve_min=data["vfr_fuel_reserve_min"],
    )


@dataclass(frozen=True)
class VfrMinima:
    jurisdiction: str
    airspace: str
    day_night: str
    visibility_min_sm: float
    ceiling_min_ft: int


def load_vfr_minima(jurisdiction: str, airspace: str = "G",
                    day_night: str = "day") -> VfrMinima:
    path = CONFIG_DIR / "minima" / f"{jurisdiction}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Minima config bulunamadı: {jurisdiction} ({path})")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    try:
        entry = data[airspace][day_night]
    except KeyError as e:
        raise KeyError(f"{jurisdiction} config'inde {airspace}/{day_night} tanımı yok") from e
    return VfrMinima(
        jurisdiction=jurisdiction,
        airspace=airspace,
        day_night=day_night,
        visibility_min_sm=entry["visibility_min_sm"],
        ceiling_min_ft=entry["ceiling_min_ft"],
    )
