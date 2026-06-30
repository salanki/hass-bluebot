"""Entity behaviour tests (flow freshness, totals, flowing)."""

from __future__ import annotations

from .helpers import FakeClient, make_datapoint, make_device


async def test_entities_created(setup_integration, hass):
    device = make_device(device_id="d1", serial="BB1")
    client = FakeClient(
        devices=[device],
        latest={"d1": make_datapoint(flow_rate=6.5)},
        totals={"d1": 1234.5},
    )
    await setup_integration(client)

    assert hass.states.get("sensor.pool_hx_flow_rate").state == "6.5"
    assert hass.states.get("sensor.pool_hx_total_volume").state == "1234.5"
    assert hass.states.get("binary_sensor.pool_hx_flowing").state == "on"


async def test_stale_datapoint_reads_zero(setup_integration, hass):
    device = make_device(device_id="d1", serial="BB1")
    client = FakeClient(
        devices=[device],
        latest={"d1": make_datapoint(age_seconds=3600, flow_rate=6.5)},
        totals={"d1": 10.0},
    )
    await setup_integration(client)

    # Stale (1h old) -> meter idle -> 0 GPM and not flowing.
    assert hass.states.get("sensor.pool_hx_flow_rate").state == "0.0"
    assert hass.states.get("binary_sensor.pool_hx_flowing").state == "off"


async def test_no_datapoint_is_unknown(setup_integration, hass):
    device = make_device(device_id="d1", serial="BB1")
    client = FakeClient(devices=[device], latest={"d1": None}, totals={})
    await setup_integration(client)

    assert hass.states.get("sensor.pool_hx_flow_rate").state == "unknown"
    # Total volume with no data is unavailable, not a misleading 0.
    assert hass.states.get("sensor.pool_hx_total_volume").state == "unavailable"


async def test_inactive_device_skipped(setup_integration, hass):
    active = make_device(device_id="d1", serial="BB1", label="Pool HX")
    gateway = make_device(
        device_id="g1", serial="GW1", label="Gateway", category="Gateway"
    )
    client = FakeClient(
        devices=[active, gateway],
        latest={"d1": make_datapoint()},
        totals={"d1": 1.0},
    )
    entry, _ = await setup_integration(client)

    assert hass.states.get("sensor.pool_hx_flow_rate") is not None
    assert hass.states.get("sensor.gateway_flow_rate") is None
    assert entry.runtime_data.devices == [active]
