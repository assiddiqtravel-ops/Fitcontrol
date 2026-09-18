#!/usr/bin/env bash
# Entrypoint dispatcher for the backend image.
#   api          -> run migrations then start the FastAPI server
#   bot          -> run the Telegram bot (long polling)
#   scheduler    -> run the notification scheduler loop
#   migrate      -> run Alembic migrations and exit
#   seed         -> load development sample data and exit
set -euo pipefail

wait_for_db() {
  echo "Waiting for database..."
  python - <<'PY'
import asyncio, os, sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    url = os.environ["DATABASE_URL"]
    for attempt in range(30):
        try:
            eng = create_async_engine(url)
            async with eng.connect() as c:
                await c.execute(text("SELECT 1"))
            await eng.dispose()
            print("Database is ready.")
            return
        except Exception as e:  # noqa
            print(f"  db not ready ({attempt+1}/30): {e}")
            await asyncio.sleep(2)
    sys.exit("Database did not become ready in time.")

asyncio.run(main())
PY
}

cmd="${1:-api}"

case "$cmd" in
  api)
    wait_for_db
    alembic upgrade head
    # Render (and most PaaS) inject the port via $PORT; fall back to 8000 locally.
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
    ;;
  bot)
    wait_for_db
    exec python -m app.bot.main
    ;;
  scheduler)
    wait_for_db
    exec python -m app.bot.notifications
    ;;
  migrate)
    wait_for_db
    exec alembic upgrade head
    ;;
  seed)
    wait_for_db
    exec python -m app.seed
    ;;
  *)
    exec "$@"
    ;;
esac
