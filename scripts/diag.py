import sys, time, subprocess
sys.path.insert(0, "/usr/lib/hypnotix")
import mpv

URL = sys.argv[1]
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 14.0
lf = "/tmp/opencode/mpv_%d.log" % (abs(hash(URL)) % 100000)

m = mpv.MPV(vo="null", hwdec="no", terminal=False, log_file=lf)
m.play(URL)
time.sleep(secs)
try:
    print("=== props ===")
    for p in ["time-pos", "video-format", "audio-format", "idle-active"]:
        print("  %-14s = %s" % (p, str(m._get_property(p))[:80]))
except Exception as e:
    print("prop err", e)
m.terminate()

print("=== mpv log (filtered) ===")
import os
if os.path.exists(lf):
    lines = open(lf, encoding="utf-8", errors="ignore").read().splitlines()
    key = ("error", "failed", "hls", "http", "ffmpeg", "demux", "codec",
           "denied", "timeout", "avformat", "connection", "refused",
           "not compliant", "playlist", "no such", "warning", "open")
    sel = [l for l in lines if any(k in l.lower() for k in key)]
    for l in sel[-40:]:
        print("  " + l[:180])
    print("--- total log lines: %d, selected: %d" % (len(lines), len(sel)))
