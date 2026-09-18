FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps: psycopg2 needs libpq; build tools for any wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt ./
# psycopg2-binary is needed by Alembic (sync driver) in the container.
RUN pip install -r requirements.txt psycopg2-binary==2.9.10

COPY . .

RUN chmod +x entrypoint.sh

EXPOSE 8000

# Default: run the API (compose overrides `command` for bot/scheduler).
ENTRYPOINT ["./entrypoint.sh"]
CMD ["api"]
