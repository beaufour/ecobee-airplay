---
name: ecobee-airplay
description: Discover speaker-equipped Ecobee thermostats that expose AirPlay/RAOP and stream local files or audio URLs to them. Use for Ecobee arbitrary-audio playback, speaker capability checks, automations, or troubleshooting this repository's CLI; do not route ordinary HVAC-control tasks here.
---

# Ecobee AirPlay

Use the repository CLI to discover and stream audio to compatible Ecobee
thermostats over the local network.

## Workflow

1. Confirm which thermostat the user intends to address. Keep network probing
   scoped to devices and networks they authorized.
2. From the repository root, run `uv run ecobee-airplay scan`. If multicast
   discovery fails and the user knows the address, use that address directly
   with `--device` during playback.
3. When several receivers exist, select the exact room name or IP. Do not infer
   from an AirPlay name alone: Apple TVs and other speakers can share room
   names. The CLI filters for Ecobee model/manufacturer data.
4. Run `uv run ecobee-airplay play AUDIO --device TARGET`. Preserve the current
   volume unless the user explicitly asks to change it.
5. Treat a zero exit status as transport completion, then ask for or use an
   available real-world confirmation that the intended thermostat made sound.

Local files and HTTP(S) URLs are supported. Read `README.md` for setup and
troubleshooting, and `docs/research.md` when API background or protocol evidence
is relevant.

## Network troubleshooting

When a native playback service is configured in
`~/.config/ecobee-airplay/service.json`, normal `play` commands upload local
audio there. Prefer this configured path when direct transport is known to fail;
use `--direct` only for an intentional direct-network test. Service responses
confirm transport completion, not audible sound. Read the README's "Optional
native playback service" section for configuration and upload limits.

Direct-IP discovery bypasses multicast limitations, but an open TCP 7000 does
not guarantee playback. The receiver also needs to reach the sender's advertised
UDP timing and control ports, and the sender needs the receiver's negotiated
event and audio/control ports. See `README.md` under "Network requirements" for
the paths. Use `play --timing-port PORT --control-port PORT` to match an existing
relay or forwarding rule; the default `0` chooses ephemeral sender ports.

If initial setup succeeds but audio-stream `SETUP` returns `400`, check the UDP
return paths before concluding that playback requires the same subnet. A
setup-only experiment with pyatv 0.18.0 succeeded through a narrow timing/control
relay while retaining the container's original RTSP URL address; changing the
URL alone failed. This verifies session setup, not audible playback through NAT.

Prefer destination-scoped routing or relays for the needed ports. Do not infer
that a discovery failure or `400` requires general host networking or broad LAN
access. Read `docs/research.md` for the experiment and distinguish discovery,
session setup, transport completion, and confirmed sound when reporting results.

## Direct fallback

If the repository CLI is unavailable but `uvx` can be used, scan and play with
the underlying client:

```sh
uvx --from pyatv atvremote --scan-protocols raop scan
uvx --from pyatv atvremote \
  --scan-hosts THERMOSTAT_IP \
  --scan-protocols raop \
  stream_file=/path/to/audio.mp3
```

Verify that scan output identifies an Ecobee `EB-*` model before playing. Do
not substitute the Ecobee cloud API: its audio object configures volume and
voice settings but exposes no arbitrary-media playback action.
