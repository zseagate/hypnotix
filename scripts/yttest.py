import sys, os, time
sys.path.insert(0,"/usr/lib/hypnotix")
import mpv
name, url = sys.argv[1], sys.argv[2]
secs = float(sys.argv[3]) if len(sys.argv)>3 else 35
lf = "/tmp/opencode/yt_%d.log" % (abs(hash(name)) % 100000)
m = mpv.MPV(vo="null", hwdec="no", terminal=False, log_file=lf, ytdl=True)
m.play(url)
best = None
for i in range(int(secs*2)):
    time.sleep(0.5)
    try:
        vf = m._get_property("video-format"); tp = m._get_property("time-pos")
        af = m._get_property("audio-format")
    except Exception:
        vf = tp = af = None
    if vf:
        t0 = tp; time.sleep(1.5)
        try: t1 = m._get_property("time-pos")
        except Exception: t1 = None
        if t1 is not None and t0 is not None and t1 > t0:
            print("PLAYABLE %-22s %s/%s" % (name, vf, af)); best="OK"; break
    if i % 20 == 19:
        print("  %s t=%s v=%s tpos=%s" % (name, i*0.5, vf, tp))
if not best: print("BROKEN   %-22s v=%s tpos=%s" % (name, vf, tp))
m.terminate()
