"""
SkyBrief FastAPI uygulaması (Faz 1 — LLM'siz deterministik pipeline).

Uç noktalar:
  GET  /api/health   -> sağlık kontrolü
  POST /api/brief    -> uçuş brifingi (Briefing JSON)

Çalıştırma:  uvicorn backend.main:app --reload   (SkyBrief kökünden)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.models import Briefing, FlightQuery
from backend.pipeline import generate_briefing
from backend.query_parser import parse_query
from backend.synthesizer import validate_no_fabrication

app = FastAPI(title="SkyBrief API", version="0.1 (Faz 1)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class BriefRequest(BaseModel):
    """Serbest metin (`query`) VEYA yapılandırılmış alanlar. Yapılandırılmış alanlar
    metinden çıkarılanı ezer."""
    query: str | None = None
    departure_icao: str | None = None
    destination_icao: str | None = None
    aircraft_type: str | None = None
    pilot_rule: Literal["VFR", "IFR"] | None = None
    jurisdiction: Literal["TR", "FAA", "EASA"] | None = None
    departure_time: datetime | None = None
    departure_runway_heading: float | None = None
    destination_runway_heading: float | None = None


def _build_query(req: BriefRequest) -> FlightQuery:
    # 1) Serbest metinden çıkar (varsa), 2) yapılandırılmış alanlarla ez.
    fields: dict = {}
    if req.query:
        fields.update(parse_query(req.query))
    for key in ("departure_icao", "destination_icao", "aircraft_type",
                "pilot_rule", "jurisdiction", "departure_time"):
        val = getattr(req, key)
        if val is not None:
            fields[key] = val
    # FlightQuery varsayılanları (aircraft_type=C172, pilot_rule=VFR, jurisdiction=TR)
    return FlightQuery(**{k: v for k, v in fields.items() if v is not None})


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/brief", response_model=Briefing)
async def brief(req: BriefRequest) -> Briefing:
    query = _build_query(req)
    try:
        result = await generate_briefing(
            query,
            departure_runway_heading=req.departure_runway_heading,
            destination_runway_heading=req.destination_runway_heading,
        )
    except FileNotFoundError as e:
        # Bilinmeyen uçak tipi / jurisdiction config'i
        raise HTTPException(status_code=400, detail=str(e))

    # Guardrail: deterministik sentezde temiz olmalı; yine de izlenemeyen sayı varsa düşür.
    offenders = validate_no_fabrication(result.briefing, result.allowed_values)
    if offenders:
        codes = {rf.code for rf in offenders}
        result.briefing.risk_factors = [
            rf for rf in result.briefing.risk_factors if rf.code not in codes
        ]
    return result.briefing


# --- Frontend'i servis et (tek komutla local demo) -----------------------
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    @app.get("/")
    async def index():
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="static")
