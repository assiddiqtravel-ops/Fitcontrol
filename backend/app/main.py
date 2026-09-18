"""FastAPI application entrypoint."""
from __future__ import annotations

import logging

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.errors import register_error_handlers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fitcontrol")


def create_app() -> FastAPI:
    app = FastAPI(
        title="FitControl API",
        version="0.1.0",
        description="SaaS automation for fitness clubs — API, bot and Mini App backend.",
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url=f"{settings.api_v1_prefix}/docs",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    # --- Health check (unauthenticated) ---
    @app.get("/health", tags=["system"])
    async def health() -> dict:
        return {
            "status": "ok",
            "app": settings.app_name,
            "environment": settings.environment,
            "dev_auth": settings.effective_dev_auth(),
        }

    # --- API v1 ---
    from app.api.routers import (
        auth_clubs,
        clients_plans,
        dashboard,
        payments,
        subscriptions,
        support,
        visits,
    )

    api = APIRouter(prefix=settings.api_v1_prefix)
    api.include_router(auth_clubs.router)
    api.include_router(clients_plans.router)
    api.include_router(subscriptions.router)
    api.include_router(payments.router)
    api.include_router(visits.router)
    api.include_router(dashboard.router)
    api.include_router(support.router)

    # Telegram webhook (only active when TELEGRAM_UPDATE_MODE=webhook).
    from app.bot.webhook import router as webhook_router

    api.include_router(webhook_router)
    app.include_router(api)

    if settings.is_production and settings.dev_auth_mode:
        logger.warning(
            "DEV_AUTH_MODE is set but ignored because ENVIRONMENT=production."
        )

    logger.info("FitControl API initialized (env=%s)", settings.environment)
    return app


app = create_app()
