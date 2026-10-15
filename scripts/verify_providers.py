#!/usr/bin/python3
import sys, os
sys.path.insert(0, "/usr/lib/hypnotix")

from common import Manager, Provider

CANDIDATES = [
    ("Free-TV",            "url", "https://fastly.jsdelivr.net/gh/free-TV/IPTV@master/playlist.m3u8"),
    ("IPTV-ORG-ZH",        "url", "https://iptv-org.github.io/iptv/languages/zho.m3u"),
    ("IPTV-ORG-CN",        "url", "https://iptv-org.github.io/iptv/countries/cn.m3u"),
    ("IPTV-ORG-HK",        "url", "https://iptv-org.github.io/iptv/countries/hk.m3u"),
    ("IPTV-ORG-TW",        "url", "https://iptv-org.github.io/iptv/countries/tw.m3u"),
    ("IPTV-ORG-SPORTS",    "url", "https://iptv-org.github.io/iptv/categories/sports.m3u"),
    ("IPTV-ORG-MOVIES",    "url", "https://iptv-org.github.io/iptv/categories/movies.m3u"),
    ("zbds",               "url", "https://live.zbds.top/tv/iptv4.m3u"),
]

class FakeSettings:
    def get_string(self, key):
        return {"user-agent": "Mozilla/5.0", "http-referer": ""}[key]

settings = FakeSettings()
mgr = Manager(settings)

ok = []
for name, ptype, url in CANDIDATES:
    info = "%s:::%s:::%s:::::::::" % (name, ptype, url)
    p = Provider(name=None, provider_info=info)
    downloaded = mgr.get_playlist(p, refresh=True)
    legit = mgr.check_playlist(p) if downloaded else False
    if legit:
        mgr.load_channels(p)
        print("OK    %-18s groups=%-4d channels=%-5d movies=%-5d path=%s"
              % (name, len(p.groups), len(p.channels), len(p.movies), os.path.basename(p.path)))
        ok.append(info)
    else:
        print("FAIL  %-18s downloaded=%s legit=%s" % (name, downloaded, legit))

print("\n# VALID PROVIDERS: %d / %d" % (len(ok), len(CANDIDATES)))
with open("/tmp/opencode/valid_providers.txt", "w") as f:
    f.write("\n".join(ok))
