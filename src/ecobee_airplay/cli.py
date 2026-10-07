"""Command-line interface for discovering and playing to Ecobee receivers."""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pyatv
from pyatv.const import Protocol

from ecobee_airplay import __version__


class EcobeeAirplayError(RuntimeError):
    """A user-actionable discovery or selection error."""


def _model_name(config: Any) -> str:
    device_info = config.device_info
    raw_model = getattr(device_info, "raw_model", None)
    if raw_model:
        return str(raw_model)
    return str(getattr(device_info, "model_str", "Unknown"))


def _is_ecobee(config: Any) -> bool:
    model = _model_name(config).casefold()
    if model.startswith("eb-") or "ecobee" in model:
        return True

    for service in config.services:
        properties = getattr(service, "properties", {})
        manufacturer = str(properties.get("manufacturer", "")).casefold()
        advertised_model = str(properties.get("am", "")).casefold()
        if "ecobee" in manufacturer or advertised_model.startswith("eb-"):
            return True
    return False


def _has_raop(config: Any) -> bool:
    return config.get_service(Protocol.RAOP) is not None


def _filter_ecobees(configs: Iterable[Any]) -> list[Any]:
    return sorted(
        (config for config in configs if _is_ecobee(config) and _has_raop(config)),
        key=lambda config: (config.name.casefold(), str(config.address)),
    )


async def _discover(
    timeout: int, host: str | None = None, *, debug: bool = False
) -> list[Any]:
    configs = await pyatv.scan(
        asyncio.get_running_loop(),
        timeout=timeout,
        hosts=[host] if host else None,
        protocol={Protocol.AirPlay, Protocol.RAOP},
    )
    ecobees = _filter_ecobees(configs)
    if debug:
        print(
            f"Discovery ({host or 'multicast'}, {timeout}s): "
            f"{len(configs)} AirPlay/RAOP receivers, {len(ecobees)} Ecobees",
            file=sys.stderr,
        )
        for config in configs:
            if not _is_ecobee(config):
                status = "ignored: not identified as Ecobee"
            elif not _has_raop(config):
                status = "ignored: no RAOP service"
            else:
                status = "accepted"
            print(f"  {_device_summary(config)}: {status}", file=sys.stderr)
    return ecobees


def _looks_like_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def _volume(value: str) -> float:
    try:
        volume = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "volume must be a number from 0 to 100"
        ) from error
    if not 0 <= volume <= 100:
        raise argparse.ArgumentTypeError("volume must be from 0 to 100")
    return volume


def _udp_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("UDP port must be from 0 to 65535") from error
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError("UDP port must be from 0 to 65535")
    return port


def _device_summary(config: Any) -> str:
    return f"{config.name} ({config.address}, {_model_name(config)})"


def _choose_device(configs: Sequence[Any], selector: str | None) -> Any:
    if not configs:
        raise EcobeeAirplayError(
            "no Ecobee AirPlay receivers found; try the thermostat IP with --device"
        )

    if selector:
        selector_key = selector.casefold()
        matches = [
            config
            for config in configs
            if config.name.casefold() == selector_key
            or str(config.address).casefold() == selector_key
            or selector_key
            in {str(identifier).casefold() for identifier in config.all_identifiers}
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            choices = ", ".join(_device_summary(config) for config in matches)
            raise EcobeeAirplayError(
                f"device selector {selector!r} is ambiguous: {choices}; use an IP"
            )

        available = ", ".join(_device_summary(config) for config in configs)
        raise EcobeeAirplayError(
            f"no Ecobee matches {selector!r}; available receivers: {available}"
        )

    if len(configs) == 1:
        return configs[0]

    choices = ", ".join(_device_summary(config) for config in configs)
    raise EcobeeAirplayError(
        f"multiple Ecobees found: {choices}; select one with --device"
    )


def _normalize_source(value: str) -> str:
    if value.startswith(("http://", "https://")):
        return value

    path = Path(value).expanduser()
    if not path.is_file():
        raise EcobeeAirplayError(f"audio file does not exist: {value}")
    return str(path.resolve())


def _print_devices(configs: Sequence[Any]) -> None:
    if not configs:
        print("No Ecobee AirPlay receivers found.")
        return

    rows = [
        (config.name, str(config.address), _model_name(config)) for config in configs
    ]
    widths = [
        max(len(header), *(len(row[index]) for row in rows))
        for index, header in enumerate(("NAME", "ADDRESS", "MODEL"))
    ]
    print(f"{'NAME':<{widths[0]}}  {'ADDRESS':<{widths[1]}}  {'MODEL':<{widths[2]}}")
    for name, address, model in rows:
        print(f"{name:<{widths[0]}}  {address:<{widths[1]}}  {model:<{widths[2]}}")


async def _run_scan(args: argparse.Namespace) -> int:
    host = str(args.device) if args.device else None
    configs = await _discover(args.timeout, host=host, debug=args.debug)
    _print_devices(configs)
    if not configs:
        print(
            "Discovery can miss receivers. Retry with --timeout 15 --debug, "
            "or scan --device THERMOSTAT_IP to use unicast discovery.",
            file=sys.stderr,
        )
        if sys.platform == "darwin":
            print(
                "On macOS, check your terminal app's Local Network access in "
                "System Settings > Privacy & Security > Local Network.",
                file=sys.stderr,
            )
    return 0 if configs else 1


async def _run_play(args: argparse.Namespace) -> int:
    if not args.direct and args.service_config.is_file():
        return await asyncio.to_thread(_run_service_play, args)
    source = _normalize_source(args.source)
    host = args.device if args.device and _looks_like_ip(args.device) else None
    configs = await _discover(args.timeout, host=host, debug=args.debug)
    config = _choose_device(configs, args.device)

    print(f"Streaming {args.source!r} to {_device_summary(config)}...", file=sys.stderr)
    atv = await pyatv.connect(
        config,
        asyncio.get_running_loop(),
        protocol=Protocol.RAOP,
    )
    try:
        atv.settings.protocols.raop.timing_port = args.timing_port
        atv.settings.protocols.raop.control_port = args.control_port
        if args.volume is not None:
            await atv.audio.set_volume(args.volume)
        await atv.stream.stream_file(source)
    finally:
        await asyncio.gather(*atv.close())
    print("Playback finished.", file=sys.stderr)
    return 0


def _run_service_play(args: argparse.Namespace) -> int:
    config = json.loads(args.service_config.read_text())
    devices = config["devices"]
    matches = [
        ip for name, ip in devices.items()
        if args.device
        and (name.casefold() == args.device.casefold() or ip == args.device)
    ]
    if not args.device and len(devices) == 1:
        matches = list(devices.values())
    if len(matches) != 1:
        raise EcobeeAirplayError("select an approved service receiver with --device")
    if args.source.startswith(("http://", "https://")):
        raise EcobeeAirplayError(
            "service playback requires a local file; download audio first"
        )
    path = Path(_normalize_source(args.source))
    if not 0 < path.stat().st_size <= 8 * 1024 * 1024:
        raise EcobeeAirplayError(
            "service audio upload must be between 1 byte and 8 MiB"
        )
    endpoint = config["url"].rstrip("/") + "/play/" + matches[0]
    if args.volume is not None:
        endpoint += "?" + urlencode({"volume": args.volume})
    request = urllib.request.Request(
        endpoint, data=path.read_bytes(),
        headers={"Authorization": "Bearer " + config["token"],
                 "Content-Type": "application/octet-stream"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=75) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise EcobeeAirplayError(error.read().decode()) from None
    except urllib.error.URLError as error:
        raise EcobeeAirplayError(
            f"playback service unavailable: {error.reason}"
        ) from None
    if not result.get("transport_completed"):
        raise EcobeeAirplayError(
            "playback service did not confirm transport completion"
        )
    print(json.dumps(result))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ecobee-airplay",
        description="Discover Ecobee AirPlay receivers and stream audio to them.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="list Ecobee AirPlay receivers")
    scan.add_argument(
        "--debug",
        action="store_true",
        help="show discovery diagnostics and tracebacks on errors",
    )
    scan.add_argument(
        "-d",
        "--device",
        type=ipaddress.IPv4Address,
        help="thermostat IPv4 address; bypass multicast discovery",
    )
    scan.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="discovery timeout in seconds (default: 5)",
    )
    scan.set_defaults(handler=_run_scan)

    play = subparsers.add_parser("play", help="stream an audio file or URL")
    play.add_argument("source", help="local audio file or HTTP(S) URL")
    play.add_argument(
        "--debug",
        action="store_true",
        help="show discovery diagnostics and tracebacks on errors",
    )
    play.add_argument(
        "-d",
        "--device",
        default=os.getenv("ECOBEE_DEVICE") or os.getenv("ECOBEE_HOST"),
        help="exact Ecobee room name or IP (env: ECOBEE_DEVICE)",
    )
    play.add_argument(
        "--volume",
        type=_volume,
        metavar="0-100",
        help="set playback volume; omitted means leave it unchanged",
    )
    play.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="discovery timeout in seconds (default: 5)",
    )
    play.set_defaults(handler=_run_play)
    play.add_argument("--timing-port", type=_udp_port, default=0,
                      help="sender UDP timing port; 0 chooses an ephemeral port")
    play.add_argument("--control-port", type=_udp_port, default=0,
                      help="sender UDP control port; 0 chooses an ephemeral port")
    play.add_argument("--service-config", type=Path,
                      default=Path(os.getenv("ECOBEE_AIRPLAY_SERVICE_CONFIG") or
                                   Path.home() / ".config/ecobee-airplay/service.json"),
                      help="optional authenticated playback-service configuration")
    play.add_argument("--direct", action="store_true",
                      help="bypass configured service and stream from this machine")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return asyncio.run(args.handler(args))
    except KeyboardInterrupt:
        print("Playback interrupted.", file=sys.stderr)
        return 130
    # This is the CLI boundary, so dependency and network failures are concise.
    except Exception as error:
        if args.debug:
            raise
        print(f"error: {error}", file=sys.stderr)
        return 1
