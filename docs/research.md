# Investigation notes

## Result

Arbitrary local audio playback works over AirPlay's Remote Audio Output
Protocol (RAOP). The successful test sent a generated MP3 from a Mac directly
to an Ecobee `EB-STATE5` on the LAN. The thermostat played it aloud, and the
receiver required neither pairing nor a password.

Validated on September 22, 2026, with firmware `p20.4.8.70908`.

## Official Ecobee API

The [Ecobee API introduction](https://www.ecobee.com/home/developer/api/introduction/index.shtml)
describes a cloud HTTP API for reading and updating thermostat data. Its
[`Thermostat` object](https://developer.ecobee.com/home/developer/api/documentation/v1/objects/Thermostat.shtml)
has an `audio` configuration object, and
[`Selection`](https://developer.ecobee.com/home/developer/api/documentation/v1/objects/Selection.shtml)
supports `includeAudio`.

The documented audio fields configure:

- playback volume
- microphone enabled/privacy state
- alert volume
- key-click volume
- compatible voice engines

There is no documented media URL, byte stream, queue, transport control, or
playback action. `sendMessage` creates a thermostat alert, not arbitrary audio.
The official cloud API is therefore not the playback path.

## Other apparent routes

- Spotify Connect works, but selects Spotify-hosted content; it is not a
  general local-file transport.
- Alexa can address the thermostat as an Alexa endpoint. Community Home
  Assistant answers commonly suggest
  [`alexa_media_player`](https://github.com/alandtse/alexa_media_player) for
  announcements or media. That route depends on Amazon account/cloud behavior
  and does not expose the speaker locally.
- A recent [community report](https://www.reddit.com/r/ecobee/comments/1s6fqed/wth_ecobee_is_an_airplay_destination_for_spotify/)
  observed Ecobee as an AirPlay destination and confirmed audio from non-Spotify
  apps. That was the useful clue; the device investigation below established
  the protocol and tested a local MP3 end to end.

## Local discovery

The thermostat was first identified by its Ecobee-assigned MAC prefix, then by
Bonjour. It advertised these services:

```text
Guest Room._airplay._tcp.local. -> ecobee-vulcan-2.local.:7000
1DDE...@Guest Room._raop._tcp.local. -> ecobee-vulcan-2.local.:7000
```

The TXT records identified:

```text
manufacturer=ecobee Inc.
model=EB-STATE5
am=EB-STATE5
```

The household also had an Apple TV with a nearly identical room name. Checking
the model/manufacturer and resolved host prevented testing the wrong device.

Useful macOS inspection commands are:

```sh
dns-sd -B _airplay._tcp local.
dns-sd -B _raop._tcp local.
dns-sd -L 'Room Name' _airplay._tcp local.
```

[`pyatv`](https://pyatv.dev/) independently reported AirPlay and RAOP on port
7000, no credentials, no password, and no required pairing. Its
[`atvremote` streaming documentation](https://pyatv.dev/documentation/atvremote/#streaming)
documents `stream_file=sample.mp3`; RAOP is specifically the audio-streaming
protocol.

## End-to-end test

A short spoken AIFF was generated locally, converted to MP3, and sent with:

```sh
uvx --from pyatv atvremote \
  --scan-hosts THERMOSTAT_IP \
  --scan-protocols raop \
  stream_file=/tmp/ecobee-test.mp3
```

The command exited successfully after the stream completed, and a person in the
home confirmed hearing the spoken MP3 from the thermostat. This repository's
CLI wraps the same `pyatv` API with Ecobee-only discovery and safer target
selection.

## Network return-path experiment

On October 2, 2026, setup-only probes compared a direct LAN sender with a
NAT-connected container against an Ecobee `EB-STATE5`. Both used pyatv 0.18.0.
The probes stopped after audio-stream setup, before `RECORD`, audio-source
decoding, volume changes, or audio transmission. Successful sessions were
explicitly torn down.

| Sender configuration | Initial session SETUP | Audio-stream SETUP |
|---|---|---|
| Direct LAN sender | 200 | 200 |
| Container, original RTSP session URL | 200 | 400 |
| Container, LAN host address substituted in RTSP session URL | 200 | 400 |
| Container, LAN host address in URL plus UDP timing/control relay | 200 | 200 |
| Container, original URL plus UDP timing/control relay | 200 | 200 |

The logged audio format and setup options matched; session identifiers, UDP
ports, and per-session encryption material varied. The relay used fixed sender
ports 47000 (timing) and 47001 (control), listened on the LAN host's address,
accepted packets only from the selected thermostat, and forwarded them to the
container. It returned container replies through the same LAN-side socket.
Both temporary relays closed after each probe; no persistent network settings
were changed.

The successful rewritten-URL probe relayed nine 32-byte timing requests and
nine replies. The successful original-URL probe relayed three timing requests
and three replies. No control-port packets were observed during either probe.
Thus, receiver-initiated timing traffic and its replies were demonstrated, while
the separate necessity of a control relay was not tested. Audio transport and
audible playback through the relay remain unverified.

These results show that the private address in the RTSP URL did not prevent
setup on this receiver. Providing the UDP return path resolved the observed
failure. A `400` alone does not prove this cause on another receiver or firmware.

The general requirements are discovery (multicast or direct IP), outbound
session/event connections, receiver-initiated timing requests with replies,
bidirectional control traffic, and outbound audio to negotiated receiver ports.
They can be provided through routing or narrowly scoped relays without placing
the sender on the same subnet or enabling general host networking. See
[Network requirements](../README.md#network-requirements) for the path table.

Relevant pyatv implementation sources:

- [RTSP session URL generation](https://github.com/postlund/pyatv/blob/v0.18.0/pyatv/support/rtsp.py)
- [Sender UDP timing/control sockets and audio transport](https://github.com/postlund/pyatv/blob/v0.18.0/pyatv/protocols/raop/stream_client.py)
- [AirPlay 2 setup and negotiated event/audio/control ports](https://github.com/postlund/pyatv/blob/v0.18.0/pyatv/protocols/raop/protocols/airplayv2.py)

## Security observation

The tested receiver accepted audio from any host with LAN reachability, without
pairing or an AirPlay password. This is convenient for automation but means
that untrusted clients on the same reachable network could also attempt
playback. Network segmentation is the practical control if the thermostat
offers no UI to disable or protect AirPlay.
