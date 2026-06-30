"""Config, reauth and options flow tests."""

from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pybluebot import BluebotAuthError, BluebotConnectionError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bluebot.const import (
    CONF_API_KEY,
    CONF_FLOW_SCAN_INTERVAL,
    DOMAIN,
)


def _patch_validate(monkeypatch, result):
    async def _fake(hass, api_key):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("custom_components.bluebot.config_flow._validate", _fake)


async def test_user_flow_success(hass, monkeypatch):
    _patch_validate(monkeypatch, "org-1")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "prefix.uuid"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "org-1"
    assert result["data"][CONF_API_KEY] == "prefix.uuid"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (BluebotAuthError("no"), "invalid_auth"),
        (BluebotConnectionError("down"), "cannot_connect"),
    ],
)
async def test_user_flow_errors(hass, monkeypatch, error, expected):
    _patch_validate(monkeypatch, error)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "bad"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == expected


async def test_user_flow_duplicate_aborts(hass, monkeypatch):
    MockConfigEntry(domain=DOMAIN, unique_id="org-1").add_to_hass(hass)
    _patch_validate(monkeypatch, "org-1")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "prefix.uuid"}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow_updates_key(hass, monkeypatch):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="org-1", data={CONF_API_KEY: "old"}
    )
    entry.add_to_hass(hass)
    _patch_validate(monkeypatch, "org-1")

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "new-key"}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_KEY] == "new-key"


async def test_reauth_wrong_account_aborts(hass, monkeypatch):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="org-1", data={CONF_API_KEY: "old"}
    )
    entry.add_to_hass(hass)
    _patch_validate(monkeypatch, "org-2")

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "other-org"}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "wrong_account"


async def test_options_flow(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="org-1")
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_FLOW_SCAN_INTERVAL: 45, "totals_scan_interval": 600}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_FLOW_SCAN_INTERVAL] == 45
