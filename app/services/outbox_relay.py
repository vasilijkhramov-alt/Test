from __future__ import annotations

import asyncio
from contextlib import suppress

from faststream.rabbit import RabbitBroker
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.messaging.topology import PAYMENTS_EXCHANGE_NAME
from app.models.base import utcnow
from app.models.enums import OutboxStatus
from app.models.outbox import OutboxEvent


class OutboxRelay:
    def __init__(
        self,
        *,
        broker: RabbitBroker,
        session_factory: async_sessionmaker,
        settings: Settings,
    ) -> None:
        self._broker = broker
        self._session_factory = session_factory
        self._settings = settings
        self._stop_event = asyncio.Event()

    async def run(self) -> None:
        while not self._stop_event.is_set():
            dispatched = await self._dispatch_batch()
            if dispatched:
                continue

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._settings.outbox_poll_interval_seconds,
                )
            except TimeoutError:
                continue

    async def stop(self) -> None:
        self._stop_event.set()

    async def _dispatch_batch(self) -> int:
        async with self._session_factory() as session:
            result = await session.execute(
                select(OutboxEvent)
                .where(OutboxEvent.status == OutboxStatus.PENDING)
                .where(OutboxEvent.available_at <= utcnow())
                .order_by(OutboxEvent.created_at)
                .limit(self._settings.outbox_batch_size)
                .with_for_update(skip_locked=True)
            )
            events = list(result.scalars())

            if not events:
                return 0

            for event in events:
                try:
                    await self._broker.publish(
                        event.payload,
                        exchange=PAYMENTS_EXCHANGE_NAME,
                        routing_key=event.routing_key,
                        persist=True,
                        message_id=str(event.id),
                        timestamp=utcnow(),
                        content_type="application/json",
                        message_type=event.event_type,
                    )
                    event.status = OutboxStatus.PUBLISHED
                    event.published_at = utcnow()
                    event.last_error = None
                except Exception as exc:
                    event.attempts += 1
                    event.last_error = str(exc)

            await session.commit()
            return len(events)


async def stop_task(task: asyncio.Task[None]) -> None:
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
