import asyncio
import logging
import time

import httpx

from .config import settings

log = logging.getLogger(__name__)


class TokenClient:
    def __init__(self) -> None:
        self._token: str = ""
        self._expires_at: float = 0.0
        # verify=False mirrors the rest of the stack (self-signed cert)
        self._http = httpx.AsyncClient(verify=False)

    async def get_token(self) -> str:
        if self._token and time.time() < self._expires_at:
            return self._token
        await self._fetch()
        return self._token

    async def _fetch(self) -> None:
        resp = await self._http.post(
            f"{settings.or_base_url}/auth/realms/{settings.or_realm}"
            "/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "openremote",
                "username": settings.or_username,
                "password": settings.or_password,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._expires_at = time.time() + data["expires_in"] - settings.token_refresh_margin
        log.debug("Token refreshed, expires in %ds", data["expires_in"])

    async def refresh_loop(self) -> None:
        """Background task: keeps the cached token alive."""
        while True:
            try:
                await self._fetch()
                sleep_for = max(5.0, self._expires_at - time.time())
                await asyncio.sleep(sleep_for)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.warning("Token refresh failed: %s — retrying in 10 s", exc)
                await asyncio.sleep(10)

    async def close(self) -> None:
        await self._http.aclose()
