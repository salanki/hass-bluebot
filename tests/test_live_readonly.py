"""Opt-in read-only live tests against the real Bluebot API.

Run with ``make test-live`` and ``BLUEBOT_API_KEY`` set. Skipped by default.
"""

from __future__ import annotations

import os

import aiohttp
import pytest
from pybluebot import BluebotClient

pytestmark = pytest.mark.live

API_KEY = os.environ.get("BLUEBOT_API_KEY", "")


@pytest.mark.skipif(not API_KEY, reason="BLUEBOT_API_KEY not set")
async def test_live_devices_and_flow():
    async with aiohttp.ClientSession() as session:
        client = BluebotClient(API_KEY, session)
        org = await client.async_validate()
        assert org
        devices = await client.async_get_devices()
        assert devices
        latest = await client.async_get_latest([d.id for d in devices])
        assert set(latest) <= {d.id for d in devices}
        total = await client.async_get_total_volume(devices[0].id)
        assert total is None or total >= 0
