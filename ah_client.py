"""Agent Handler API Client — synchronous for Streamlit."""

import json
import re
import httpx
from typing import Any

AH_BASE_URL = "https://ah-api.merge.dev/api/v1"


class AgentHandlerClient:
    def __init__(self, api_key: str, tool_pack_id: str, registered_user_id: str):
        self.api_key = api_key
        self.tool_pack_id = tool_pack_id
        self.registered_user_id = registered_user_id
        self.mcp_url = (
            f"{AH_BASE_URL}/tool-packs/{tool_pack_id}"
            f"/registered-users/{registered_user_id}/mcp"
        )
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._session_id: str | None = None

    def _mcp(self, method: str, params: dict | None = None, req_id: int = 1) -> dict:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params:
            payload["params"] = params
        headers = {**self.headers}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(self.mcp_url, json=payload, headers=headers, params={"format": "json"})
            if "mcp-session-id" in resp.headers:
                self._session_id = resp.headers["mcp-session-id"]
            resp.raise_for_status()
            return resp.json()

    def initialize(self):
        return self._mcp("initialize")

    def list_tools(self) -> list[dict]:
        if not self._session_id:
            self.initialize()
        result = self._mcp("tools/list")
        return result.get("result", {}).get("tools", [])

    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        if not self._session_id:
            self.initialize()
        result = self._mcp("tools/call", params={"name": tool_name, "arguments": arguments})
        return result.get("result", {})

    # ── REST helpers ──

    def _get(self, path: str, params: dict | None = None) -> dict:
        with httpx.Client(timeout=30.0) as c:
            r = c.get(f"{AH_BASE_URL}/{path}", headers=self.headers, params=params)
            r.raise_for_status()
            return r.json()

    def _post(self, path: str, body: dict) -> dict:
        with httpx.Client(timeout=30.0) as c:
            r = c.post(f"{AH_BASE_URL}/{path}", headers=self.headers, json=body)
            if r.status_code >= 400:
                try:
                    detail = r.json()
                except Exception:
                    detail = r.text
                raise Exception(f"{r.status_code}: {detail}")
            return r.json()

    def _patch(self, path: str, body: dict) -> dict:
        with httpx.Client(timeout=30.0) as c:
            r = c.patch(f"{AH_BASE_URL}/{path}", headers=self.headers, json=body)
            r.raise_for_status()
            return r.json()

    def _delete(self, path: str):
        with httpx.Client(timeout=30.0) as c:
            r = c.delete(f"{AH_BASE_URL}/{path}", headers=self.headers)
            r.raise_for_status()

    def list_connectors(self) -> list[dict]:
        results, url = [], f"{AH_BASE_URL}/connectors?page_size=50"
        with httpx.Client(timeout=30.0) as c:
            while url:
                r = c.get(url, headers=self.headers)
                r.raise_for_status()
                data = r.json()
                results.extend(data.get("results", []))
                url = data.get("next")
        return results

    def get_connector(self, slug: str) -> dict:
        return self._get(f"connectors/{slug}")

    def list_tool_packs(self) -> list[dict]:
        return self._get("tool-packs/").get("results", [])

    def get_tool_pack(self, pack_id: str) -> dict:
        return self._get(f"tool-packs/{pack_id}/")

    def create_tool_pack(self, name: str, desc: str, connectors: list[dict]) -> dict:
        return self._post("tool-packs/", {"name": name, "description": desc, "connectors": connectors})

    def update_tool_pack(self, pack_id: str, **fields) -> dict:
        return self._patch(f"tool-packs/{pack_id}/", fields)

    def delete_tool_pack(self, pack_id: str):
        self._delete(f"tool-packs/{pack_id}/")

    def list_app_credentials(self) -> list[dict]:
        return self._get("application-credentials").get("results", [])

    def create_app_credential(self, connector_slug: str, client_id: str, client_secret: str,
                              external_id: str | None = None, scopes: str | None = None) -> dict:
        body: dict[str, Any] = {"connector_slug": connector_slug, "client_id": client_id, "client_secret": client_secret}
        if external_id: body["external_id"] = external_id
        if scopes: body["scopes"] = scopes
        return self._post("application-credentials", body)

    def update_app_credential(self, cred_id: str, **fields) -> dict:
        return self._patch(f"application-credentials/{cred_id}", fields)

    def delete_app_credential(self, cred_id: str):
        self._delete(f"application-credentials/{cred_id}")

    def list_registered_users(self) -> list[dict]:
        results = []
        with httpx.Client(timeout=30.0) as c:
            for is_test in ["false", "true"]:
                r = c.get(f"{AH_BASE_URL}/registered-users", headers=self.headers,
                          params={"is_test": is_test, "page_size": "100"})
                r.raise_for_status()
                results.extend(r.json().get("results", []))
        return results

    def create_registered_user(self, origin_user_id: str, origin_user_name: str,
                               shared_credential_group: dict | None = None) -> dict:
        body: dict[str, Any] = {"origin_user_id": origin_user_id, "origin_user_name": origin_user_name}
        if shared_credential_group:
            body["shared_credential_group"] = shared_credential_group
        return self._post("registered-users", body)

    def create_or_find_registered_user(self, origin_user_id: str, origin_user_name: str,
                                       shared_credential_group: dict | None = None) -> str:
        """Create a registered user or find existing. Returns the AH user ID."""
        try:
            user = self.create_registered_user(origin_user_id, origin_user_name, shared_credential_group)
            return user.get("id", "")
        except Exception as e:
            err = str(e)
            if "already exists" in err:
                match = re.search(r"registered-users/([a-f0-9-]+)", err)
                if match:
                    return match.group(1)
            # Fallback: search
            for u in self.list_registered_users():
                if u.get("origin_user_id") == origin_user_id:
                    return u.get("id", "")
            return ""

    def create_link_token(self, connector_slug: str) -> str:
        return self._post(
            f"registered-users/{self.registered_user_id}/link-token",
            {"connector": connector_slug},
        ).get("link_token", "")

    def delete_user_credentials(self, connector_slug: str):
        self._delete(f"credentials/registered-users/{self.registered_user_id}/connectors/{connector_slug}")
