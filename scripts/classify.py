#!/usr/bin/python3
"""Classify each news stream: does libmpv (Hypnotix's engine) actually play it here?

Tests both with the system proxy and direct, so we can tell real stream failures
apart from local environment (proxy/TLS) failures.
Dumps the tail of mpv's error log for every failure.
"""
import sys, os, time, subprocess
sys.path.insert(0, "/usr/lib/hypnotix")
import mpv

STREAMS = [
    ("CNN International",    "https://turnerlive.warnermediacdn.com/hls/live/586495/cnngo/cnn_slate/VIDEO_0_3564000.m3u8"),
    ("BBC News",             "https://vs-hls-push-ww-live.akamaized.net/x=4/i=urn:bbc:pips:service:bbc_news_channel_hd/t=3840/v=pv14/b=5070016/main.m3u8"),
    ("Al Jazeera English",   "https://live-hls-apps-aje-fa.getaj.net/AJE/index.m3u8"),
    ("DW English",           "https://dwamdstream102.akamaized.net/hls/live/2015525/dwstream102/index.m3u8"),
    ("CGTN",                 "https://news.cgtn.com/resource/live/english/cgtn-news.m3u8"),
    ("Reuters",              "https://amg00453-reuters-amg00453c1-rakuten-uk-2110.playouts.now.amagi.tv/playlist/amg00453-reuters-reuters-rakutenuk/playlist.m3u8"),
    ("CBS News",             "https://dai.google.com/linear/hls/event/Sid4xiTQTkCT1SLu6rjUSQ/master.m3u8"),
    ("ABC News Live",        "https://abcnews-streams.akamaized.net/hls/live/2023560/abcnewshudson1/master.m3u8"),
    ("NBC News Now",         "https://d1si3n1st4nkgb.cloudfront.net/10502/88896001/hls/master.m3u8?ads.xumo_channelId=88896001"),
    ("LiveNOW from FOX",     "https://fox-foxnewsnow-vizio.amagi.tv/playlist.m3u8"),
    ("India Today",          "https://indiatodaylive.akamaized.net/hls/live/2014320/indiatoday/indiatodaylive/playlist.m3u8"),
    ("Scripps News",         "https://content.uplynk.com/channel/4bb4901b934c4e029fd4c1abfc766c37.m3u8"),
    ("USA Today",            "https://cdn-ue1-prod.tsv2.amagi.tv/linear/amg00731-gannettcoinc-usatoday/playlist.m3u8"),
    ("Russia Today",         "https://rt-glb.rttv.com/live/rtnews/playlist.m3u8"),
    ("TalkTV (UK)",          "https://488f4ce4.wurl.com/master/f36d25e7e52f1ba8d7e56eb859c636563214f79d/master.m3u8"),
    ("SABC News",            "https://sabconetanw.cdn.mangomolo.com/news/smil:news.stream.smil/playlist.m3u8"),
    ("RTHK TV31",            "https://rthktv31-live.akamaized.net/hls/live/2036818/RTHKTV31/master.m3u8"),
    ("RTHK TV35",            "https://rthktv35-live.akamaized.net/hls/live/2101643/RTHKTV35/master.m3u8"),
    ("Phoenix Chinese",      "http://223.110.245.139/ott.js.chinamobile.com/PLTV/3/224/3221226922/index.m3u8"),
    ("Phoenix InfoNews",     "http://223.110.245.167/ott.js.chinamobile.com/PLTV/3/224/3221226923/index.m3u8"),
]

def test(url, lf, secs=10):
    m = mpv.MPV(vo="null", hwdec="no", terminal=False, log_file=lf)
    try:
        m.play(url)
        t0 = None
        for _ in range(secs * 2):
            time.sleep(0.5)
            try:
                vf = m._get_property("video-format")
                tp = m._get_property("time-pos")
            except Exception:
                vf, tp = None, None
            if vf:
                if t0 is None:
                    t0 = tp
                    time.sleep(1.5)
                    t1 = None
                    try: t1 = m._get_property("time-pos")
                    except Exception: pass
                    if t1 is not None and t0 is not None and t1 > t0:
                        return True, "playing"
                break
        try:
            return False, "%s" % m._get_property("time-pos")
        except Exception:
            return False, "no-track"
    finally:
        try: m.terminate()
        except Exception: pass

def errtail(lf, n=4):
    if not os.path.exists(lf):
        return "no-log"
    ls = [l for l in open(lf, encoding="utf-8", errors="ignore")
          if l.strip() and ("[e]" in l or "[w]" in l)]
    return " || ".join(x.strip()[:110] for x in ls[-n:])

def main(no_proxy):
    if no_proxy:
        for k in ("http_proxy", "https_proxy", "all_proxy",
                  "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
            os.environ.pop(k, None)
    env = "NO-PROXY" if no_proxy else "PROXY"
    print("===== %s =====" % env)
    ok = []
    for name, url in STREAMS:
        lf = "/tmp/opencode/%s_%d.log" % (env, abs(hash(name)) % 100000)
        good, why = test(url, lf)
        if good:
            print("OK    %-22s %s" % (name, why)); ok.append(name)
        else:
            print("FAIL  %-22s %s" % (name, errtail(lf, 2)))
    print("--- %s playable: %d/%d ---\n" % (env, len(ok), len(STREAMS)))
    return set(ok)

if __name__ == "__main__":
    a = main(False)
    b = main(True)
    print("### SUMMARY")
    for name, url in STREAMS:
        s = []
        if name in a: s.append("proxy")
        if name in b: s.append("direct")
        print("  %-22s %s" % (name, "+".join(s) if s else "*** NOT PLAYABLE ***"))
