# hypnotix

Setup notes, a curated news playlist, and tooling for getting
[Hypnotix](https://hypnotix.org) TV working on a Mac Mini running Ubuntu
(Cinnamon).

Collected over an Oct 2026 troubleshooting session. Everything here was validated
against this box's actual `libmpv 0.37` — Hypnotix's real playback engine — not
just "returns HTTP 200".

## Layout

```
playlists/
  news.m3u                  Curated news playlist, every channel playback-verified
scripts/
  add_providers.py          Writes verified providers into org.x.hypnotix.providers
  verify_providers.py       Tests candidate providers with Hypnotix's own Manager code
  verify_news.py            Verifies configured providers + any passed in as args
  classify.py               Per-stream libmpv decode test, proxy vs direct comparison
  mpv_all.py                Authoritative playback matrix (news + YouTube live + baselines)
  playback_test.py          libmpv probe, requires both video and audio format + time advancing
  yttest.py                 Single YouTube-live stream probe with mpv log dump
  durtest.py                YouTube channel /live vs @handle/live URL forms
  ffcheck.sh                ffmpeg/ffprobe batch playback check (CSV: name<TAB>url)
  check.sh                  curl-only playlist HTTP/size/channel-count check
  t.sh                      curl-only quick segment-count check
  diag.py  mpvopt.py        mpv log dump / option-sensitivity probes
  init_test.py              Can libmpv even init under Hypnotix's flag set?
  zbdstest.py               Single-stream probe with per-tick property logging
```

## Quick start

```bash
# install what the scripts assume
sudo apt install hypnotix yt-dlp ffmpeg curl

# check the news playlist is healthy before installing it
python3 scripts/verify_news.py

# install the public provider set
python3 scripts/add_providers.py

# then verify the channels Hypnotix actually loads
python3 scripts/verify_news.py

# add the news playlist as a local provider
python3 - <<'EOF'
from gi.repository import Gio
s = Gio.Settings.new("org.x.hypnotix")
p = s.get_strv("providers")
n = "News:::local:::file:///path/to/playlists/news.m3u:::::::::"
if n not in p:
    s.set_strv("providers", p + [n])
EOF
```

Always dump dconf before touching it — dconf has no undo:

```bash
dconf dump /org/x/hypnotix/ > /tmp/hypnotix_backup_$(date +%Y%m%d_%H%M%S).txt
```

The mpv scripts write their logs into a scratch dir, defaulting to `/tmp/opencode`:

```bash
mkdir -p /tmp/opencode
```

`scripts/verify_news.py` resolves `playlists/news.m3u` relative to the checkout,
or takes `NEWS_M3U=/path/to/file.m3u` to point somewhere else.

## Things that actually matter on this box

**Use `watch?v=` for YouTube live, not `/live`.** Hypnotix ships `mpv 0.37` with
`ytdl_hook`, which resolves `https://www.youtube.com/watch?v=<id>` fine but fails
on the `https://www.youtube.com/channel/<ID>/live` form. Channel `/live` URLs are
useful for *discovering* the current live video ID, useless for *playing* it.

**"HTTP 200" is not "plays".** A lot of news HLS CDNs answer the master playlist
but this box's local HTTP proxy (`127.0.0.1:3067`) cuts the `.ts` segment
fetches, so mpv stalls. `scripts/classify.py` runs every stream both through the
proxy and with it unset so you can tell real breakage from local-environment
breakage. Channels in that state are left commented out in `news.m3u`.

**`mpv 0.37` exposes only legacy property names.** Use hyphenated
`m._get_property("video-format")` / `"time-pos"` — the camelCase shortcuts raise.
`audio-format` reports `"no"` on this build even when audio plays fine; confirm
with `audio-params` and the log line `AAC 2ch 48000Hz` instead.

**Hypnotix provider format is positional.** `name:::type:::url:::user:::pass:::epg`
— six fields, empty ones still need their `:`. `type` is `url` or `local`; for
`local` the `url` field is a `file://` path and Hypnotix strips the prefix.

## Not included

Nothing here contains credentials, tokens or secrets. Stream URLs are public
broadcast endpoints.
