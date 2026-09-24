"""Cloud liveness must never turn missing/stale telemetry into zero flow."""

from dataclasses import replace
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.bluebot.pybluebot import BluebotConnectionError

from .helpers import FakeClient, make_datapoint, make_device


async def test_expiry_unchanged_poll_and_recovery(setup_integration, hass, freezer):
    start = dt_util.utcnow()
    dp = make_datapoint(flow_rate=0)
    client = FakeClient(latest={"dev-1": dp}, totals={"dev-1": 20})
    entry, _ = await setup_integration(client)
    flow = entry.runtime_data.flow
    assert hass.states.get("binary_sensor.pool_hx_online").state == "on"
    assert hass.states.get("sensor.pool_hx_flow_rate").state == "0"
    assert hass.states.get("binary_sensor.pool_hx_flowing").state == "off"

    freezer.move_to(start + timedelta(seconds=59))
    await flow.async_refresh()  # Successful request, unchanged cached data.
    assert hass.states.get("binary_sensor.pool_hx_online").state == "on"

    freezer.move_to(start + timedelta(seconds=60))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.pool_hx_online").state == "off"
    assert hass.states.get("sensor.pool_hx_flow_rate").state == "unavailable"
    assert hass.states.get("binary_sensor.pool_hx_flowing").state == "unavailable"
    assert hass.states.get("sensor.pool_hx_total_volume").state == "20"

    client.latest["dev-1"] = make_datapoint(flow_rate=7)
    await flow.async_refresh()
    assert hass.states.get("binary_sensor.pool_hx_online").state == "on"
    assert hass.states.get("sensor.pool_hx_flow_rate").state == "7"
    assert hass.states.get("binary_sensor.pool_hx_flowing").state == "on"
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert flow._cancel_expiry is None


async def test_cloud_error_is_unavailable_and_recovers(
    setup_integration, hass, monkeypatch
):
    client = FakeClient(latest={"dev-1": make_datapoint()})
    entry, _ = await setup_integration(client)
    original = client.async_get_latest
    monkeypatch.setattr(
        client,
        "async_get_latest",
        AsyncMock(side_effect=BluebotConnectionError("cloud unreachable")),
    )
    await entry.runtime_data.flow.async_refresh()
    assert hass.states.get("binary_sensor.pool_hx_online").state == "unavailable"
    assert hass.states.get("sensor.pool_hx_flow_rate").state == "unavailable"
    monkeypatch.setattr(client, "async_get_latest", original)
    await entry.runtime_data.flow.async_refresh()
    assert hass.states.get("binary_sensor.pool_hx_online").state == "on"


async def test_offline_meter_does_not_hide_other_meter(setup_integration, hass):
    client = FakeClient(
        devices=[make_device(), make_device("d2", "BB2", "Auto Fill")],
        latest={
            "dev-1": make_datapoint(age_seconds=61),
            "d2": make_datapoint(flow_rate=0),
        },
    )
    await setup_integration(client)
    assert hass.states.get("binary_sensor.pool_hx_online").state == "off"
    assert hass.states.get("binary_sensor.auto_fill_online").state == "on"
    assert hass.states.get("sensor.auto_fill_flow_rate").state == "0"


@pytest.mark.parametrize("field", ["recorded_at", "flow_rate"])
async def test_incomplete_datapoint_is_not_no_flow(setup_integration, hass, field):
    dp = replace(make_datapoint(), **{field: None})
    await setup_integration(FakeClient(latest={"dev-1": dp}))
    assert hass.states.get("binary_sensor.pool_hx_flowing").state != "off"
    assert hass.states.get("sensor.pool_hx_flow_rate").state != "0"
