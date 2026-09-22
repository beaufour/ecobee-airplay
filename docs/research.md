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

## Security observation

The tested receiver accepted audio from any host with LAN reachability, without
pairing or an AirPlay password. This is convenient for automation but means
that untrusted clients on the same reachable network could also attempt
playback. Network segmentation is the practical control if the thermostat
offers no UI to disable or protect AirPlay.
