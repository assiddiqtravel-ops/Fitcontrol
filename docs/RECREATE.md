# Как воссоздать FitControl «с нуля» (памятка для будущей сессии)

Этот файл — инструкция, которую Claude (или любой разработчик) читает, чтобы
заново создать и развернуть такого же бота, как FitControl. Весь исходный код
уже лежит в этом репозитории — его достаточно клонировать и развернуть.

## В следующий раз — одна команда

Скажи Claude:

> «Создай/разверни бота как FitControl (репозиторий `assiddiqtravel-ops/Fitcontrol`).
> Спрашивай у меня данные поэтапно.»

Claude прочитает этот файл + `README.md` + `docs/DEPLOYMENT.md` и пойдёт по шагам,
задавая вопросы ниже.

---

## Какие данные Claude спросит поэтапно (подготовь заранее)

### Этап A — Продукт
1. **Название продукта/клуба** (брендинг, напр. «FitControl»).
2. **Языки интерфейса** (по умолчанию: русский + узбекский латиница).
3. **Таймзона клубов** (по умолчанию `Asia/Tashkent`).
4. **Валюта** (по умолчанию UZS, целые суммы без копеек).

> Если это точная копия FitControl — на этапе A можно просто сказать
> «как есть, по умолчанию».

### Этап B — Telegram
5. **Токен бота** из [@BotFather](https://t.me/BotFather) (`/newbot` → скопировать токен).
   *(Присылай в личном сообщении; в код он не попадает — только в переменные Render.)*
6. **Username бота** (напр. `@Fitcontroluzbot`) — чтобы сверять с `getMe`.

### Этап C — Хостинг (аккаунты твои)
7. Доступ к **Vercel** (фронтенд) и **Render** (бэкенд + PostgreSQL).
   Claude даёт пошаговые инструкции — клики в дашбордах делаешь ты.
8. Желаемые имена сервисов (по умолчанию: `fitcontrol-api`, `fitcontrol-db`,
   Vercel-проект `fitcontrol`).
9. **Домены** — свои кастомные или дефолтные (`*.vercel.app` / `*.onrender.com`).

### Что Claude сгенерирует сам
- `TELEGRAM_WEBHOOK_SECRET` (длинная случайная строка).
- Все конфиги, миграции, тесты — уже в репозитории.

---

## Порядок действий (Claude ведёт, ты кликаешь)

Полные детали — в [`DEPLOYMENT.md`](DEPLOYMENT.md). Кратко:

1. **PostgreSQL (Render):** создать **пустую** БД → скопировать Internal URL.
2. **Backend (Render, Docker, ветка проекта):**
   - Root Directory `backend`, Health Check `/health`, Docker Command пусто.
   - Переменные: `ENVIRONMENT=production`, `DATABASE_URL`, `TELEGRAM_BOT_TOKEN`,
     `WEBAPP_URL`, `CORS_ORIGINS`, `DEV_AUTH_MODE=false`,
     `TELEGRAM_UPDATE_MODE=webhook`, `TELEGRAM_WEBHOOK_SECRET`, `PUBLIC_API_URL`,
     `DEFAULT_TIMEZONE`.
   - Дождаться Live → проверить `<api>/health`.
3. **Frontend (Vercel):** Root Directory `miniapp`, framework Vite. `vercel.json`
   уже проксирует `/api/*` на бэкенд, поэтому `VITE_API_BASE` можно не задавать.
4. **Вебхук Telegram:**
   `https://api.telegram.org/bot<ТОКЕН>/setWebhook?url=<api>/api/v1/telegram/webhook&secret_token=<секрет>`
   → проверить `getWebhookInfo` (поле `url` заполнено).
5. **BotFather:** `/setmenubutton` → URL = адрес Vercel.
6. **(Опц.) роль поддержки:** `python -m app.manage grant-admin <telegram_id>`.

---

## Критичные грабли (проверить обязательно — на этом мы теряли время)

| Симптом | Причина | Что сделать |
|---------|---------|-------------|
| `No open ports detected` (Render) | сервис слушал не `$PORT` | уже исправлено: uvicorn на `${PORT:-8000}` |
| `requires an async driver` | `DATABASE_URL` без `+asyncpg` | код сам нормализует; вставляй Render-URL как есть |
| `relation "users" already exists` | БД **не пустая** | использовать чистую БД (`DROP SCHEMA public CASCADE; CREATE SCHEMA public;`) |
| Mini App: `Unexpected token '<'` | фронт бьёт мимо `/api` (пустой `VITE_API_BASE`) | уже исправлено: fallback на `/api/v1` + прокси Vercel |
| `initData signature mismatch` | алгоритм/токен | уже исправлено (исключаем только `hash`, `strip()` токена). Если снова — токен в Render должен быть **того же бота** (сверить `getMe` → `username`) |
| Вебхук «молчит» | `url` пустой в `getWebhookInfo` | реально выполнить `setWebhook`, затем проверить `getWebhookInfo` |
| Секрет не совпал (403) | путаница KEY/VALUE | KEY = `TELEGRAM_WEBHOOK_SECRET` (имя), VALUE = сам секрет; он же в `setWebhook` |
| Видно старую версию Mini App | кэш Telegram | Clear Cache (Desktop) или тест на телефоне |

---

## Три слоя при отладке «бот не работает»
1. **Бот отвечает?** → `getWebhookInfo` (`url` + `last_error_message`) + логи Render (`POST …/telegram/webhook`).
2. **Фронт достаёт API?** → `<vercel>/api/v1/openapi.json` должен вернуть JSON; в DevTools Network запрос идёт на `/api/v1/...`.
3. **initData валидна?** → `signature mismatch` = токен/алгоритм; HTML-ошибка = api base/прокси.

---

## Что уже готово в репозитории (не надо писать заново)
- Backend: FastAPI + SQLAlchemy async + Alembic, RBAC, tenant-изоляция, финансы,
  посещения, отчёты, уведомления, восстановление доступа. Тесты (pytest) зелёные.
- Bot: aiogram 3 (webhook + polling), команды `/start /help /report /debtors /ending`.
- Mini App: React + TS + Vite, i18n ru/uz, все экраны.
- Инфраструктура: `render.yaml`, `miniapp/vercel.json`, `docker-compose.yml`,
  `.env.example`, миграции, `app/manage.py`, `app/seed.py`.
- Документация: `README.md`, `DEPLOYMENT.md`, `BACKUP.md`, этот файл.
