"""Marzban API client."""

import logging
from datetime import datetime

import httpx

from src.utils.config import settings

logger = logging.getLogger(__name__)


class MarzbanClient:
    def __init__(self) -> None:
        self.base_url = f"{settings.marzban_address}/api"
        self._token: str | None = None
        self._client = httpx.AsyncClient(timeout=15.0)

    async def _get_token(self) -> str:
        if self._token is not None:
            return self._token
        return await self._refresh_token()

    async def _refresh_token(self) -> str:
        resp = await self._client.post(
            f"{self.base_url}/admin/token",
            data={
                "username": settings.marzban_username,
                "password": settings.marzban_password,
            },
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        return self._token

    async def _headers(self) -> dict[str, str]:
        token = await self._get_token()
        return {"Authorization": f"Bearer {token}"}

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = await self._headers()
        resp = await self._client.request(
            method, f"{self.base_url}{path}", headers=headers, **kwargs
        )
        if resp.status_code == 401:
            await self._refresh_token()
            headers = await self._headers()
            resp = await self._client.request(
                method, f"{self.base_url}{path}", headers=headers, **kwargs
            )
        resp.raise_for_status()
        return resp

    async def create_user(
        self,
        username: str,
        expire_timestamp: int,
        data_limit_bytes: int,
    ) -> dict:
        payload = {
            "username": username,
            "proxies": {"vless": {"flow": "xtls-rprx-vision"}},
            "inbounds": {"vless": ["VLESS TCP REALITY"]},
            "expire": expire_timestamp,
            "data_limit": data_limit_bytes,
            "data_limit_reset_strategy": "no_reset",
        }
        resp = await self._request("POST", "/user", json=payload)
        return resp.json()

    async def get_user(self, username: str) -> dict:
        resp = await self._request("GET", f"/user/{username}")
        return resp.json()

    async def modify_user(self, username: str, **fields) -> dict:
        resp = await self._request("PUT", f"/user/{username}", json=fields)
        return resp.json()

    async def delete_user(self, username: str) -> None:
        await self._request("DELETE", f"/user/{username}")

    async def get_vless_link(self, username: str) -> str:
        """Get first vless:// link from user's links field."""
        data = await self.get_user(username)
        links = data.get("links", [])
        for link in links:
            if link.startswith("vless://"):
                return link
        raise ValueError(f"No vless:// link found for user {username}")

    async def get_user_usage(self, username: str) -> dict:
        """Return dict with used_traffic, data_limit, expire, status."""
        data = await self.get_user(username)
        return {
            "used_traffic": data.get("used_traffic", 0),
            "data_limit": data.get("data_limit", 0),
            "expire": data.get("expire"),
            "status": data.get("status", "unknown"),
            "online_at": data.get("online_at"),
        }

    async def close(self) -> None:
        await self._client.aclose()


marzban_client = MarzbanClient()
