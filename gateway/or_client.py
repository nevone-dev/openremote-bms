import time

import httpx

from .auth import TokenClient
from .config import settings


class ORClient:
    def __init__(self, auth: TokenClient) -> None:
        self._auth = auth
        self._http = httpx.AsyncClient(verify=False, base_url=settings.or_base_url)

    async def _hdrs(self) -> dict:
        token = await self._auth.get_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # ── Asset CRUD ────────────────────────────────────────────────────────────

    async def get_assets(self) -> list[dict]:
        resp = await self._http.post(
            f"/api/{settings.or_realm}/asset/query",
            json={},
            headers=await self._hdrs(),
        )
        resp.raise_for_status()
        return resp.json()

    async def get_asset(self, asset_id: str) -> dict | None:
        resp = await self._http.get(
            f"/api/{settings.or_realm}/asset/{asset_id}",
            headers=await self._hdrs(),
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    async def create_asset(self, payload: dict) -> dict:
        resp = await self._http.post(
            f"/api/{settings.or_realm}/asset",
            json=payload,
            headers=await self._hdrs(),
        )
        resp.raise_for_status()
        return resp.json()

    async def update_asset(self, asset_id: str, payload: dict) -> dict:
        resp = await self._http.put(
            f"/api/{settings.or_realm}/asset/{asset_id}",
            json=payload,
            headers=await self._hdrs(),
        )
        resp.raise_for_status()
        return resp.json()

    # ── Attribute writes ──────────────────────────────────────────────────────

    async def write_attribute(self, asset_id: str, attr_name: str, value: object) -> None:
        """Write one attribute via GET → patch → PUT (only reliable path on this OR version)."""
        now = int(time.time() * 1000)
        asset = await self.get_asset(asset_id)
        if asset and attr_name in asset.get("attributes", {}):
            asset["attributes"][attr_name]["value"] = value
            asset["attributes"][attr_name]["timestamp"] = now
            await self.update_asset(asset_id, asset)

    async def write_attributes(self, events: list[dict]) -> None:
        """Batch-write attributes. Groups by asset to minimise round-trips.

        Each dict: {"id": assetId, "name": attrName, "value": any}
        """
        now = int(time.time() * 1000)
        # Group by asset id
        by_asset: dict[str, list[dict]] = {}
        for e in events:
            by_asset.setdefault(e["id"], []).append(e)

        for asset_id, asset_events in by_asset.items():
            asset = await self.get_asset(asset_id)
            if not asset:
                continue
            for e in asset_events:
                name = e["name"]
                if name in asset.get("attributes", {}):
                    asset["attributes"][name]["value"] = e["value"]
                    asset["attributes"][name]["timestamp"] = now
            await self.update_asset(asset_id, asset)

    # ── Dashboard CRUD ────────────────────────────────────────────────────────

    async def get_dashboards(self) -> list[dict]:
        resp = await self._http.get(
            f"/api/{settings.or_realm}/dashboard/all/{settings.or_realm}",
            headers=await self._hdrs(),
        )
        resp.raise_for_status()
        return resp.json()

    async def get_dashboard(self, dashboard_id: str) -> dict | None:
        resp = await self._http.get(
            f"/api/{settings.or_realm}/dashboard/{settings.or_realm}/{dashboard_id}",
            headers=await self._hdrs(),
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    async def create_dashboard(self, payload: dict) -> dict:
        resp = await self._http.post(
            f"/api/{settings.or_realm}/dashboard",
            json=payload,
            headers=await self._hdrs(),
        )
        resp.raise_for_status()
        return resp.json()

    async def update_dashboard(self, payload: dict) -> dict:
        """PUT /dashboard — ID must be present inside payload."""
        resp = await self._http.put(
            f"/api/{settings.or_realm}/dashboard",
            json=payload,
            headers=await self._hdrs(),
        )
        resp.raise_for_status()
        return resp.json()

    async def delete_dashboard(self, dashboard_id: str) -> None:
        resp = await self._http.delete(
            f"/api/{settings.or_realm}/dashboard/{settings.or_realm}/{dashboard_id}",
            headers=await self._hdrs(),
        )
        resp.raise_for_status()

    async def close(self) -> None:
        await self._http.aclose()
