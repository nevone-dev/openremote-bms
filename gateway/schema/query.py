from typing import Optional

import strawberry

from gateway.or_client import ORClient
from .types import Asset, Attribute, Dashboard, DashboardTemplate, DashboardWidget, GridItem


def _map_asset(raw: dict) -> Asset:
    attrs = [
        Attribute(
            name=name,
            type=a.get("type", ""),
            value=a.get("value"),
            timestamp=a.get("timestamp"),
        )
        for name, a in raw.get("attributes", {}).items()
    ]
    return Asset(
        id=strawberry.ID(raw["id"]),
        name=raw["name"],
        type=raw["type"],
        parent_id=strawberry.ID(raw["parentId"]) if raw.get("parentId") else None,
        attributes=attrs,
    )


def _map_dashboard(raw: dict) -> Dashboard:
    tmpl = raw.get("template", {})
    widgets = [
        DashboardWidget(
            id=w["id"],
            display_name=w.get("displayName", ""),
            widget_type_id=w.get("widgetTypeId", ""),
            grid_item=GridItem(
                x=w["gridItem"]["x"],
                y=w["gridItem"]["y"],
                w=w["gridItem"]["w"],
                h=w["gridItem"]["h"],
                min_h=w["gridItem"].get("minH", 2),
                min_w=w["gridItem"].get("minW", 2),
                no_resize=w["gridItem"].get("noResize", False),
                no_move=w["gridItem"].get("noMove", False),
                locked=w["gridItem"].get("locked", False),
            ),
            widget_config=w.get("widgetConfig"),
        )
        for w in tmpl.get("widgets", [])
    ]
    return Dashboard(
        id=strawberry.ID(raw["id"]),
        display_name=raw.get("displayName", ""),
        realm=raw.get("realm", ""),
        access=raw.get("access", "SHARED"),
        version=raw.get("version", 0),
        template=DashboardTemplate(
            columns=tmpl.get("columns", 12),
            max_screen_width=tmpl.get("maxScreenWidth", 1920),
            refresh_interval=tmpl.get("refreshInterval", "FIVE_MIN"),
            widgets=widgets,
        ),
    )


@strawberry.type
class Query:
    @strawberry.field
    async def assets(self, info: strawberry.types.Info) -> list[Asset]:
        client: ORClient = info.context["or_client"]
        return [_map_asset(a) for a in await client.get_assets()]

    @strawberry.field
    async def asset(self, info: strawberry.types.Info, id: strawberry.ID) -> Optional[Asset]:
        client: ORClient = info.context["or_client"]
        raw = await client.get_asset(str(id))
        return _map_asset(raw) if raw else None

    @strawberry.field
    async def dashboards(self, info: strawberry.types.Info) -> list[Dashboard]:
        client: ORClient = info.context["or_client"]
        return [_map_dashboard(d) for d in await client.get_dashboards()]

    @strawberry.field
    async def dashboard(self, info: strawberry.types.Info, id: strawberry.ID) -> Optional[Dashboard]:
        client: ORClient = info.context["or_client"]
        raw = await client.get_dashboard(str(id))
        return _map_dashboard(raw) if raw else None
