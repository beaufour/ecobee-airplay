import argparse
from ipaddress import ip_address
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pyatv.const import Protocol

from ecobee_airplay import cli
from ecobee_airplay.cli import (
    EcobeeAirplayError,
    _choose_device,
    _filter_ecobees,
    _is_ecobee,
    _normalize_source,
    _volume,
)


class FakeService:
    def __init__(self, protocol=Protocol.RAOP, **properties):
        self.protocol = protocol
        self.properties = properties


class FakeConfig:
    def __init__(self, name, address, model, services=None, identifiers=None):
        self.name = name
        self.address = ip_address(address)
        self.device_info = SimpleNamespace(raw_model=model, model_str=model)
        self.services = services or [FakeService(am=model)]
        self.all_identifiers = identifiers or set()

    def get_service(self, protocol):
        return next(
            (service for service in self.services if service.protocol == protocol),
            None,
        )


def test_ecobee_model_is_recognized():
    assert _is_ecobee(FakeConfig("Guest Room", "192.0.2.10", "EB-STATE5"))


def test_non_ecobee_airplay_receiver_is_ignored():
    device = FakeConfig("Guest Room", "192.0.2.11", "AppleTV5,3")
    assert not _is_ecobee(device)
    assert _filter_ecobees([device]) == []


def test_manufacturer_fallback_is_recognized():
    service = FakeService(manufacturer="ecobee Inc.")
    device = FakeConfig("Hall", "192.0.2.12", "Unknown", [service])
    assert _is_ecobee(device)


def test_choose_device_by_case_insensitive_name():
    guest = FakeConfig("Guest Room", "192.0.2.10", "EB-STATE5")
    kitchen = FakeConfig("Kitchen", "192.0.2.20", "EB-STATE5")
    assert _choose_device([guest, kitchen], "guest room") is guest


def test_choose_device_by_ip():
    guest = FakeConfig("Guest Room", "192.0.2.10", "EB-STATE5")
    assert _choose_device([guest], "192.0.2.10") is guest


def test_choose_device_requires_selector_when_multiple():
    devices = [
        FakeConfig("Guest Room", "192.0.2.10", "EB-STATE5"),
        FakeConfig("Kitchen", "192.0.2.20", "EB-STATE5"),
    ]
    with pytest.raises(EcobeeAirplayError, match="multiple Ecobees"):
        _choose_device(devices, None)


def test_normalize_source_accepts_https_url():
    url = "https://example.com/chime.mp3"
    assert _normalize_source(url) == url


def test_normalize_source_rejects_missing_file():
    with pytest.raises(EcobeeAirplayError, match="does not exist"):
        _normalize_source("missing.mp3")


def test_volume_accepts_fractional_percentage():
    assert _volume("33.5") == 33.5


def test_volume_rejects_out_of_range_value():
    with pytest.raises(argparse.ArgumentTypeError, match="0 to 100"):
        _volume("101")


def test_scan_by_ip_uses_unicast_and_keeps_ecobee_filter(monkeypatch, capsys):
    ecobee = FakeConfig("Guest Room", "192.0.2.10", "EB-STATE5")
    apple_tv = FakeConfig("Guest Room", "192.0.2.11", "AppleTV5,3")
    scan = AsyncMock(return_value=[apple_tv, ecobee])
    monkeypatch.setattr(cli.pyatv, "scan", scan)

    assert cli.main(["scan", "--device", "192.0.2.10", "--debug"]) == 0

    assert scan.call_args.kwargs["hosts"] == ["192.0.2.10"]
    assert scan.call_args.kwargs["protocol"] == {Protocol.AirPlay, Protocol.RAOP}
    output = capsys.readouterr()
    assert "192.0.2.10" in output.out
    assert "192.0.2.11" not in output.out
    assert "2 AirPlay/RAOP receivers, 1 Ecobees" in output.err
    assert "ignored: not identified as Ecobee" in output.err


def test_empty_scan_explains_discovery_limitations(monkeypatch, capsys):
    monkeypatch.setattr(cli.pyatv, "scan", AsyncMock(return_value=[]))
    monkeypatch.setattr(cli.sys, "platform", "darwin")

    assert cli.main(["scan", "--debug"]) == 1

    output = capsys.readouterr()
    assert "No Ecobee AirPlay receivers found." in output.out
    assert "0 AirPlay/RAOP receivers, 0 Ecobees" in output.err
    assert "--device THERMOSTAT_IP" in output.err
    assert "Local Network" in output.err


def test_debug_scan_explains_missing_raop_service(monkeypatch, capsys):
    ecobee = FakeConfig(
        "Guest Room",
        "192.0.2.10",
        "EB-STATE5",
        [FakeService(protocol=Protocol.AirPlay, manufacturer="ecobee Inc.")],
    )
    monkeypatch.setattr(cli.pyatv, "scan", AsyncMock(return_value=[ecobee]))

    assert cli.main(["scan", "--debug"]) == 1

    assert "ignored: no RAOP service" in capsys.readouterr().err
