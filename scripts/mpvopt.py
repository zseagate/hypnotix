import sys, os, time
sys.path.insert(0,"/usr/lib/hypnotix")
import mpv
url=sys.argv[1]
extra=sys.argv[2:]
os.chdir("/tmp/opencode")
lf="/tmp/opencode/opt_%s.log" % abs(hash("".join(extra)))%10000
m=mpv.MPV(vo="null",hwdec="no",terminal=False,log_file=lf, **dict(x.split("=",1) for x in extra))
m.play(url)
time.sleep(12)
try:
    print("%-28s v=%s tpos=%s" % (" ".join(extra) or "plain",
        m._get_property("video-format"), m._get_property("time-pos")))
except Exception as e: print("  err",str(e)[:60])
m.terminate()
