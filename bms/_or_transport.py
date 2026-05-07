"""
Internal async REST client for OpenRemote with token caching.
No dependency on the gateway — talks directly to OR over HTTPS.
"""

from __future__ import annotations

import logging
import time

import httpx

log = logging.getLogger(__name__)


class ORTransport:
    def __init__(
        self,
        base_url: str,
        realm: str,
        username: str,
        password: str,
    ) -> None:
        self._base_url  = base_url
        self._realm     = realm
        self._username  = username
        self._password  = password
        # verify=False — self-signed cert on localhost
        self._http = httpx.AsyncClient(verify=False, base_url=base_url)
        self._token     = ""
        self._expires   = 0.0

    # ── Auth ──────────────────────────────────────────────────────────────────

    async def _get_token(self) -> str:
        if self._token and time.time() < self._expires:
            return self._token
        resp = await self._http.post(
            f"/auth/realms/{self._realm}/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id":  "openremote",
                "username":   self._username,
                "password":   self._password,
            },
        )
        resp.raise_for_status()
        body = resp.json()
        self._token   = body["access_token"]
        self._expires = time.time() + body["expires_in"] - 30
        log.debug("Token refreshed")
        return self._token

    async def _hdrs(self) -> dict:
        return {
            "Authorization": f"Bearer {await self._get_token()}",
            "Content-Type":  "application/json",
        }

    # ── Asset operations ──────────────────────────────────────────────────────

    async def get_assets(self) -> list[dict]:
        resp = await self._http.post(
            f"/api/{self._realm}/asset/query",
            json={},
            headers=await self._hdrs(),
        )
        resp.raise_for_status()
        return resp.json()

    async def get_asset(self, asset_id: str) -> dict | None:
        resp = await self._http.get(
            f"/api/{self._realm}/asset/{asset_id}",
            headers=await self._hdrs(),
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    async def write_attribute(self, asset_id: str, attr_name: str, value: object) -> None:
        """GET → patch one attribute → PUT back."""
        import time as _t
        now = int(_t.time() * 1000)
        asset = await self.get_asset(asset_id)
        if asset and attr_name in asset.get("attributes", {}):
            asset["attributes"][attr_name]["value"] = value
            asset["attributes"][attr_name]["timestamp"] = now
            resp = await self._http.put(
                f"/api/{self._realm}/asset/{asset_id}",
                json=asset,
                headers=await self._hdrs(),
            )
            resp.raise_for_status()

    async def write_attributes(self, events: list[dict]) -> None:
        """Batch-write: group by asset, one GET+PUT per asset.

        events: list of {"id": assetId, "name": attrName, "value": any}
        """
        import time as _t
        now = int(_t.time() * 1000)
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
            resp = await self._http.put(
                f"/api/{self._realm}/asset/{asset_id}",
                json=asset,
                headers=await self._hdrs(),
            )
            resp.raise_for_status()

    async def close(self) -> None:
        await self._http.aclose()
