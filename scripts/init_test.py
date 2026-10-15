import sys
sys.path.insert(0,"/usr/lib/hypnotix")
import mpv
print("libmpv import OK")
for kwargs,label in [
    ({"ytdl":True,"hwdec":"no","wid":"0"},"Hypnotix-like (ytdl=True, wid=0)"),
    ({"hwdec":"no","vo":"null"},"vo=null"),
]:
    try:
        m = mpv.MPV(**kwargs)
        print("INIT OK   :", label)
        m.terminate()
    except Exception as e:
        print("INIT FAIL :", label, "|", str(e)[:160])
