#!/usr/bin/python3
"""Authoritative playback test using mpv 0.37 — Hypnotix's actual playback engine.

mpv 0.37 exposes only legacy properties, so we verify playback via
video-format being set AND time-pos advancing.
mpv 0.37 includes ytdl_hook, so YouTube live channels are testable too.
"""
import sys, os, time
sys.path.insert(0, "/usr/lib/hypnotix")
import mpv

import os
SECS = float(os.environ.get("SECS", "18"))
NAMES = {
    "CNN International": "https://turnerlive.warnermediacdn.com/hls/live/586495/cnngo/cnn_slate/VIDEO_0_3564000.m3u8",
    "BBC News (akamai)": "https://vs-hls-push-ww-live.akamaized.net/x=4/i=urn:bbc:pips:service:bbc_news_channel_hd/t=3840/v=pv14/b=5070016/main.m3u8",
    "DW English": "https://dwamdstream102.akamaized.net/hls/live/2015525/dwstream102/index.m3u8",
    "Al Jazeera EN": "https://live-hls-apps-aje-fa.getaj.net/AJE/index.m3u8",
    "CGTN": "https://news.cgtn.com/resource/live/english/cgtn-news.m3u8",
    "Reuters": "https://amg00453-reuters-amg00453c1-rakuten-uk-2110.playouts.now.amagi.tv/playlist/amg00453-reuters-reuters-rakutenuk/playlist.m3u8",
    "CBS News": "https://dai.google.com/linear/hls/event/Sid4xiTQTkCT1SLu6rjUSQ/master.m3u8",
    "ABC News Live": "https://abcnews-streams.akamaized.net/hls/live/2023560/abcnewshudson1/master.m3u8",
    "LiveNOW FOX": "https://fox-foxnewsnow-vizio.amagi.tv/playlist.m3u8",
    "India Today": "https://indiatodaylive.akamaized.net/hls/live/2014320/indiatoday/indiatodaylive/playlist.m3u8",
    "Scripps News": "https://content.uplynk.com/channel/4bb4901b934c4e029fd4c1abfc766c37.m3u8",
    "Russia Today": "https://rt-glb.rttv.com/live/rtnews/playlist.m3u8",
    "SABC News": "https://sabconetanw.cdn.mangomolo.com/news/smil:news.stream.smil/playlist.m3u8",
    "RTHK TV31": "https://rthktv31-live.akamaized.net/hls/live/2036818/RTHKTV31/master.m3u8",
    "RTHK TV32": "https://rthktv32-live.akamaized.net/hls/live/2036819/RTHKTV32/master.m3u8",
    "RTHK TV33": "https://rthktv33-live.akamaized.net/hls/live/2101641/RTHKTV33/master.m3u8",
    "RTHK TV34": "https://rthktv34-live.akamaized.net/hls/live/2101642/RTHKTV34/master.m3u8",
    "RTHK TV35": "https://rthktv35-live.akamaized.net/hls/live/2101643/RTHKTV35/master.m3u8",
    "Phoenix Chinese": "http://223.110.245.139/ott.js.chinamobile.com/PLTV/3/224/3221226922/index.m3u8",
    "Phoenix InfoNews": "http://223.110.245.167/ott.js.chinamobile.com/PLTV/3/224/3221226923/index.m3u8",
    "中天新聞 CTI (YT)": "https://www.youtube.com/watch?v=vr3XyVCR4T0",
    "東森新聞 EBC (YT)": "https://www.youtube.com/watch?v=V1p33hqPrUk",
    "TVBS新聞 (YT)": "https://www.youtube.com/watch?v=m_dhMSvUCIc",
    "華視新聞 CTS (YT)": "https://www.youtube.com/watch?v=wM0g8EoUZ_E",
    "民視新聞 FTV (YT)": "https://www.youtube.com/watch?v=ylYJSBUgaMA",
    "公視新聞 PTS (YT)": "https://www.youtube.com/watch?v=quwqlazU-c8",
    "寰宇新聞 SET (YT)": "https://www.youtube.com/watch?v=6IquAgfvYmc",
    "台視新聞 TTV (YT)": "https://www.youtube.com/watch?v=9iRAqBMakXY",
    "寰宇財經 SET-Biz (YT)": "https://www.youtube.com/watch?v=yAUQQ0DhPxI",
    "TVBS ON AIR (YT)": "https://www.youtube.com/watch?v=2mCSYvcfhtc",
    "東森財經 EBC-Fin (YT)": "https://www.youtube.com/watch?v=1I2iq41Akmo",
    "中視新聞 CTV (YT)": "https://www.youtube.com/watch?v=baDV1O5EBP0",
    "非凡財經 USTV (YT)": "https://www.youtube.com/watch?v=eA6Aczd3FZM",
    "CCTV1 (zbds baseline)": "http://74.91.26.218:82/live/cctv1hd.m3u8",
}

def probe(url, secs=18):
    lf = "/tmp/opencode/p_%d.log" % (abs(hash(url)) % 1000000)
    m = mpv.MPV(vo="null", hwdec="no", terminal=False, log_file=lf, ytdl=True)
    try:
        m.play(url)
        for _ in range(int(secs * 2)):
            time.sleep(0.5)
            try:
                vf = m._get_property("video-format")
                tp = m._get_property("time-pos")
            except Exception:
                vf = tp = None
            if vf:
                t0 = tp
                time.sleep(2.0)
                try:
                    t1 = m._get_property("time-pos")
                except Exception:
                    t1 = None
                if t1 is not None and t0 is not None and t1 > t0:
                    try:
                        af = m._get_property("audio-format")
                    except Exception:
                        af = "?"
                    return True, "%s / %s" % (vf, af)
                return False, "v=%s no-time-progress" % vf
        return False, "timeout v=%s tpos=%s" % (
            (m._get_property("video-format") if True else None), None)
    except Exception as e:
        return False, "exc:%s" % str(e)[:50]
    finally:
        try:
            m.terminate()
        except Exception:
            pass

def main():
    sub = sys.argv[1] if len(sys.argv) > 1 else None
    only_yt = len(sys.argv) > 2 and sys.argv[2] == "YT"
    good, bad = [], []
    for name, url in NAMES.items():
        if sub and sub.lower() not in name.lower():
            continue
        if only_yt and "(YT)" not in name:
            continue
        ok, why = probe(url, SECS)
        if ok:
            print("PLAYABLE  %-26s %s" % (name, why)); good.append(name)
        else:
            print("BROKEN    %-26s %s" % (name, why)); bad.append(name)
    print("\n=== PLAYABLE: %d / %d ===" % (len(good), len(good) + len(bad)))
    if bad:
        print("remaining broken:", "; ".join(bad))

main()
