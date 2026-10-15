#!/usr/bin/python3
"""Verify Hypnotix providers actually load channels through Hypnotix's own Manager.

Runs against the configured org.x.hypnotix.providers list. Any extra arguments
are treated as provider strings (name:::type:::url:::user:::pass:::epg) and
verified in the same pass, so a playlist can be checked before it is installed.

    python3 scripts/verify_news.py
    python3 scripts/verify_news.py \
        "News:::local:::file://$PWD/playlists/news.m3u:::::::::"
"""
import sys, os, re, subprocess, pathlib

sys.path.insert(0, "/usr/lib/hypnotix")
import gi
gi.require_version("GLib", "2.0")
from gi.repository import GLib
import common

REPO = pathlib.Path(__file__).resolve().parent.parent
M3U = os.environ.get("NEWS_M3U", str(REPO / "playlists" / "news.m3u"))
NEWS_PROVIDER = "News:::local:::file://%s:::::::::" % M3U

def configured_providers():
    out = subprocess.run(
        ["dconf", "dump", "/org/x/hypnotix/"], capture_output=True, text=True
    ).stdout
    m = re.search(r"providers=\[(.*)\]\n", out, re.S)
    if not m:
        return []
    return [x.strip().strip("'") for x in m.group(1).split("', '")]

class FakeSettings:
    def get_string(self, k):
        return {"user-agent": "Mozilla/5.0", "http-referer": ""}.get(k, "")

mg = common.Manager(FakeSettings())
ok = fail = 0

for pi in configured_providers() + sys.argv[1:]:
    parts = pi.split(":::")
    if len(parts) != 6:
        print("BAD FORMAT  %s" % pi); fail += 1; continue
    p = common.Provider(parts[0], pi)
    if not mg.get_playlist(p):
        print("GET-FAIL    %-18s %s" % (p.name, p.url[:60])); fail += 1; continue
    if not mg.check_playlist(p):
        print("CHECK-FAIL  %-18s path=%s" % (p.name, p.path)); fail += 1; continue
    mg.load_channels(p)
    n = len(p.channels) + len(p.movies) + len(p.series)
    print("OK          %-18s ch=%-5d movies=%-4d series=%-4d total=%d"
          % (p.name, len(p.channels), len(p.movies), len(p.series), n))
    ok += 1
    if p.name == "News":
        byg = {}
        for c in p.channels:
            byg.setdefault(c.group_title or "(none)", []).append(c)
        print("   --- News groups ---")
        for g, chs in byg.items():
            print("   [%s] %d channels" % (g, len(chs)))
            for c in chs:
                print("     %-26s %s" % (c.name, (c.url or "")[:58]))

print("\n=== %d ok / %d fail ===" % (ok, fail))
sys.exit(1 if fail else 0)
