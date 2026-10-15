#!/usr/bin/python3
"""Verify streams are actually PLAYABLE via libmpv (Hypnotix's real playback path).

libmpv 0.37 only exposes legacy property names, so we use hyphenated names via
_get_property and require a video+audio format to be selected with time advancing.
"""
import sys, time
sys.path.insert(0, "/usr/lib/hypnotix")
import mpv

PLAYLIST = [
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
    ("RTHK TV31 (香港)",     "https://rthktv31-live.akamaized.net/hls/live/2036818/RTHKTV31/master.m3u8"),
    ("RTHK TV35 (香港新聞)", "https://rthktv35-live.akamaized.net/hls/live/2101643/RTHKTV35/master.m3u8"),
    ("凤凰中文 Phoenix",     "http://223.110.245.139/ott.js.chinamobile.com/PLTV/3/224/3221226922/index.m3u8"),
    ("凤凰資訊 Phoenix Info","http://223.110.245.167/ott.js.chinamobile.com/PLTV/3/224/3221226923/index.m3u8"),
    ("台視新聞 TTV (YT)",    "https://www.youtube.com/@TTV_NEWS/live"),
    ("華視新聞 CTS (YT)",    "https://www.youtube.com/channel/UCDCJyLpbfgeVE/live"),
    ("東森新聞 EBC (YT)",    "https://www.youtube.com/channel/UCR3asjvr_WAax/live"),
    ("TVBS新聞 (YT)",        "https://www.youtube.com/channel/UC5nwNW4KdC0Sz/live"),
    ("寰宇新聞 SET (YT)",    "https://www.youtube.com/channel/UCp2f7tGJGN6R9/live"),
    ("中視新聞 CTV (YT)",    "https://www.youtube.com/channel/UCmH4q-Yjeazay/live"),
    ("民視新聞 FTV (YT)",    "https://www.youtube.com/channel/UC2VmWn8dAqkzl/live"),
    ("公視新聞 PTS (YT)",    "https://www.youtube.com/channel/UCexpzYDEnfmAv/live"),
]

FAIL = {}

def probe(name, url, secs=12):
    m = mpv.MPV(vo="null", hwdec="no", terminal=False)
    def gp(p):
        try:
            return m._get_property(p)
        except Exception:
            return None
    try:
        m.play(url)
        ok = False
        reason = "timeout"
        for _ in range(secs * 2):
            time.sleep(0.5)
            vf = gp("video-format")
            af = gp("audio-format")
            tp = gp("time-pos")
            if vf and af:
                t0 = tp
                time.sleep(1.2)
                t1 = gp("time-pos")
                if t1 is not None and t0 is not None and (t1 > t0):
                    ok = True
                    break
                reason = "no-time-progress(%s->%s)" % (t0, t1)
                break
            if gp("eof-reached"):
                reason = "eof"
                break
        if ok:
            print("OK    %-24s %s / %s" % (name, vf, af))
            return True
        print("FAIL  %-24s %s | v=%s a=%s tpos=%s" %
              (name, reason, gp("video-format"), gp("audio-format"), gp("time-pos")))
        FAIL[name] = reason
        return False
    except Exception as e:
        print("EXC   %-24s %s" % (name, str(e)[:70]))
        return False
    finally:
        try: m.terminate()
        except Exception: pass

if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    good = 0
    for name, url in PLAYLIST:
        if only and only.lower() not in name.lower():
            continue
        if probe(name, url):
            good += 1
    print("\nPLAYABLE: %d / %d" % (good, len(PLAYLIST)))
