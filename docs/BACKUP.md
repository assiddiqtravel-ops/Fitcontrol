# PostgreSQL backup & restore — FitControl

Financial data must never be lost. Take regular backups and test restores.

## Assumptions

Values come from your `.env` (`POSTGRES_USER`, `POSTGRES_DB`). In docker-compose
the database service is named `db`.

## Backup (logical dump)

Create a compressed custom-format dump (recommended — supports selective and
parallel restore):

```bash
# From the host, against the compose db container:
docker compose exec -T db \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -F c \
  > "backup_$(date +%Y%m%d_%H%M%S).dump"
```

Plain SQL alternative (human-readable):

```bash
docker compose exec -T db \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  > "backup_$(date +%Y%m%d_%H%M%S).sql"
```

## Restore

Custom-format dump into a fresh database:

```bash
# Ensure the target DB exists and is empty, then:
cat backup_YYYYMMDD_HHMMSS.dump | docker compose exec -T db \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists
```

Plain SQL dump:

```bash
cat backup_YYYYMMDD_HHMMSS.sql | docker compose exec -T db \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

## Scheduling

Run a nightly cron on the host, e.g.:

```cron
0 2 * * * cd /path/to/fitcontrol && docker compose exec -T db \
  pg_dump -U fitcontrol -d fitcontrol -F c > /backups/fitcontrol_$(date +\%F).dump
```

Rotate/retain (keep 14 days):

```bash
find /backups -name 'fitcontrol_*.dump' -mtime +14 -delete
```

## Notes

- Always test a restore into a throwaway database before you rely on a backup.
- Store backups off-box (object storage / another host) and encrypt at rest.
- Migrations are versioned by Alembic; after restoring an older dump, run
  `docker compose run --rm api migrate` to bring the schema to `head`.
