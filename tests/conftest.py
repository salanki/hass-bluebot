from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bluebot.const import CONF_API_KEY, DOMAIN

from .helpers import FakeClient, make_device


@pytest.hookimpl(trylast=True)
def pytest_runtest_setup(item):
    """Re-enable sockets for ``live`` tests so they reach the real API."""
    if item.get_closest_marker("live") is not None:
        import socket

        import pytest_socket

        pytest_socket.enable_socket()
        socket.socket.connect = pytest_socket._true_connect


@pytest.fixture(scope="session", autouse=True)
def _prewarm_aiohttp_shutdown_thread():
    """Pre-create + close an aiohttp session so the per-test thread diff is empty."""
    import asyncio

    import aiohttp

    async def _poke():
        session = aiohttp.ClientSession()
        await session.close()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_poke())
    finally:
        loop.close()
    yield


@pytest.fixture
def setup_integration(hass, enable_custom_integrations, monkeypatch):
    """Set up the integration backed by a FakeClient; returns (entry, client)."""

    async def _setup(client: FakeClient | None = None):
        client = client or FakeClient(
            devices=[make_device()],
            latest={},
            totals={},
        )
        monkeypatch.setattr(
            "custom_components.bluebot.BluebotClient",
            lambda *a, **k: client,
        )
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_API_KEY: "prefix.uuid"},
            unique_id="org-1",
            title="Bluebot",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return entry, client

    return _setup
