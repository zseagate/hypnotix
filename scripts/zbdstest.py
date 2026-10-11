import sys, os, time
sys.path.insert(0,"/usr/lib/hypnotix")
import mpv
urls = [
 ("CCTV1 (zbds)", "http://74.91.26.218:82/live/cctv1hd.m3u8"),
]
for name,url in urls:
    lf = "/tmp/opencode/zbds_%s.log" % (abs(hash(name))%10000)
    m = mpv.MPV(vo="null", hwdec="no", terminal=False, log_file=lf)
    m.play(url)
    for i in range(20):
        time.sleep(0.5)
        try:
            vf = m._get_property("video-format"); tp = m._get_property("time-pos")
            ia = m._get_property("idle-active")
        except Exception as e:
            vf=tp=ia=None
        if vf:
            print("OK  %s v=%s tpos=%s" % (name, vf, tp)); break
        if i % 4 == 3:
            print("  t=%s idle=%s v=%s tpos=%s" % (i*0.5, ia, vf, tp))
    else:
        print("FAIL %s" % name)
    m.terminate()
