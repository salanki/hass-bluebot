"""Unit tests for the pybluebot client and parsing helpers."""

from __future__ import annotations

import pytest
from pybluebot import (
    BluebotAuthError,
    BluebotClient,
    BluebotConnectionError,
    BluebotError,
    Device,
    LatestDatapoint,
    normalize_api_key,
)
from pybluebot.util import parse_timestamp, to_bool, to_float

from .helpers import FakeResponse, FakeSession


def test_normalize_api_key_strips_prefix():
    # The documented quirk: only the part after the dot is accepted upstream.
    assert (
        normalize_api_key("9tDgW6OYyN1.afdf8839-8b9b-40c6")
        == "afdf8839-8b9b-40c6"
    )
    # Already-normalized UUID passes through untouched.
    assert normalize_api_key("afdf8839-8b9b-40c6") == "afdf8839-8b9b-40c6"
    assert normalize_api_key("  trims.me  ") == "me"


def test_to_float_and_bool():
    assert to_float("3.5") == 3.5
    assert to_float(None) is None
    assert to_float("nope") is None
    assert to_bool("true") is True
    assert to_bool(0) is False
    assert to_bool("maybe") is None


def test_parse_timestamp_handles_z_suffix():
    ts = parse_timestamp("2026-06-30T13:08:03.522Z")
    assert ts is not None
    assert ts.tzinfo is not None
    assert parse_timestamp(None) is None
    assert parse_timestamp("garbage") is None


def test_device_from_json_and_meter_filter():
    meter = Device.from_json(
        {
            "id": "abc",
            "serialNumber": "BB1",
            "label": "Pool HX",
            "model": "100-W",
            "category": "EndDevice",
            "active": True,
            "organizationId": "org",
        }
    )
    assert meter.name == "Pool HX"
    assert meter.is_meter is True

    inactive = Device.from_json({"id": "x", "serialNumber": "BB2", "active": False})
    assert inactive.is_meter is False
    assert inactive.name == "BB2"  # falls back to serial


def test_latest_datapoint_from_json():
    dp = LatestDatapoint.from_json(
        {
            "recordedAt": "2026-06-30T13:08:03.522Z",
            "flowRate": 6.3,
            "flowAmount": 0.18,
            "flowDuration": 1772,
            "quality": 99,
            "signalStrength": 80,
            "networkRssi": -57,
            "onboardTemperature": None,
        }
    )
    assert dp.flow_rate == 6.3
    assert dp.network_rssi == -57.0
    assert dp.recorded_at is not None


def _session_for(payload, status=200, text=""):
    return FakeSession(lambda url, params, headers: FakeResponse(status, payload, text))


async def test_request_auth_error_maps():
    client = BluebotClient("k", _session_for(None, status=403))
    with pytest.raises(BluebotAuthError):
        await client.async_get_total_volume("dev")


async def test_request_retryable_error_maps():
    for status in (429, 500, 503):
        client = BluebotClient("k", _session_for(None, status=status))
        with pytest.raises(BluebotConnectionError):
            await client.async_get_total_volume("dev")


async def test_request_client_error_maps():
    client = BluebotClient("k", _session_for(None, status=404, text="nope"))
    with pytest.raises(BluebotError):
        await client.async_get_total_volume("dev")


async def test_get_total_volume_parses():
    payload = {"data": [{"total_flow_amount": 61892.9}]}
    client = BluebotClient("k", _session_for(payload))
    assert await client.async_get_total_volume("dev") == pytest.approx(61892.9)


async def test_get_latest_keys_by_device_and_sends_header():
    payload = {
        "data": [
            {
                "deviceId": "dev-1",
                "lastDatapoint": {"recordedAt": "2026-06-30T13:00:00Z", "flowRate": 5},
            },
            {"deviceId": "dev-2", "lastDatapoint": None},
        ]
    }
    session = _session_for(payload)
    client = BluebotClient("prefix.thekey", session)
    result = await client.async_get_latest(["dev-1", "dev-2"])
    assert result["dev-1"].flow_rate == 5.0
    assert result["dev-2"] is None
    # Header carries the normalized key.
    assert session.calls[0]["headers"]["bluebot-api-key"] == "thekey"


async def test_get_devices_handles_bare_list():
    payload = [{"id": "a", "serialNumber": "BB1", "active": True}]
    client = BluebotClient("k", _session_for(payload))
    devices = await client.async_get_devices()
    assert len(devices) == 1
    assert devices[0].id == "a"


async def test_get_latest_batches_over_50_ids():
    seen_batches = []

    def handler(url, params, headers):
        ids = dict(params)["ids"].split(",") if params else []
        seen_batches.append(len(ids))
        rows = [{"deviceId": i, "lastDatapoint": None} for i in ids]
        return FakeResponse(200, {"data": rows})

    client = BluebotClient("k", FakeSession(handler))
    ids = [f"d{i}" for i in range(120)]
    result = await client.async_get_latest(ids)
    assert len(result) == 120
    assert seen_batches == [50, 50, 20]
