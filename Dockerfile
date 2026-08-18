# ---------- 1) Frontend build (React + Vite + Tailwind + shadcn/ui) ----------
FROM node:22-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build          # -> /web/dist

# ---------- 2) Backend (deterministik brifing motoru) ----------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
# Frontend build çıktısını FastAPI'nin servis edeceği yere kopyala.
COPY --from=web /web/dist ./web/dist

RUN useradd -m appuser
USER appuser

EXPOSE 8000

# Render $PORT verir; yoksa 8000.
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
