"""Entry point — FastAPI app factory + lifecycle."""
import asyncio
import logging

import asyncpg
import redis.asyncio as aioredis
from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings
from app.worker.queue import worker_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agentic Kirana Worker",
        version="2.0.0",
        docs_url="/docs" if settings.ENV != "production" else None,
        redoc_url=None,
    )
    app.include_router(router)

    @app.on_event("startup")
    async def startup() -> None:
        app.state.pg_pool = await asyncpg.create_pool(
            settings.DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        app.state.redis_client = await aioredis.from_url(settings.REDIS_URL)
        asyncio.create_task(worker_loop(app.state.pg_pool, app.state.redis_client))
        logger.info("Startup complete — worker listening")

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await app.state.pg_pool.close()
        await app.state.redis_client.close()
        logger.info("Shutdown complete")

    return app


app = create_app()
