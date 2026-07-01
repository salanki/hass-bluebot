"""Async client for the Bluebot water-flow-meter cloud REST API.

Base URL ``https://prod.bluebot.com/management/v1``. Authentication is a single
``bluebot-api-key`` header.

API-key quirk
-------------
Bluebot issues keys in the form ``<prefix>.<uuid>`` but the backend only accepts
the **uuid part after the dot** — the full string returns ``403`` on every
endpoint. :func:`normalize_api_key` strips to the last dot-separated segment so
users can paste either form.

Only read endpoints are used; this integration never writes to the cloud.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

import aiohttp

from .exceptions import BluebotAuthError, BluebotConnectionError, BluebotError
from .models import Device, LatestDatapoint

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://prod.bluebot.com/management/v1"
API_KEY_HEADER = "bluebot-api-key"

DEFAULT_TIMEOUT = 30.0
# ``/flow/latest`` accepts at most 50 device ids per call.
LATEST_BATCH_SIZE = 50
# ``GET /device`` page size when paginating large accounts.
DEVICE_PAGE_SIZE = 200


def normalize_api_key(api_key: str) -> str:
    """Return the usable key: the segment after the last dot (if any)."""
    return api_key.strip().rsplit(".", 1)[-1]


def _chunked(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


class BluebotClient:
    """Thin async wrapper over the Bluebot REST API."""

    def __init__(
        self,
        api_key: str,
        session: aiohttp.ClientSession,
        *,
        base_url: str = BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._key = normalize_api_key(api_key)
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    async def _request(self, path: str, params: object = None) -> object:
        """GET ``path`` and return parsed JSON, mapping failures to our errors."""
        url = f"{self._base_url}{path}"
        try:
            async with self._session.get(
                url,
                params=params,
                headers={API_KEY_HEADER: self._key},
                timeout=self._timeout,
            ) as resp:
                if resp.status in (401, 403):
                    raise BluebotAuthError(
                        f"API key rejected ({resp.status}) for {path}"
                    )
                if resp.status == 429 or resp.status >= 500:
                    raise BluebotConnectionError(
                        f"retryable server response {resp.status} for {path}"
                    )
                if resp.status >= 400:
                    body = await resp.text()
                    raise BluebotError(f"HTTP {resp.status} for {path}: {body[:200]}")
                return await resp.json()
        except BluebotError:
            raise
        except (TimeoutError, aiohttp.ClientError) as err:
            raise BluebotConnectionError(f"request to {path} failed: {err}") from err

    async def async_validate(self) -> str:
        """Validate the key and return the organization id (the entry unique_id).

        Uses ``GET /organizations/mine`` (works even with zero meters). Falls
        back to a meter's ``organizationId`` if the org list is empty.
        """
        data = await self._request("/organizations/mine")
        if isinstance(data, list) and data:
            org_id = data[0].get("id")
            if org_id:
                return str(org_id)
        devices = await self.async_get_devices()
        for device in devices:
            if device.organization_id:
                return device.organization_id
        raise BluebotError("no organization found for this API key")

    async def async_get_devices(self) -> list[Device]:
        """Return all meters, paginating through ``GET /device``."""
        devices: list[Device] = []
        offset = 0
        while True:
            data = await self._request(
                "/device",
                params={
                    "limit": DEVICE_PAGE_SIZE,
                    "offset": offset,
                    "pagination": "true",
                },
            )
            # With pagination=true the API returns {data: [...], total: n};
            # without it (older behaviour) it returns a bare list. Handle both.
            if isinstance(data, dict):
                rows = data.get("data", [])
                total = data.get("total")
            else:
                rows = data
                total = None
            devices.extend(Device.from_json(row) for row in rows)
            offset += len(rows)
            if not rows or (total is not None and offset >= total):
                break
            if total is None:  # bare-list response: single page only
                break
        return devices

    async def async_get_latest(
        self, device_ids: Sequence[str]
    ) -> dict[str, LatestDatapoint | None]:
        """Return the latest datapoint per device, batching at 50 ids/call."""
        result: dict[str, LatestDatapoint | None] = {}
        for batch in _chunked(list(device_ids), LATEST_BATCH_SIZE):
            params = [("ids", ",".join(batch)), ("metrics", "lastDatapoint")]
            data = await self._request("/flow/latest", params=params)
            rows = data.get("data", []) if isinstance(data, dict) else []
            for row in rows:
                device_id = row.get("deviceId")
                if not device_id:
                    continue
                raw = row.get("lastDatapoint")
                result[str(device_id)] = (
                    LatestDatapoint.from_json(raw) if raw else None
                )
        return result

    async def async_get_total_volume(self, device_id: str) -> float | None:
        """Return lifetime cumulative volume (US gallons) for one meter."""
        data = await self._request(
            f"/flow/datapoints/{device_id}",
            params={"resolution": "total"},
        )
        rows = data.get("data", []) if isinstance(data, dict) else []
        if not rows:
            return None
        value = rows[0].get("total_flow_amount")
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    async def async_get_today_volume(
        self, device_id: str, timezone: str | None, from_iso: str
    ) -> float:
        """Return gallons since local midnight for one meter.

        Uses the server-side daily rollup (``resolution=day``) with ``timezone``
        so the day boundary matches the meter's own timezone — the same figure
        Bluebot's app shows. ``from_iso`` is local midnight today. Returns 0.0
        when there is no flow yet today.
        """
        params: dict[str, object] = {"resolution": "day", "from": from_iso}
        if timezone:
            params["timezone"] = timezone
        data = await self._request(f"/flow/datapoints/{device_id}", params=params)
        rows = data.get("data", []) if isinstance(data, dict) else []
        total = 0.0
        for row in rows:
            value = row.get("total_flow_amount")
            if value is not None:
                try:
                    total += float(value)
                except (TypeError, ValueError):
                    continue
        return total
