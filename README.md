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
- The sender and thermostat must be able to reach each other on the LAN
- Multicast DNS for name-based discovery, or the thermostat IP address
- A thermostat that advertises an Ecobee AirPlay/RAOP receiver

`pyatv` supports common inputs including MP3, WAV, OGG, and Vorbis, plus
HTTP(S) streams. AirPlay behavior is based on reverse-engineered protocols and
can change with firmware updates.

## Troubleshooting

No devices found:

- Confirm the thermostat and computer are on the same LAN.
- Try its IP with `--device`; this uses unicast discovery and works across some
  networks that block multicast DNS.
- On macOS, inspect advertisements directly with
  `dns-sd -B _raop._tcp local.`.
- Confirm the device model begins with `EB-` in the scan result. The CLI
  intentionally ignores Apple TVs, HomePods, and other AirPlay receivers.

Playback fails:

- First try a short MP3 or WAV file.
- Check that TCP port 7000 is reachable from the sender.
- Run with `--debug` for the underlying exception and traceback.
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
