import asyncio
import json
import logging
import ssl
import time
from dataclasses import dataclass
from typing import Optional

from .config import settings

log = logging.getLogger(__name__)


@dataclass
class AttributeEvent:
    asset_id: str
    attribute_name: str
    value: object
    timestamp: float  # unix ms


class MQTTBridge:
    """Connects to the OpenRemote MQTT broker, receives attribute change events,
    and fans them out to any number of async queue subscribers (GraphQL
    subscriptions).

    OR MQTT topic layout (subscribe):
        {realm}/{clientId}/attributevalue/{attributeName}/{assetId}

    OR MQTT topic layout (write):
        {realm}/{clientId}/writeattributevalue/{attributeName}/{assetId}
    """

    def __init__(self) -> None:
        self._queues: list[asyncio.Queue] = []

    # ── Subscription management ───────────────────────────────────────────────

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=512)
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._queues.remove(q)
        except ValueError:
            pass

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _broadcast(self, event: AttributeEvent) -> None:
        for q in list(self._queues):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # slow subscriber — drop oldest rather than block

    @staticmethod
    def _parse(topic: str, raw: bytes) -> Optional[AttributeEvent]:
        # Expected: {realm}/{clientId}/attributevalue/{attrName}/{assetId}
        parts = topic.split("/")
        if len(parts) != 5 or parts[2] != "attributevalue":
            return None
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            value = raw.decode("utf-8", errors="replace")
        return AttributeEvent(
            asset_id=parts[4],
            attribute_name=parts[3],
            value=value,
            timestamp=time.time() * 1000,
        )

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        import aiomqtt  # deferred so missing dep doesn't break import at startup

        tls_ctx: Optional[ssl.SSLContext] = None
        if settings.mqtt_use_tls:
            tls_ctx = ssl.create_default_context()
            tls_ctx.check_hostname = False
            tls_ctx.verify_mode = ssl.CERT_NONE

        username = settings.mqtt_username or settings.or_username
        password = settings.mqtt_password or settings.or_password
        # Subscribe wildcard: all attribute changes forwarded to our clientId
        sub_topic = f"{settings.or_realm}/{settings.mqtt_client_id}/attributevalue/#"

        while True:
            try:
                async with aiomqtt.Client(
                    hostname=settings.mqtt_host,
                    port=settings.mqtt_port,
                    username=username,
                    password=password,
                    identifier=settings.mqtt_client_id,
                    tls_context=tls_ctx,
                ) as client:
                    await client.subscribe(sub_topic)
                    log.info("MQTT bridge connected → subscribed to %s", sub_topic)
                    async for message in client.messages:
                        event = self._parse(str(message.topic), message.payload)
                        if event:
                            await self._broadcast(event)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.warning("MQTT bridge error (%s) — reconnecting in 5 s", exc)
                await asyncio.sleep(5)
