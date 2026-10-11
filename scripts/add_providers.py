#!/usr/bin/python3
"""Add verified-working providers to Hypnotix (org.x.hypnotix.providers).

Format per entry: name:::type:::url:::username:::password:::epg
"""
from gi.repository import Gio

existing = Gio.Settings.new("org.x.hypnotix").get_strv("providers")
print("BEFORE (%d):" % len(existing))
for e in existing:
    print("  -", e)

new_entries = [
    # name, url  (all of these were verified with Hypnotix's own Manager code)
    ("Free-TV CDN",    "https://cdn.jsdelivr.net/gh/free-TV/IPTV@master/playlist.m3u8"),
    ("IPTV-ORG-ZH",    "https://iptv-org.github.io/iptv/languages/zho.m3u"),
    ("IPTV-ORG-CN",    "https://iptv-org.github.io/iptv/countries/cn.m3u"),
    ("IPTV-ORG-HK",    "https://iptv-org.github.io/iptv/countries/hk.m3u"),
    ("IPTV-ORG-TW",    "https://iptv-org.github.io/iptv/countries/tw.m3u"),
    ("IPTV-ORG-SPORTS","https://iptv-org.github.io/iptv/categories/sports.m3u"),
    ("IPTV-ORG-MOVIES","https://iptv-org.github.io/iptv/categories/movies.m3u"),
]

have = {e.split(":::")[0] for e in existing}
added = []
for name, url in new_entries:
    if name in have:
        print("SKIP  %-16s already present" % name)
        continue
    added.append("%s:::url:::%s:::::::::" % (name, url))

result = existing + added
s = Gio.Settings.new("org.x.hypnotix")
s.set_strv("providers", result)

print("\nADDED (%d):" % len(added))
for a in added:
    print("  +", a)

print("\nAFTER (%d):" % len(s.get_strv("providers")))
for e in s.get_strv("providers"):
    print("  *", e)
