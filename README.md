# FitControl

**SaaS для автоматизации фитнес-клубов.** Точка входа и канал уведомлений —
Telegram-бот; основная админ-панель — Telegram Mini App. Backend на FastAPI,
PostgreSQL, изоляция данных по клубам, финансовый журнал с аудитом.

> MVP. Реализованы: аутентификация через Telegram initData, мультиклубность с
> серверной изоляцией, RBAC, клиенты, тарифы, абонементы (заморозка/продление),
> платежи с частичной оплатой и идемпотентностью, возвраты/сторно с аудитом,
> посещаемость с проверкой абонемента, дашборд и отчёты, фоновые уведомления,
> Mini App (ru/uz).

---

## Содержание
- [Архитектура](#архитектура)
- [Роли и доступ](#роли-и-доступ)
- [Ключевые решения](#ключевые-решения)
- [Быстрый старт (Docker)](#быстрый-старт-docker)
- [Локальный запуск без Docker](#локальный-запуск-без-docker)
- [Продакшн-деплой (Vercel + Render)](#продакшн-деплой-vercel--render)
- [Восстановление доступа](#восстановление-доступа)
- [Настройка Telegram-бота и Mini App](#настройка-telegram-бота-и-mini-app)
- [Переменные окружения](#переменные-окружения)
- [API](#api)
- [Тесты](#тесты)
- [Резервное копирование](#резервное-копирование)
- [Ограничения MVP и следующие этапы](#ограничения-mvp-и-следующие-этапы)

---

## Архитектура

```
                    ┌─────────────────────┐
   Telegram  ─────▶ │  Bot (aiogram 3)    │  /start, /report, /debtors …
                    │  Scheduler          │  напоминания, ежедневная сводка
                    └─────────┬───────────┘
                              │ (общие модели/БД)
   Telegram  ─────▶ ┌─────────▼───────────┐        ┌──────────────┐
   Mini App  ─initData─▶ │ FastAPI backend  │──────▶ │ PostgreSQL   │
   (React/TS/Vite)   │  REST + OpenAPI     │  async │  SQLAlchemy 2│
                    └─────────────────────┘        │  + Alembic   │
                                                    └──────────────┘
```

- **backend/** — FastAPI API, aiogram-бот, планировщик уведомлений, модели,
  сервисы (бизнес-логика), миграции Alembic, тесты Pytest.
- **miniapp/** — React + TypeScript + Vite, мобильный-first UI, i18n (ru/uz).
- **docker-compose.yml** — `db`, `api`, `bot`, `scheduler`, `miniapp`.

Слои backend: `api/` (роутеры + зависимости авторизации) → `services/`
(бизнес-логика, транзакции) → `models/` (SQLAlchemy). Все запросы фильтруются
по `club_id`, взятому из проверенного членства, — изоляция проверяется на
сервере.

## Роли и доступ

| Роль | Права (в рамках клуба) |
|------|------------------------|
| `platform_admin` | системный доступ (кросс-клубный флаг на пользователе) |
| `club_owner` | всё в своём клубе + настройки + управление сотрудниками |
| `club_admin` | клиенты, тарифы, абонементы, платежи, приглашения |
| `trainer` | чтение и отметка посещений (минимальные права) |

Проверка ролей — серверная, на каждом защищённом endpoint (`RequireRole`).
Скрытие кнопок в UI — только дополнение, не граница безопасности.

## Ключевые решения

- **Деньги** хранятся как **целые UZS (сумы)**, без `float`. У сума нет
  используемой дробной части (тийин практически не в обороте), целочисленная
  арифметика точна. Единый масштаб задан в `app/core/money.py`; при
  необходимости суб-единиц меняется одна константа и тип колонки одной миграцией.
- **Финансовый журнал append-only.** `Charge` (начисление), `Payment` (оплата),
  `FinancialAdjustment` (скидка/сторно/коррекция). Платежи не удаляются;
  исправление — сторно/возврат отдельной записью с автором, временем и причиной.
- **Долг** = `max(0, начислено − оплачено(не сторнированное) − скидки + коррекции)`.
  Будущие/неоплаченные продажи не считаются полученной выручкой (доход
  признаётся по фактическим платежам). Дашборд показывает поступления и долги
  раздельно.
- **Идемпотентность оплат** — заголовок `Idempotency-Key`, уникальный в рамках
  клуба; повторный запрос возвращает существующий платёж (HTTP 200 вместо 201).
- **Аудит** финансовых и административных действий — таблица `audit_logs`
  (без секретов и полных платёжных данных).
- **initData** валидируется по официальному алгоритму (HMAC-SHA256 с ключом
  `WebAppData`) + проверка свежести `auth_date`. `user_id` от клиента не в доверии.
- **Календарь абонементов**: `days` — включительно от даты старта
  (`start + value − 1`); `months` — прибавление календарных месяцев через
  `relativedelta` минус один день (окончание месяца корректно «прижимается»).
  Заморозка продлевает `end_date` на число замороженных дней. Подробности —
  докстринг `app/services/dates.py`.

## Быстрый старт (Docker)

Требуется Docker + Docker Compose.

```bash
git clone <repo> fitcontrol && cd fitcontrol
cp .env.example .env
# отредактируйте .env: TELEGRAM_BOT_TOKEN, WEBAPP_URL (см. ниже)

docker compose up --build
```

Что поднимется:
- API — http://localhost:8000 (Swagger: http://localhost:8000/api/v1/docs,
  health: http://localhost:8000/health)
- Mini App — http://localhost:5173
- Bot и Scheduler — фоновые сервисы

Миграции применяются автоматически при старте `api`. Загрузить демо-данные
(только для development):

```bash
docker compose run --rm api seed
```

Демо-владелец: Telegram ID `999000001`. Для входа без Telegram выставьте в `.env`
`DEV_AUTH_MODE=true` и `VITE_DEV_TELEGRAM_ID=999000001`, затем пересоберите
`miniapp` (`docker compose up --build miniapp`).

## Локальный запуск без Docker

**Backend** (Python 3.11+; в контейнере — 3.12):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# нужна работающая PostgreSQL; задайте DATABASE_URL
export DATABASE_URL="postgresql+asyncpg://fitcontrol:fitcontrol@localhost:5432/fitcontrol"
export TELEGRAM_BOT_TOKEN="<токен>"
export DEV_AUTH_MODE=true          # только для локальной разработки

alembic upgrade head               # миграции
python -m app.seed                 # (опц.) демо-данные
uvicorn app.main:app --reload      # API на :8000
```

Бот и планировщик:
```bash
python -m app.bot.main             # Telegram-бот (long polling)
python -m app.bot.notifications    # планировщик уведомлений (цикл 60с)
```

**Mini App**:
```bash
cd miniapp
npm install
# dev-режим проксирует /api на http://localhost:8000
VITE_DEV_TELEGRAM_ID=999000001 npm run dev   # http://localhost:5173
npm run build                                 # прод-сборка в dist/
npm run typecheck                             # проверка типов
```

## Продакшн-деплой (Vercel + Render)

Полное пошаговое руководство — [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).
Кратко:

- **Frontend (Mini App)** → **Vercel**. Root Directory `miniapp`, framework Vite
  (`vercel.json` настраивает SPA-rewrite). Единственная переменная —
  `VITE_API_BASE=https://<render-api>/api/v1`. Секретов backend и токена бота во
  фронтенде **нет**.
- **Backend** → **Render** по блюпринту [`render.yaml`](render.yaml): Web Service
  (FastAPI, health-check `/health`) + Background Worker бота + Background Worker
  планировщика. Фоновые задачи и уведомления не зависят от открытого браузера.
- **PostgreSQL** → управляемая Render Postgres (данные не в локальной ФС сервиса;
  `DATABASE_URL` через переменные окружения; миграции Alembic применяются на
  старте API).
- **Telegram updates** → **основной способ — long polling** в Background Worker
  (`TELEGRAM_UPDATE_MODE=polling`). Альтернатива — webhook в API
  (`TELEGRAM_UPDATE_MODE=webhook` + `TELEGRAM_WEBHOOK_SECRET` + `PUBLIC_API_URL`,
  регистрация `python -m app.manage set-webhook`). Способ описан в DEPLOYMENT.
- **Домены и HTTPS**, полный список переменных окружения, а также **аварийное
  восстановление** (перезапуск/rollback Render, восстановление БД из бэкапа) —
  в DEPLOYMENT.

## Восстановление доступа

Данные клуба привязаны к `club_id`, а не к Telegram-аккаунту — **потеря
Telegram не удаляет клуб и его данные**. Telegram ID не является единственным
фактором восстановления: у клуба есть внешние контакты `recovery_email` /
`recovery_phone` (Настройки), которые поддержка проверяет перед восстановлением.

Восстановление выполняет роль поддержки `platform_admin` (назначается только
на сервере):

```bash
python -m app.manage grant-admin <telegram_id_поддержки>
python -m app.manage list-admins
```

Эндпоинты (только `platform_admin`, требуют `reason`, всё пишется в `AuditLog`):
- `POST /api/v1/support/clubs/{club_id}/grant-access` — выдать/восстановить
  доступ новому Telegram-аккаунту с сохранением `club_id` и всех данных;
- `POST /api/v1/support/recovery/change-telegram-id` — сменить Telegram ID
  существующего пользователя, сохранив все членства (и club_id).

Подробности и процедура проверки — в [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md#9-account-recovery-lost-telegram-account).

## Настройка Telegram-бота и Mini App

1. **Создать бота**: напишите [@BotFather](https://t.me/BotFather) → `/newbot`,
   получите **токен** → в `.env` `TELEGRAM_BOT_TOKEN=...`.
2. **HTTPS URL для Mini App** (Telegram требует https). Для теста поднимите
   туннель к Mini App (порт 5173):
   - `cloudflared tunnel --url http://localhost:5173` → получите
     `https://<...>.trycloudflare.com`, или
   - `ngrok http 5173`.
   Пропишите этот адрес в `.env` `WEBAPP_URL=https://<...>` и пересоберите
   backend/бот (бот берёт URL для кнопки WebApp).
3. **Привязать Web App в BotFather** (для кнопки-меню): `/newapp` или
   `/setmenubutton` → выберите бота → укажите тот же HTTPS URL.
4. Откройте бота, нажмите **/start** → кнопка «Открыть FitControl».

> В продакшене Mini App и API обслуживаются по HTTPS, `DEV_AUTH_MODE=false`,
> `CORS_ORIGINS` ограничен origin'ом Mini App.

## Переменные окружения

См. `.env.example` (полный список с комментариями). Кратко:

| Переменная | Назначение |
|-----------|-----------|
| `ENVIRONMENT` | `development` / `production` (в prod DEV_AUTH_MODE выключен принудительно) |
| `DATABASE_URL` | async-URL PostgreSQL (`postgresql+asyncpg://…`) |
| `TELEGRAM_BOT_TOKEN` | токен бота из BotFather (нужен боту и валидации initData) |
| `WEBAPP_URL` | публичный HTTPS-адрес Mini App (кнопка WebApp) |
| `INITDATA_MAX_AGE_SECONDS` | макс. возраст initData (по умолчанию 86400) |
| `DEV_AUTH_MODE` | dev-обход авторизации через `X-Dev-Telegram-Id` (по умолч. false) |
| `CORS_ORIGINS` | список origin'ов через запятую (`*` только для dev) |
| `DEFAULT_TIMEZONE` | таймзона по умолчанию для сводок (`Asia/Tashkent`) |
| `DAILY_SUMMARY_HOUR` | час (0–23, локальный клубу) ежедневной сводки |
| `EXPIRY_REMINDER_DAYS` | за сколько дней напоминать об окончании |
| `VITE_API_BASE` | базовый URL API для прод-сборки Mini App |
| `VITE_DEV_TELEGRAM_ID` | dev: под каким Telegram ID заходить вне Telegram |

Секреты — только через окружение/`.env`; `.env` в `.gitignore`.

## API

OpenAPI/Swagger: `GET /api/v1/docs`. Единый формат ошибок:
`{"error": {"code": "...", "message": "...", "details": {...}}}`.

Аутентификация: заголовок `X-Init-Data: <initData>` (или
`Authorization: tma <initData>`). Активный клуб — заголовок `X-Club-Id`.

Группы: `/auth/telegram` (через `/auth/me`), `/clubs`, `/clubs/current`,
`/dashboard`, `/clients`, `/plans`, `/subscriptions`, `/payments`, `/debts`,
`/visits`, `/staff/invites`, `/staff`, `/reports`, `/settings`, `/support`
(восстановление доступа, только platform_admin). Health — `GET /health`.
Telegram webhook (только в режиме webhook) — `POST /api/v1/telegram/webhook`.

## Тесты

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

Тесты используют изолированную SQLite (никогда не подключаются к продакшену) и
покрывают: валидацию initData (валидный/подпись/просрочка), изоляцию двух
клубов, RBAC (owner/admin/trainer), частичную оплату и расчёт долга,
сторно/возврат + аудит, истёкший абонемент и посещение (с исключением),
идемпотентность оплаты, endpoints клиентов и тарифов, дедупликацию уведомлений.

## Резервное копирование

См. [`docs/BACKUP.md`](docs/BACKUP.md) — `pg_dump`/`pg_restore`, расписание,
ротация.

## Ограничения MVP и следующие этапы

Реализовано и **фактически проверено** в этом окружении: сборка backend
(импорт приложения, boot через uvicorn, реальные HTTP-запросы), миграции
Alembic (up/down, `alembic check` без дрейфа), полный прогон Pytest (backend,
включая RBAC, изоляцию, финансы, восстановление доступа и проверку секрета
webhook), typecheck и прод-сборка Mini App, management-CLI. **Не** запускалось
здесь: полный `docker compose up` и деплой на Vercel/Render (нет доступа к
вашим аккаунтам — используйте `docs/DEPLOYMENT.md`), реальная доставка
сообщений в Telegram и регистрация webhook (нужен токен и публичные URL).

Осознанно вне рамок MVP / следующие этапы:
- QR-регистрация посещений (заложено как расширение; безопасная реализация —
  отдельный этап).
- Клиентские уведомления (сейчас — только сотрудникам; требуют явного согласия
  и настройки).
- Продвинутая кассовая сверка/смены (сейчас — базовая сводка по способам оплаты).
- Онлайн-платежи/эквайринг (внешние провайдеры) — через адаптер, здесь-заглушка.
- Роль тренера расширить (расписания, персональные тренировки).
- Ролевые ограничения по частоте запросов (rate limiting) на чувствительных
  endpoint'ах — заложить на уровне API-gateway/прокси в проде.
- Редактирование/деактивация тарифов и продление абонемента из UI (API готов).

---

### Лицензия / авторство
Учебный/стартовый проект FitControl.
