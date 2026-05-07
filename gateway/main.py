import asyncio
import logging
from contextlib import asynccontextmanager

import strawberry
from fastapi import FastAPI, Request
from strawberry.fastapi import GraphQLRouter

from .auth import TokenClient
from .config import settings
from .mqtt_bridge import MQTTBridge
from .or_client import ORClient
from .schema.mutation import Mutation
from .schema.query import Query
from .schema.subscription import Subscription

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    auth = TokenClient()
    or_client = ORClient(auth)
    bridge = MQTTBridge()

    app.state.auth = auth
    app.state.or_client = or_client
    app.state.bridge = bridge

    auth_task = asyncio.create_task(auth.refresh_loop(), name="token-refresh")
    bridge_task = asyncio.create_task(bridge.run(), name="mqtt-bridge")
    log.info("Gateway started — realm=%s  OR=%s", settings.or_realm, settings.or_base_url)

    yield

    auth_task.cancel()
    bridge_task.cancel()
    await asyncio.gather(auth_task, bridge_task, return_exceptions=True)
    await or_client.close()
    await auth.close()
    log.info("Gateway stopped")


async def get_context(request: Request) -> dict:
    return {
        "or_client": request.app.state.or_client,
        "mqtt_bridge": request.app.state.bridge,
        "realm": settings.or_realm,
    }


schema = strawberry.Schema(query=Query, mutation=Mutation, subscription=Subscription)
graphql_router = GraphQLRouter(schema, context_getter=get_context)

app = FastAPI(title="OpenRemote Gateway", lifespan=lifespan)
app.include_router(graphql_router, prefix="/graphql")


@app.get("/health")
async def health():
    return {"status": "ok", "realm": settings.or_realm, "or_url": settings.or_base_url}
