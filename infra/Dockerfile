FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir \
        "fastapi>=0.115" "uvicorn>=0.30" "sqlalchemy>=2.0" "pydantic>=2.7" \
        "httpx>=0.27" "psycopg[binary]>=3.1"

COPY common ./common
COPY world ./world
COPY harness ./harness
COPY scoring ./scoring
COPY view ./view
COPY tools ./tools
COPY cases ./cases

ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m", "harness.run"]
