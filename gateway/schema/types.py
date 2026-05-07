from typing import Any, NewType, Optional
import strawberry

# JSON scalar: passes values through as-is (no serialisation needed)
JSON = strawberry.scalar(
    NewType("JSON", Any),
    name="JSON",
    description="Arbitrary JSON value (object, array, string, number, boolean, null)",
    serialize=lambda v: v,
    parse_value=lambda v: v,
)


@strawberry.type
class Attribute:
    name: str
    type: str
    value: Optional[JSON] = None
    timestamp: Optional[float] = None


@strawberry.type
class Asset:
    id: strawberry.ID
    name: str
    type: str
    parent_id: Optional[strawberry.ID] = None
    attributes: list[Attribute] = strawberry.field(default_factory=list)


@strawberry.type
class AttributeChangeEvent:
    asset_id: strawberry.ID
    attribute_name: str
    value: Optional[JSON]
    timestamp: float


# ── Dashboard types ───────────────────────────────────────────────────────────

@strawberry.type
class GridItem:
    x: int
    y: int
    w: int
    h: int
    min_h: int
    min_w: int
    no_resize: bool
    no_move: bool
    locked: bool


@strawberry.type
class DashboardWidget:
    id: str
    display_name: str
    widget_type_id: str
    grid_item: GridItem
    widget_config: Optional[JSON] = None


@strawberry.type
class DashboardTemplate:
    columns: int
    max_screen_width: int
    refresh_interval: str
    widgets: list[DashboardWidget]


@strawberry.type
class Dashboard:
    id: strawberry.ID
    display_name: str
    realm: str
    access: str
    version: int
    template: DashboardTemplate


# ── Dashboard input types ─────────────────────────────────────────────────────

@strawberry.input
class GridItemInput:
    x: int
    y: int
    w: int
    h: int
    min_h: int = 2
    min_w: int = 2
    no_resize: bool = False
    no_move: bool = False
    locked: bool = False


@strawberry.input
class DashboardWidgetInput:
    display_name: str
    widget_type_id: str
    grid_item: GridItemInput
    widget_config: Optional[JSON] = None
    id: Optional[str] = None


@strawberry.input
class CreateDashboardInput:
    display_name: str
    access: str = "SHARED"
    columns: int = 12
    max_screen_width: int = 1920
    refresh_interval: str = "FIVE_MIN"
    widgets: list[DashboardWidgetInput] = strawberry.field(default_factory=list)


@strawberry.input
class UpdateDashboardInput:
    id: strawberry.ID
    display_name: Optional[str] = None
    access: Optional[str] = None
    refresh_interval: Optional[str] = None
    widgets: Optional[list[DashboardWidgetInput]] = None
