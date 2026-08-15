"""
Deterministik uçuş kuralları motoru — SkyBrief'in kalbi.

Bu modülde LLM YOKTUR. Tüm güvenlik matematiği burada, saf Python ile yapılır;
böylece birim testlerle kanıtlanabilir ve halüsinasyon riski taşımaz.
LLM bu fonksiyonları "araç" olarak çağırır ama sonucu asla kendisi uydurmaz.

İçerik:
  • classify_flight_category  -> VFR / MVFR / IFR / LIFR (FAA eşikleri, config'lenebilir)
  • crosswind_component       -> yan/ön rüzgâr bileşenleri (trigonometri)
  • exceeds_crosswind_limit   -> POH limit karşılaştırması
  • evaluate_vfr_minima       -> görüş/tavan minimalarına uygunluk
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, IntEnum


# ----------------------------------------------------------------------------
# Uçuş kategorisi (FAA standart eşikleri)
# ----------------------------------------------------------------------------
class FlightCategory(IntEnum):
    """Değer = kısıtlılık sırası (büyük = daha kötü). 'En kötüyü seç' için IntEnum."""
    VFR = 0
    MVFR = 1
    IFR = 2
    LIFR = 3

    @property
    def label(self) -> str:
        return self.name


@dataclass(frozen=True)
class CategoryResult:
    category: FlightCategory | None      # None = sınıflandırılamadı (data gap)
    driven_by: str | None                # "visibility" | "ceiling" | None
    ceiling_ft: int | None
    visibility_sm: float | None


def _cat_from_ceiling(ceiling_ft: int | None) -> FlightCategory:
    # METAR semantiği: tavan raporlanmamışsa "tavan yok" (sınırsız) demektir -> VFR.
    if ceiling_ft is None:
        return FlightCategory.VFR
    if ceiling_ft < 500:
        return FlightCategory.LIFR
    if ceiling_ft < 1000:
        return FlightCategory.IFR
    if ceiling_ft <= 3000:
        return FlightCategory.MVFR
    return FlightCategory.VFR


def _cat_from_vis(visibility_sm: float | None) -> FlightCategory | None:
    # Görüş bilinmiyorsa sınıflandıramayız (data gap). None döndür.
    if visibility_sm is None:
        return None
    if visibility_sm < 1:
        return FlightCategory.LIFR
    if visibility_sm < 3:
        return FlightCategory.IFR
    if visibility_sm <= 5:
        return FlightCategory.MVFR
    return FlightCategory.VFR


def classify_flight_category(ceiling_ft: int | None,
                             visibility_sm: float | None) -> CategoryResult:
    """Tavan ve görüşten uçuş kategorisini hesaplar (daha kısıtlayıcı olan kazanır).

    - visibility_sm None ise -> kategori None (data gap; abstain tetikler).
    - ceiling_ft None ise -> tavan sınırsız (VFR katkısı) kabul edilir.
    """
    vis_cat = _cat_from_vis(visibility_sm)
    if vis_cat is None:
        return CategoryResult(None, None, ceiling_ft, visibility_sm)

    ceil_cat = _cat_from_ceiling(ceiling_ft)
    worst = max(vis_cat, ceil_cat)
    driven_by = "visibility" if vis_cat >= ceil_cat else "ceiling"
    return CategoryResult(worst, driven_by, ceiling_ft, visibility_sm)


# ----------------------------------------------------------------------------
# Rüzgâr bileşenleri
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class WindComponents:
    crosswind_kt: float     # daima >= 0 (mutlak yan rüzgâr)
    headwind_kt: float      # negatif = kuyruk rüzgârı (tailwind)
    angle_deg: float        # rüzgâr ile pist arası açı (0–180)


def crosswind_component(runway_heading_deg: float,
                        wind_dir_deg: float,
                        wind_speed_kt: float) -> WindComponents:
    """Pist yönü, rüzgâr yönü ve hızından yan/ön rüzgâr bileşenlerini hesaplar.

    Pist yönü gerçek/manyetik derece (örn. RWY 24 ~ 240°). Açı 0–180'e normalize edilir.
    """
    diff = abs((wind_dir_deg - runway_heading_deg + 180) % 360 - 180)
    rad = math.radians(diff)
    crosswind = abs(wind_speed_kt * math.sin(rad))
    headwind = wind_speed_kt * math.cos(rad)
    return WindComponents(
        crosswind_kt=round(crosswind, 1),
        headwind_kt=round(headwind, 1),
        angle_deg=round(diff, 1),
    )


def exceeds_crosswind_limit(crosswind_kt: float, max_demonstrated_kt: float) -> bool:
    """Yan rüzgâr, uçağın POH 'maximum demonstrated crosswind' değerini aşıyor mu?"""
    return crosswind_kt > max_demonstrated_kt


# ----------------------------------------------------------------------------
# VFR minima kontrolü
# ----------------------------------------------------------------------------
class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"     # veri eksik -> data gap


@dataclass(frozen=True)
class MinimaCheck:
    name: str
    required: float
    actual: float | None
    status: CheckStatus


def _check_min(name: str, required: float, actual: float | None,
               none_means_unlimited: bool = False) -> MinimaCheck:
    if actual is None:
        # Tavan için None = "tavan yok" = geçer; görüş için None = bilinmiyor.
        status = CheckStatus.PASS if none_means_unlimited else CheckStatus.UNKNOWN
        return MinimaCheck(name, required, None, status)
    status = CheckStatus.PASS if actual >= required else CheckStatus.FAIL
    return MinimaCheck(name, required, actual, status)


def evaluate_vfr_minima(visibility_sm: float | None,
                        ceiling_ft: int | None,
                        vis_min_sm: float,
                        ceiling_min_ft: float) -> list[MinimaCheck]:
    """Mevcut görüş/tavanı, verilen minima değerleriyle karşılaştırır.

    Minima değerleri config'ten (jurisdiction'a göre) gelir — bu fonksiyon sabit
    eşik içermez, yalnızca karşılaştırır.
    """
    return [
        _check_min("visibility_sm", vis_min_sm, visibility_sm),
        _check_min("ceiling_ft", ceiling_min_ft, ceiling_ft, none_means_unlimited=True),
    ]
