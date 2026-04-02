"""3X-UI API client."""

import json
import logging
import urllib.parse
import uuid as uuid_mod

import httpx

from src.utils.config import settings

logger = logging.getLogger(__name__)


class XUIClient:
    def __init__(self) -> None:
        self.base_url = settings.marzban_address.rstrip("/")
        self._client = httpx.AsyncClient(timeout=15.0, verify=False)
        self._logged_in = False

    async def _login(self) -> None:
        resp = await self._client.post(
            f"{self.base_url}/login",
            data={
                "username": settings.marzban_username,
                "password": settings.marzban_password,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"3X-UI login failed: {data}")
        self._logged_in = True

    async def _ensure_logged_in(self) -> None:
        if not self._logged_in:
            await self._login()

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        await self._ensure_logged_in()
        resp = await self._client.request(
            method, f"{self.base_url}{path}", **kwargs
        )
        if resp.status_code == 401:
            self._logged_in = False
            await self._login()
            resp = await self._client.request(
                method, f"{self.base_url}{path}", **kwargs
            )
        resp.raise_for_status()
        return resp

    async def _get_reality_inbound(self) -> dict:
        """Find the inbound with 'reality' in tag or remark."""
        resp = await self._request("GET", "/panel/api/inbounds/list")
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"Failed to list inbounds: {data}")
        for inbound in data.get("obj", []):
            tag = (inbound.get("tag") or "").lower()
            remark = (inbound.get("remark") or "").lower()
            if "reality" in tag or "reality" in remark:
                return inbound
        raise ValueError("No inbound with 'reality' tag/remark found")

    async def create_client(
        self,
        email: str,
        expire_timestamp_ms: int,
        limit_ip: int = 3,
    ) -> str:
        """Create a client in the reality inbound. Returns the client UUID."""
        inbound = await self._get_reality_inbound()
        inbound_id = inbound["id"]
        client_uuid = str(uuid_mod.uuid4())

        client_settings = {
            "id": client_uuid,
            "email": email,
            "flow": "xtls-rprx-vision",
            "enable": True,
            "expiryTime": expire_timestamp_ms,
            "totalGB": 0,
            "limitIp": limit_ip,
        }

        payload = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [client_settings]}),
        }

        resp = await self._request(
            "POST", "/panel/api/inbounds/addClient", json=payload
        )
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"Failed to create client: {data}")

        return client_uuid

    async def update_client(
        self,
        client_uuid: str,
        email: str,
        expire_timestamp_ms: int,
    ) -> None:
        """Update client expiry and re-enable."""
        inbound = await self._get_reality_inbound()
        inbound_id = inbound["id"]

        client_settings = {
            "id": client_uuid,
            "email": email,
            "flow": "xtls-rprx-vision",
            "enable": True,
            "expiryTime": expire_timestamp_ms,
            "totalGB": 0,
            "limitIp": 3,
        }

        payload = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [client_settings]}),
        }

        resp = await self._request(
            "POST", f"/panel/api/inbounds/updateClient/{client_uuid}", json=payload
        )
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"Failed to update client: {data}")

    async def get_client_traffic(self, email: str) -> dict:
        """Get client traffic stats by email."""
        resp = await self._request(
            "GET", f"/panel/api/inbounds/getClientTraffics/{email}"
        )
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"Failed to get client traffic: {data}")
        obj = data.get("obj", {})
        return {
            "used_traffic": (obj.get("up", 0) or 0) + (obj.get("down", 0) or 0),
            "up": obj.get("up", 0),
            "down": obj.get("down", 0),
            "expiry_time": obj.get("expiryTime", 0),
            "enable": obj.get("enable", False),
        }

    async def get_vless_link(self, email: str) -> str:
        """Build vless:// link from inbound settings and client UUID."""
        inbound = await self._get_reality_inbound()

        # Find client UUID by email
        clients_raw = inbound.get("settings", "{}")
        if isinstance(clients_raw, str):
            clients_data = json.loads(clients_raw)
        else:
            clients_data = clients_raw

        client_uuid = None
        for client in clients_data.get("clients", []):
            if client.get("email") == email:
                client_uuid = client["id"]
                break

        if not client_uuid:
            raise ValueError(f"Client with email {email} not found in inbound")

        # Parse stream settings
        stream_raw = inbound.get("streamSettings", "{}")
        if isinstance(stream_raw, str):
            stream = json.loads(stream_raw)
        else:
            stream = stream_raw

        network = stream.get("network", "tcp")
        security = stream.get("security", "reality")

        reality = stream.get("realitySettings", {})
        server_names = reality.get("serverNames", [])
        sni = server_names[0] if server_names else ""
        public_key = reality.get("settings", {}).get("publicKey", "")
        short_ids = reality.get("shortIds", [])
        sid = short_ids[0] if short_ids else ""
        fingerprint = reality.get("settings", {}).get("fingerprint", "chrome")

        # Build address and port
        listen = inbound.get("listen", "")
        port = inbound.get("port", 443)
        # Use panel address host if listen is empty or 0.0.0.0
        if not listen or listen in ("0.0.0.0", "::"):
            parsed = urllib.parse.urlparse(self.base_url)
            listen = parsed.hostname or "127.0.0.1"

        remark = inbound.get("remark", "VPN")

        params = {
            "type": network,
            "security": security,
            "pbk": public_key,
            "fp": fingerprint,
            "sni": sni,
            "sid": sid,
            "flow": "xtls-rprx-vision",
        }
        query = urllib.parse.urlencode(params)
        fragment = urllib.parse.quote(remark)

        return f"vless://{client_uuid}@{listen}:{port}?{query}#{fragment}"

    async def delete_client(self, inbound_id: int, client_uuid: str) -> None:
        resp = await self._request(
            "POST", f"/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}"
        )
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"Failed to delete client: {data}")

    async def close(self) -> None:
        await self._client.aclose()


xui_client = XUIClient()
