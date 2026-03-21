FROM python:3.11-slim

WORKDIR /webapp

# Instalar dependencias del sistema para pandas/numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código (no los datos — se bind-montan en runtime)
COPY app/ ./app/
COPY static/ ./static/

EXPOSE 8000

# 1 worker: SQLite se escribe solo en startup, lecturas OK multi-thread
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
