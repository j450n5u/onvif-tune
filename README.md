# onvif-tune

Read and change a security camera's video encoder settings — codec and
bitrate — from the command line, over plain ONVIF. No vendor app, no
dependencies, one file.

```
$ ONVIF_PASS=... python3 onvif_tune.py 10.0.0.50 show
token=main  enc=H264 2688x1520 fps=25 bitrate=6144
token=minor enc=H264 848x480   fps=25 bitrate=512
token=jpeg  enc=JPEG 640x360   fps=1  bitrate=512

$ ONVIF_PASS=... python3 onvif_tune.py 10.0.0.50 set main H265 3072
OK enc=H265 bitrate=3072
```

## Why

A batch of new cameras arrived at the factory. Each one shipped with H.264 at
maximum bitrate — fine for one camera, a storage disaster for a whole fleet.
The vendor's phone app changes encoder settings one camera at a time, several
taps each, and the web UI isn't better.

But every ONVIF camera answers SOAP on `/onvif/service`. This tool speaks the
Media2 profile directly: list the encoder configurations, see what the camera
supports, and set codec + bitrate in one command. Switching a fleet to
H.265 at a sane bitrate becomes a shell loop.

Tested on TP-Link VIGI cameras; the Media2 calls are standard ONVIF, so most
reasonably modern IP cameras should answer.

## Usage

```
onvif_tune.py <ip> show                              # list encoder configs
onvif_tune.py <ip> options <token>                   # supported codecs + bitrate range
onvif_tune.py <ip> set <token> <H264|H265> <kbps>    # change codec/bitrate
```

Credentials via `ONVIF_USER` / `ONVIF_PASS` environment variables, or
`--user` / `--password` flags. `ONVIF_USER` defaults to `admin`.

## Notes

- **`set` preserves everything else.** ONVIF's `SetVideoEncoderConfiguration`
  replaces the whole encoder block, not just the fields you send — so the tool
  fetches the current config first and carries resolution, framerate, GOP and
  quality through unchanged. Only the codec and bitrate move.
- **Every write is read back.** After a `set`, the tool re-queries the camera
  and prints what it actually stored. If the camera silently clamped or
  refused the value, you see it immediately.
- Auth is WS-UsernameToken digest (the SHA-1 nonce dance), which is what
  cameras actually expect on the ONVIF endpoint — HTTP basic auth will not
  work there.
- A camera typically applies encoder changes live, but some briefly drop the
  RTSP stream while the encoder restarts. Recorders reconnect on their own.

Python 3.8+. No dependencies.

## License

MIT
