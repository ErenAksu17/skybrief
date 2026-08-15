"""
API veri sözleşmeleri (Pydantic v2).

Bu modeller sistemin dış yüzünü (istek/yanıt) ve ajanlar arası veri akışını tanımlar.
rules.py bunlara bağımlı değildir (saf kalır); bu modeller sentez/API katmanında kullanılır.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class FlightQuery(BaseModel):
    departure_icao: str | None = None
    destination_icao: str | None = None
    aircraft_type: str = "C172"
    departure_time: datetime | None = None
    pilot_rule: Literal["VFR", "IFR"] = "VFR"
    jurisdiction: Literal["TR", "FAA", "EASA"] = "TR"


class Citation(BaseModel):
    source: str                       # "SHGM SERA.5001" / "C172 POH s.2-13"
    page: int | None = None
    snippet: str = ""


class WxReport(BaseModel):
    station: str
    kind: Literal["METAR", "TAF"]
    issued: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    raw: str = ""
    visibility_sm: float | None = None
    ceiling_ft: int | None = None
    wind_dir_deg: int | None = None
    wind_speed_kt: int | None = None
    gust_kt: int | None = None
    category: Literal["VFR", "MVFR", "IFR", "LIFR"] | None = None


class RiskFactor(BaseModel):
    code: str
    severity: Literal["info", "caution", "warning"]
    message: str
    value: float | str | None = None
    source_tool: str | None = None    # hangi araç üretti (izlenebilirlik)
    citation: Citation | None = None


class DataGap(BaseModel):
    field: str
    reason: str


class Briefing(BaseModel):
    query: FlightQuery
    generated_at: datetime
    overall: Literal["FAVORABLE", "MARGINAL", "UNFAVORABLE", "INSUFFICIENT_DATA"]
    weather: list[WxReport] = Field(default_factory=list)
    risk_factors: list[RiskFactor] = Field(default_factory=list)
    data_gaps: list[DataGap] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    disclaimer: str
