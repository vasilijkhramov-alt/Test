from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from faststream.rabbit import RabbitBroker

from app.api.deps import require_api_key
from app.api.routes.payments import router as payments_router
from app.config import get_settings
from app.db import SessionFactory
from app.messaging.topology import declare_topology
from app.services.outbox_relay import OutboxRelay, stop_task

settings = get_settings()
logging.basicConfig(level=settings.log_level)

broker = RabbitBroker(settings.rabbitmq_url)
relay = OutboxRelay(
    broker=broker,
    session_factory=SessionFactory,
    settings=settings,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await broker.connect()
    await declare_topology(broker, settings)

    relay_task = asyncio.create_task(relay.run())
    try:
        yield
    finally:
        await relay.stop()
        await stop_task(relay_task)
        await broker.close()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(payments_router)


@app.get("/health", tags=["service"], dependencies=[Depends(require_api_key)])
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
