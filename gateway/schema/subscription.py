from typing import AsyncGenerator, Optional

import strawberry

from gateway.mqtt_bridge import AttributeEvent, MQTTBridge
from .types import AttributeChangeEvent, JSON


def _to_gql(e: AttributeEvent) -> AttributeChangeEvent:
    return AttributeChangeEvent(
        asset_id=strawberry.ID(e.asset_id),
        attribute_name=e.attribute_name,
        value=e.value,
        timestamp=e.timestamp,
    )


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def attribute_changed(
        self,
        info: strawberry.types.Info,
        asset_id: Optional[strawberry.ID] = None,
        attribute_name: Optional[str] = None,
    ) -> AsyncGenerator[AttributeChangeEvent, None]:
        """Stream live attribute change events from OpenRemote via MQTT.

        Both filters are optional — omit to receive all events.
        """
        bridge: MQTTBridge = info.context["mqtt_bridge"]
        queue = bridge.subscribe()
        try:
            while True:
                event: AttributeEvent = await queue.get()
                if asset_id is not None and event.asset_id != str(asset_id):
                    continue
                if attribute_name is not None and event.attribute_name != attribute_name:
                    continue
                yield _to_gql(event)
        finally:
            bridge.unsubscribe(queue)
