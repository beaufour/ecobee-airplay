# ecobee-airplay

Play arbitrary audio files on compatible Ecobee thermostats over the local
network. No Ecobee developer key, Alexa account, Spotify account, or cloud API
is involved.

The trick is that some speaker-equipped Ecobee models advertise themselves as
AirPlay/RAOP receivers. This project discovers those receivers, filters out
same-named Apple TVs and other AirPlay devices, and streams audio with
[`pyatv`](https://pyatv.dev/).

Validated on an `EB-STATE5` running firmware `p20.4.8.70908`. Other models
should work if they appear in `scan`; please report successes or failures.

## Quick start

Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/), clone
this repository, and run:

```sh
uv run ecobee-airplay scan
uv run ecobee-airplay play song.mp3 --device "Guest Room"
```

An IP address also works and bypasses multicast discovery across VLANs:

```sh
uv run ecobee-airplay play song.mp3 --device 192.168.1.42
```

The first command can find several Ecobees. The second requires an exact room
name or address when more than one is available, reducing the chance of audio
playing in the wrong room.

To use the convenience wrapper:

```sh
./play-ecobee-audio song.mp3 --device "Guest Room"
```

Local paths and HTTP(S) audio URLs are accepted. The receiver's current volume
is preserved unless `--volume` is supplied:

```sh
uv run ecobee-airplay play https://example.com/chime.mp3 \
  --device "Guest Room" \
  --volume 35
```

Set a default target for automations:

```sh
export ECOBEE_DEVICE="Guest Room"
uv run ecobee-airplay play notification.mp3
```

Run `uv run ecobee-airplay --help` for all options.

## Why this works

Ecobee's documented cloud API exposes audio configuration—playback volume,
alert and key-click volume, microphone state, and voice-engine metadata—but no
media transport or “play this URL/file” function. Spotify Connect is restricted
to Spotify content, and the Alexa route requires an account and cloud service.

On a compatible thermostat, Bonjour advertises `_airplay._tcp` and
`_raop._tcp` on port 7000. RAOP is AirPlay's audio transport. `pyatv` already
implements discovery, decoding, transcoding, volume control, and RAOP
streaming, so this project uses its public API rather than reimplementing the
protocol.

See [the investigation notes](docs/research.md) for the API review, community
prior art, discovery records, and the end-to-end validation.

## Requirements and compatibility

- Python 3.11 or newer
- The sender and thermostat must have the bidirectional network paths described
  below; a shared LAN is the simplest arrangement, but is not required
- Multicast DNS for name-based discovery, or the thermostat IP address
- A thermostat that advertises an Ecobee AirPlay/RAOP receiver

`pyatv` supports common inputs including MP3, WAV, OGG, and Vorbis, plus
HTTP(S) streams. AirPlay behavior is based on reverse-engineered protocols and
can change with firmware updates.

### Network requirements

An open TCP port 7000 is necessary but does not establish that audio playback
can work. Session setup also advertises UDP timing and control ports on the
sender, and the thermostat must be able to reach those ports and receive replies.

| Purpose | Required network path |
|---|---|
| Discovery | Multicast DNS (UDP 5353) for name-based discovery, or direct-IP unicast discovery with `--device IP` |
| Session setup | Sender to thermostat TCP 7000 on the tested model |
| AirPlay 2 event channel | Sender to the thermostat's TCP event port returned during setup |
| Timing | Thermostat to the sender's advertised UDP timing port, with replies back to the thermostat |
| Control / retransmission | Bidirectional UDP between the sender's advertised control port and the thermostat's negotiated control endpoint |
| Audio | Sender to the thermostat's UDP audio port returned during setup |

Across NAT, containers, or filtered subnets, explicitly route or relay the UDP
return paths. An outbound TCP connection does not make receiver-initiated UDP
requests reachable. If forwarding ports, the externally reachable timing and
control ports must match the ports advertised during setup, or the advertised
values must be translated accordingly. Rewriting an IP address in the RTSP
session URL does not create these paths.

With pyatv 0.18.0, sender ports are configurable through
`settings.protocols.raop.timing_port` and
`settings.protocols.raop.control_port`; their default value of `0` selects
ephemeral ports. The CLI exposes them as `play --timing-port` and
`play --control-port`. Choose fixed ports to permit narrow forwarding rules:

```sh
uv run ecobee-airplay play audio.mp3 --device THERMOSTAT_IP \
  --timing-port 47000 --control-port 47001
```

Ports 47000 and 47001 were used in the setup-only experiment; they are example
choices, not protocol-assigned ports.

Limit any forwarding or relay to the selected thermostat addresses and required
ports. General host networking or access to the whole LAN is not required.
See [the network experiment](docs/research.md#network-return-path-experiment)
for the verified setup results and their limits.

### Optional native playback service

If full audio routing from the sender is unavailable, playback can be delegated
to an authenticated native service. The CLI looks for
`~/.config/ecobee-airplay/service.json`, or the path supplied by
`--service-config` or `ECOBEE_AIRPLAY_SERVICE_CONFIG`. With an existing service
configuration, normal `play` commands upload audio instead of streaming locally.
`--direct` explicitly bypasses this mode.

Example client configuration (keep the token private):

```json
{
  "url": "http://127.0.0.1:47002",
  "token": "SERVICE_TOKEN",
  "devices": {"Guest Room": "192.0.2.10"}
}
```

The service must expose `POST /play/IPv4` accepting raw audio bytes, bearer
authentication, and an optional `volume` query parameter, and return JSON with
`transport_completed: true`. Use a service address reachable from the caller;
the example loopback address applies when caller and service share a host.
The service must enforce its own receiver allowlist rather than trusting this
client file. Service mode uploads local files up to 8 MiB; download URL sources
on the caller first. It preserves volume unless requested and propagates service
limits and errors. Sender timing/control port options apply only to direct mode.
A successful response is transport completion, not confirmation of audible sound.

## Troubleshooting

No devices found:

- The message means discovery returned no matching receivers, not that there
  are no Ecobees on the network. Run `uv run ecobee-airplay scan --timeout 15
  --debug` to see whether discovery found any AirPlay/RAOP receivers and why
  devices were ignored.
- Confirm discovery can reach the thermostat; multicast may not cross subnet
  or container boundaries even when direct-IP connections work.
- Try `uv run ecobee-airplay scan --device 192.168.1.42 --debug` with the
  thermostat's IP; this uses unicast discovery and works across some networks
  that block multicast DNS. `play --device` also accepts an IP.
- On macOS, enable Local Network access for the terminal app under System
  Settings > Privacy & Security > Local Network, then retry the scan.
- On macOS, inspect advertisements directly with
  `dns-sd -B _raop._tcp local.`.
- Confirm the device model begins with `EB-` in the scan result. The CLI
  intentionally ignores Apple TVs, HomePods, and other AirPlay receivers.

Playback fails:

- First try a short MP3 or WAV file.
- Check that TCP port 7000 is reachable from the sender.
- If discovery and initial setup work but audio-stream `SETUP` returns `400 Bad
  Request`, check the receiver-initiated UDP timing path and replies. On the
  tested receiver, a narrow timing/control relay resolved this failure without
  changing the RTSP session URL. Other causes of `400` remain possible.
- Run with `--debug` for the underlying exception and traceback.
  Debug protocol logs can contain session encryption keys; redact them before
  sharing logs.
- If the scan says the receiver needs pairing or a password, this CLI does not
  currently automate that setup. The tested Ecobee required neither.

Security note: the tested thermostat accepted RAOP playback from the local LAN
without pairing or a password. Treat access to the IoT network accordingly.

## Agent skill

The reusable skill lives in [`skills/ecobee-airplay`](skills/ecobee-airplay).
Copy that folder into your agent's skill directory, or point an agent that
supports `SKILL.md` at it. The skill teaches an agent how to discover a target,
avoid same-name non-Ecobee receivers, preserve volume, play audio, and verify
the result.

## Development

```sh
uv sync
uv run pytest
uv run ruff check .
```

The live smoke test is intentionally separate because it plays sound on a real
device:

```sh
uv run ecobee-airplay scan
uv run ecobee-airplay play test.mp3 --device "Room Name"
```

Released under the [MIT License](LICENSE).
