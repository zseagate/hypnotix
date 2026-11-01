#!/usr/bin/env python3
"""Discover current YouTube live-stream IDs and regenerate playlist.m3u.

Run locally or from GitHub Actions. Never fails the job: channels that cannot
be resolved are skipped and recorded in status.json.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHANNELS = os.path.join(ROOT, "channels.json")
PLAYLIST = os.path.join(ROOT, "playlist.m3u")
STATUS = os.path.join(ROOT, "status.json")
YTDLP = os.environ.get("YTDLP_BIN", "yt-dlp")
TIMEOUT = int(os.environ.get("YTDLP_TIMEOUT", "45"))
RETRIES = int(os.environ.get("YTDLP_RETRIES", "2"))
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "25"))
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
VIDEO_ID_RE = re.compile(r'"videoId":"([A-Za-z0-9_-]{11})"')


def http_get(url, timeout=HTTP_TIMEOUT):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def run_ytdlp(url, timeout=TIMEOUT):
    for attempt in range(RETRIES + 1):
        try:
            p = subprocess.run(
                [YTDLP, "-J", url],
                capture_output=True, text=True, timeout=timeout,
            )
            if p.stdout.strip():
                return json.loads(p.stdout)
        except subprocess.TimeoutExpired:
            pass
        except json.JSONDecodeError:
            pass
        time.sleep(2 * (attempt + 1))
    return None


def is_live_html(video_id):
    """True/False when the watch page is readable, None when it is not."""
    try:
        html = http_get("https://www.youtube.com/watch?v=%s" % video_id)
    except Exception:
        return None
    return '"isLive":true' in html


def oembed(video_id):
    try:
        raw = http_get("https://www.youtube.com/oembed?url="
                       "https://www.youtube.com/watch?v=%s&format=json" % video_id)
        return json.loads(raw)
    except Exception:
        return {}


def channel_handle(channel_id):
    try:
        html = http_get("https://www.youtube.com/channel/%s" % channel_id)
    except Exception:
        return None
    m = re.search(r'"canonicalBaseUrl":"(/@[^"]+)"', html)
    return m.group(1) if m else None


def scrape_live(channel_id):
    """Resolve the live id from the channel page when yt-dlp is blocked.

    YouTube answers yt-dlp on CI runners with "Sign in to confirm you're not a
    bot", which used to leave every channel on its cached (often dead) id.
    The plain watch/channel pages still work, so fall back to reading them.
    Candidate videos can belong to other channels (recommended shelf), so the
    oEmbed author must match this channel's handle.
    """
    try:
        html = http_get("https://www.youtube.com/channel/%s/live" % channel_id)
    except Exception:
        return None, None

    handle = channel_handle(channel_id)
    ids = []
    for m in VIDEO_ID_RE.finditer(html):
        if m.group(1) not in ids:
            ids.append(m.group(1))

    for vid in ids[:8]:
        try:
            watch = http_get("https://www.youtube.com/watch?v=%s" % vid)
        except Exception:
            continue
        if '"isLive":true' not in watch:
            continue
        info = oembed(vid)
        author = (info.get("author_url") or "").replace("https://www.youtube.com", "")
        # Unknown author is not good enough: the /live page also lists other
        # channels' live streams, and oEmbed is anonymous/limited for some.
        if not handle or not author or author != handle:
            continue
        return vid, info.get("title", "")
    return None, None


def resolve_live(channel_id):
    """Return current live video id for a channel, or None.

    NOTE: /live works for DISCOVERY but not for PLAYBACK. Hypnotix must be
    given https://www.youtube.com/watch?v=<id> -- the /live form fails in mpv.
    """
    data = run_ytdlp("https://www.youtube.com/channel/%s/live" % channel_id)
    if data and data.get("id") and data.get("is_live"):
        return data["id"], data.get("title", "")
    return scrape_live(channel_id)


def hls_liveness(url):
    """Return (state, reason) for an HLS entry.

    state is "live", "dead" (definitively not live: ENDLIST or a live edge
    older than an hour) or "unknown" (network/format problem). Frozen slates
    such as CNN's cnn_slate endpoint advertise an ENDLIST and a stale
    PROGRAM-DATE-TIME, so checking HTTP 200 alone is not enough.
    """
    body = http_get(url)
    if "#EXT-X-STREAM-INF" in body:
        variant = None
        lines = body.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("#EXT-X-STREAM-INF"):
                for cand in lines[i + 1:]:
                    if cand.strip() and not cand.startswith("#"):
                        variant = cand.strip()
                        break
            if variant:
                break
        if variant:
            body = http_get(urllib.parse.urljoin(url, variant))

    if "#EXT-X-ENDLIST" in body:
        return "dead", "playlist has EXT-X-ENDLIST (finite/VOD loop)"

    pdts = re.findall(r"PROGRAM-DATE-TIME:([^\r\n]+)", body)
    if pdts:
        try:
            edge = datetime.fromisoformat(pdts[-1].replace("Z", "+00:00"))
            if len(pdts) == 1:
                window = sum(float(x) for x in re.findall(r"#EXTINF:([\d.]+)", body))
                edge = datetime.fromtimestamp(edge.timestamp() + window, timezone.utc)
            age = (datetime.now(timezone.utc) - edge).total_seconds()
            if age > 3600:
                return "dead", "live edge is %d min behind" % (age // 60)
        except ValueError:
            pass
    return "live", "ok"


def build(config, prev_status):
    rows, resolved, failed = [], [], []
    last_live = {c["name"]: c.get("live_id") for c in prev_status.get("channels", [])}

    for ch in config["channels"]:
        name, group = ch["name"], ch["group"]
        if ch["kind"] == "youtube":
            vid, title = resolve_live(ch["channel_id"])
            if vid:
                rows.append((name, group, "https://www.youtube.com/watch?v=%s" % vid))
                resolved.append({"name": name, "channel_id": ch["channel_id"],
                                 "live_id": vid, "title": title})
                print("OK      %-22s %s" % (name, vid))
            else:
                vid = last_live.get(name) or ch.get("last_live_id")
                if vid:
                    src = "last run" if name in last_live else "pinned"
                    still = is_live_html(vid)
                    entry = {"name": name, "channel_id": ch["channel_id"],
                             "live_id": vid, "stale": True, "source": src}
                    if still is False:
                        entry["dead"] = True
                        print("DEAD    %-22s %s  (cached %s stream has ended)"
                              % (name, vid, src))
                    else:
                        print("CACHED  %-22s %s  (no live found, using %s)"
                              % (name, vid, src))
                    rows.append((name, group, "https://www.youtube.com/watch?v=%s" % vid))
                    resolved.append(entry)
                else:
                    print("MISS    %-22s %s" % (name, ch["channel_id"]))
                    failed.append({"name": name, "channel_id": ch["channel_id"]})
        else:
            rows.append((name, group, ch["url"]))
            entry = {"name": name, "kind": "hls", "url": ch["url"]}
            try:
                state, reason = hls_liveness(ch["url"])
            except Exception as e:
                state, reason = "unknown", str(e)[:120]
            if state == "dead":
                entry["dead"] = True
                entry["reason"] = reason
                print("DEAD    %-22s %s" % (name, reason))
            else:
                print("OK      %-22s %s (%s)" % (name, "hls", state))
            resolved.append(entry)

    # keep groups contiguous
    order = {}
    for name, group, _ in rows:
        order.setdefault(group, 0)
        order[group] += 1
    return rows, resolved, failed


def write_playlist(rows, config):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "#EXTM3U",
        "# Generated by hypnotix-news %s" % now,
        "# Do not edit: regenerated by GitHub Actions. Edit channels.json instead.",
        "# YouTube entries use watch?v= URLs; the /live form does not play in mpv.",
        "",
    ]
    for name, group, url in rows:
        lines.append('#EXTINF:-1 tvg-name="%s" group-title="%s",%s' % (name, group, name))
        lines.append(url)
    lines.append("")
    lines.append("# ---- optional: verified reachable, may be blocked by local proxy ----")
    for ch in config.get("optional", []):
        lines.append('#EXTINF:-1 tvg-name="%s" group-title="%s",%s'
                     % (ch["name"], ch["group"], ch["name"]))
        lines.append("#" + ch["url"])
    with open(PLAYLIST, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    config = json.load(open(CHANNELS, encoding="utf-8"))
    prev_status = {}
    if os.path.exists(STATUS):
        try:
            prev_status = json.load(open(STATUS, encoding="utf-8"))
        except Exception:
            pass

    rows, resolved, failed = build(config, prev_status)
    write_playlist(rows, config)

    status = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": len(rows),
        "resolved": len(resolved),
        "failed": len(failed),
        "channels": resolved,
        "misses": failed,
    }
    json.dump(status, open(STATUS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print("\n=== %d channels written to playlist.m3u (%d missed) ===" % (len(rows), len(failed)))
    if failed:
        print("missed:", "; ".join(f["name"] for f in failed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
