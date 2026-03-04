"""FastAPI application factory."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from .config import settings
from .database import init_db
from .voice_handler import router as voice_router
from .dashboard import router as dashboard_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info(f"Starting {settings.app_name}")
    init_db()
    yield
    logger.info("Shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        description="AI receptionist that answers calls and books appointments.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # tighten in production
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(voice_router)
    app.include_router(dashboard_router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "app": settings.app_name}

    return app
