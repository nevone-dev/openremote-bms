import time
from typing import Optional

import strawberry

from gateway.config import settings
from gateway.or_client import ORClient
from .query import _map_asset, _map_dashboard
from .types import Asset, Dashboard, JSON, CreateDashboardInput, UpdateDashboardInput


@strawberry.input
class AttributeEventInput:
    asset_id: strawberry.ID
    attribute_name: str
    value: JSON


@strawberry.input
class AssetAttributeInput:
    name: str
    type: str
    value: Optional[JSON] = None


@strawberry.input
class AssetInput:
    name: str
    type: str
    parent_id: Optional[strawberry.ID] = strawberry.UNSET
    attributes: list[AssetAttributeInput] = strawberry.field(default_factory=list)


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def write_attribute(
        self,
        info: strawberry.types.Info,
        asset_id: strawberry.ID,
        attribute: str,
        value: JSON,
    ) -> bool:
        client: ORClient = info.context["or_client"]
        await client.write_attribute(str(asset_id), attribute, value)
        return True

    @strawberry.mutation
    async def write_attributes(
        self,
        info: strawberry.types.Info,
        events: list[AttributeEventInput],
    ) -> bool:
        client: ORClient = info.context["or_client"]
        await client.write_attributes([
            {"id": str(e.asset_id), "name": e.attribute_name, "value": e.value}
            for e in events
        ])
        return True

    @strawberry.mutation
    async def create_asset(
        self,
        info: strawberry.types.Info,
        input: AssetInput,
    ) -> Asset:
        client: ORClient = info.context["or_client"]
        now = int(time.time() * 1000)
        payload: dict = {
            "name": input.name,
            "type": input.type,
            "realm": settings.or_realm,
        }
        if input.parent_id is not strawberry.UNSET and input.parent_id is not None:
            payload["parentId"] = str(input.parent_id)
        if input.attributes:
            payload["attributes"] = {
                a.name: {
                    "name": a.name,
                    "type": a.type,
                    "meta": {},
                    "value": a.value,
                    "timestamp": now,
                }
                for a in input.attributes
            }
        raw = await client.create_asset(payload)
        return _map_asset(raw)

    @strawberry.mutation
    async def create_dashboard(
        self,
        info: strawberry.types.Info,
        input: CreateDashboardInput,
    ) -> Dashboard:
        client: ORClient = info.context["or_client"]
        _wid = 0

        def _widget_payload(w) -> dict:
            nonlocal _wid
            _wid += 1
            return {
                "id": w.id or f"w{_wid}",
                "displayName": w.display_name,
                "widgetTypeId": w.widget_type_id,
                "gridItem": {
                    "x": w.grid_item.x,
                    "y": w.grid_item.y,
                    "w": w.grid_item.w,
                    "h": w.grid_item.h,
                    "minH": w.grid_item.min_h,
                    "minW": w.grid_item.min_w,
                    "noResize": w.grid_item.no_resize,
                    "noMove": w.grid_item.no_move,
                    "locked": w.grid_item.locked,
                },
                "widgetConfig": w.widget_config or {},
            }

        payload = {
            "realm": settings.or_realm,
            "displayName": input.display_name,
            "access": input.access,
            "template": {
                "columns": input.columns,
                "maxScreenWidth": input.max_screen_width,
                "refreshInterval": input.refresh_interval,
                "screenPresets": [
                    {"id": "default", "displayName": "Default", "breakpoint": 1920, "scalingPreset": "KEEP_LAYOUT"}
                ],
                "widgets": [_widget_payload(w) for w in input.widgets],
            },
        }
        raw = await client.create_dashboard(payload)
        return _map_dashboard(raw)

    @strawberry.mutation
    async def update_dashboard(
        self,
        info: strawberry.types.Info,
        input: UpdateDashboardInput,
    ) -> Dashboard:
        """Fetch current dashboard, apply partial updates, PUT back."""
        client: ORClient = info.context["or_client"]
        raw = await client.get_dashboard(str(input.id))
        if raw is None:
            raise ValueError(f"Dashboard {input.id} not found")

        if input.display_name is not None:
            raw["displayName"] = input.display_name
        if input.access is not None:
            raw["access"] = input.access
        if input.refresh_interval is not None:
            raw["template"]["refreshInterval"] = input.refresh_interval
        if input.widgets is not None:
            _wid = 0

            def _widget_payload(w) -> dict:
                nonlocal _wid
                _wid += 1
                return {
                    "id": w.id or f"w{_wid}",
                    "displayName": w.display_name,
                    "widgetTypeId": w.widget_type_id,
                    "gridItem": {
                        "x": w.grid_item.x,
                        "y": w.grid_item.y,
                        "w": w.grid_item.w,
                        "h": w.grid_item.h,
                        "minH": w.grid_item.min_h,
                        "minW": w.grid_item.min_w,
                        "noResize": w.grid_item.no_resize,
                        "noMove": w.grid_item.no_move,
                        "locked": w.grid_item.locked,
                    },
                    "widgetConfig": w.widget_config or {},
                }

            raw["template"]["widgets"] = [_widget_payload(w) for w in input.widgets]

        updated = await client.update_dashboard(raw)
        return _map_dashboard(updated)

    @strawberry.mutation
    async def delete_dashboard(
        self,
        info: strawberry.types.Info,
        id: strawberry.ID,
    ) -> bool:
        client: ORClient = info.context["or_client"]
        await client.delete_dashboard(str(id))
        return True
