import sys, time
sys.path.insert(0,"/usr/lib/hypnotix")
import mpv
tests = [
 ("中天 频道/live", "https://www.youtube.com/channel/UC5l1Yto5oOIgR/live"),
 ("中天 handle/live", "https://www.youtube.com/@CTINewsTV/live"),
 ("東森 频道/live", "https://www.youtube.com/channel/UCR3asjvr_WAax/live"),
 ("TVBS 频道/live", "https://www.youtube.com/channel/UC5nwNW4KdC0Sz/live"),
 ("寰宇 频道/live", "https://www.youtube.com/channel/UCp2f7tGJGN6R9/live"),
 ("華視 频道/live", "https://www.youtube.com/channel/UCDCJyLpbfgeVE/live"),
]
for name, url in tests:
    m = mpv.MPV(vo="null", hwdec="no", terminal=False, log_file="/tmp/opencode/dur.log", ytdl=True)
    try:
        m.play(url)
        ok=False
        for i in range(40):
            time.sleep(0.5)
            try:
                vf=m._get_property("video-format"); tp=m._get_property("time-pos")
            except Exception:
                vf=tp=None
            if vf:
                t0=tp; time.sleep(2.0)
                try: t1=m._get_property("time-pos")
                except Exception: t1=None
                if t1 is not None and t0 is not None and t1>t0: ok=True; break
        print("%-18s %s  url=%s" % (name, "PLAYABLE" if ok else "BROKEN", "OK" if ok else ""))
    finally:
        m.terminate()
