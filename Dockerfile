# SkyBrief — üretim imajı (deterministik brifing motoru)
FROM python:3.12-slim

# Log'lar anında görünsün, .pyc yazma.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Önce bağımlılıklar (katman önbelleği: kod değişince deps yeniden kurulmaz).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama kodu + config + frontend.
COPY backend/ backend/
COPY frontend/ frontend/

# Kök olmayan kullanıcı (güvenlik).
RUN useradd -m appuser
USER appuser

EXPOSE 8000

# Render $PORT verir; yoksa 8000. Tek worker (free tier).
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
