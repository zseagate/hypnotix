#!/usr/bin/env python3
"""一键把本仓库的 m3u 以 local 类型导入 Hypnotix，秒级完成、无需下载。

原理: Hypnotix Provider 格式为 name:::type:::url:::user:::pass:::epg，
type=local + url=file:///绝对路径 时 Manager.get_playlist() 直接用本地
文件，不走 requests 下载，所以比 type=url 快 1~2 个数量级。

用法:
    python3 scripts/import_local.py --list
    python3 scripts/import_local.py --all
    python3 scripts/import_local.py --names News CN HK TW
    python3 scripts/import_local.py --file /path/to/xxx.m3u --name MyTV
    python3 scripts/import_local.py --all --strip-logos   # 生成去台标极速版

定期更新(一条命令搞定, 装完立即首次同步):
    python3 scripts/import_local.py --update --install-cron
    # 等价于先 --update 刷新上游再导入, 之后每 6 小时自动重复
    python3 scripts/import_local.py --update --install-cron --interval-hours 12
    python3 scripts/import_local.py --uninstall-cron      # 卸载定时任务
    python3 scripts/import_local.py --update --names CN HK   # 手动只刷新两个

去台标说明: freetv/iptvorg 类大列表每台都带 tvg-logo，Hypnotix 打开分组后
会逐个 requests.get 台标(每台最多 10s 超时)，2000 台就是灾难。--strip-logos
会生成 <原名>.fast.m3u(去掉 tvg-logo 参数)再导入，列表秒开，播放不受影响。

更新安全性: 下载先写 .tmp, 校验 #EXTM3U 头 + 台数不骤降(不低于旧的 20%)
才原子替换; 任何一步失败都保留旧文件, 定时任务不会把可用列表搞坏。
News 是人工精选无上游; News-Auto 由 update_playlist.py(yt-dlp) 本地再生,
想跳过它用 --skip-news。日志追加到仓库根目录 update.log(超过 512KB 自动截尾)。
"""
import argparse
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 预设:名字 -> 仓库内相对路径。playlist.m3u 由 Actions 每3小时刷新 YouTube live ID，
# news.m3u 为人工精选(15个必看)。大列表默认不导入，用 --all 才导。
PRESETS = {
    "News": "playlists/news.m3u",
    "News-Auto": "playlist.m3u",
    "CN": "playlists/iptvorgcn.m3u",
    "HK": "playlists/iptvorghk.m3u",
    "TW": "playlists/iptvorgtw.m3u",
    "ZH": "playlists/iptvorgzh.m3u",
    "Sports": "playlists/iptvorgsports.m3u",
    "Movies": "playlists/iptvorgmovies.m3u",
    "FreeTV": "playlists/freetv.m3u",
    "FreeTV-CDN": "playlists/freetvcdn.m3u",
}
# 日常推荐:小而稳，Hypnotix 秒开
DEFAULT_NAMES = ["News", "News-Auto", "CN", "HK", "TW"]

# 上游源:--update 时从这里刷新 playlists/ 下的文件。News 是人工精选不联网;
# News-Auto 由 update_playlist.py 本地再生。FreeTV 与 FreeTV-CDN 上游相同。
SOURCES = {
    "CN": "https://iptv-org.github.io/iptv/countries/cn.m3u",
    "HK": "https://iptv-org.github.io/iptv/countries/hk.m3u",
    "TW": "https://iptv-org.github.io/iptv/countries/tw.m3u",
    "ZH": "https://iptv-org.github.io/iptv/languages/zho.m3u",
    "Sports": "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "Movies": "https://iptv-org.github.io/iptv/categories/movies.m3u",
    "FreeTV": "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8",
    "FreeTV-CDN": "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8",
}
CRON_TAG = "# hypnotix-sync"   # crontab 里的标记行, 卸载时按它识别


def backup():
    out = subprocess.run(["dconf", "dump", "/org/x/hypnotix/"],
                         capture_output=True, text=True)
    if out.returncode == 0 and out.stdout.strip():
        p = Path("/tmp/hypnotix_backup_%s.txt"
                 % time.strftime("%Y%m%d_%H%M%S"))
        p.write_text(out.stdout, encoding="utf-8")
        print("backup: %s" % p)


def get_providers():
    from gi.repository import Gio
    s = Gio.Settings.new("org.x.hypnotix")
    return s, s.get_strv("providers")


def provider_str(name, path):
    return "%s:::local:::file://%s:::::::::" % (name, path)


def check_m3u(path):
    """轻量校验 + 统计，不依赖 Hypnotix 代码。"""
    n_extinf = n_url = 0
    ok = False
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            s = line.strip()
            if s.startswith("#EXTM3U"):
                ok = True
            elif s.startswith("#EXTINF"):
                n_extinf += 1
            elif "://" in s and not s.startswith("#"):
                n_url += 1
    return ok, n_extinf, n_url


def strip_logos(src: Path) -> Path:
    """去掉 tvg-logo 参数，生成 .fast.m3u。返回新路径。"""
    dst = src.with_suffix("").as_posix() + ".fast.m3u" \
        if src.suffix == ".m3u" else str(src) + ".fast.m3u"
    dst = Path(dst)
    pat = re.compile(r'\s*tvg-logo=".*?"')
    with open(src, encoding="utf-8", errors="ignore") as fin, \
            open(dst, "w", encoding="utf-8") as fout:
        for line in fin:
            if line.startswith("#EXTINF"):
                line = pat.sub("", line)
            fout.write(line)
    return dst


# ---------------- 上游更新 + 定时任务 ----------------

def fetch(url, timeout=60):
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 hypnotix-sync"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def count_extinf(text):
    return sum(1 for l in text.splitlines() if l.startswith("#EXTINF"))


def update_one(name):
    """从 SOURCES 刷新单个预设的本地 m3u。任何异常都保留旧文件。"""
    url = SOURCES.get(name)
    if not url:
        print("KEEP  %-14s 无上游(人工维护)" % name)
        return False
    dst = (REPO / PRESETS[name]).resolve()
    try:
        text = fetch(url)
    except Exception as e:
        print("FAIL  %-14s 下载失败: %s (保留旧文件)" % (name, e))
        return False
    if not text.lstrip().startswith("#EXTM3U"):
        print("FAIL  %-14s 内容不是 m3u (保留旧文件)" % name)
        return False
    new_cnt = count_extinf(text)
    old_cnt = count_extinf(
        dst.read_text(encoding="utf-8", errors="ignore")) if dst.exists() else 0
    if new_cnt == 0 or (old_cnt and new_cnt < old_cnt * 0.2):
        print("FAIL  %-14s 台数异常 %d -> %d (保留旧文件)" % (name, old_cnt, new_cnt))
        return False
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, dst)
    print("FRESH %-14s %d -> %d 台" % (name, old_cnt, new_cnt))
    # 之前生成过 .fast 版就同步重建, 定时任务才不会留下陈旧文件
    fast = dst.with_name(dst.stem + ".fast.m3u")
    if fast.exists():
        strip_logos(dst)
        print("      已同步重建 %s" % fast.name)
    return True


def update_sources(names, skip_news=False):
    print("--- update from upstream ---")
    for n in names:
        if n == "News-Auto":
            if skip_news:
                print("KEEP  %-14s (--skip-news)" % n)
                continue
            print("...   %-14s 再生 YouTube live ID (yt-dlp, 较慢)" % n)
            r = subprocess.run(
                [sys.executable, str(REPO / "scripts/update_playlist.py")],
                cwd=REPO)
            if r.returncode != 0:
                print("WARN  %-14s update_playlist.py rc=%d" % (n, r.returncode))
            continue
        update_one(n)


def crontab_lines():
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return r.stdout.splitlines() if r.returncode == 0 else []


def write_crontab(lines):
    subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n",
                   text=True, check=True)


def install_cron(hours, cron_args):
    """安装 crontab: 每 N 小时用 cron_args 重新更新+导入。幂等, 重复执行覆盖。"""
    uid = os.getuid()
    env = ("XDG_RUNTIME_DIR=/run/user/%d "
           "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/%d/bus" % (uid, uid))
    minute = 23  # 避开整点高峰
    sched = "23 4 * * *" if hours >= 24 else "%d */%d * * *" % (minute, hours)
    cmd = "%s %s %s" % (env, shlex.quote(sys.executable),
                        " ".join(shlex.quote(c) for c in cron_args))
    block = [CRON_TAG + " begin (managed by scripts/import_local.py, 勿手改)",
             "%s %s >> %s 2>&1" % (sched, cmd,
                                   shlex.quote(str(REPO / "update.log"))),
             CRON_TAG + " end"]
    kept = [l for l in crontab_lines()
            if not l.startswith(CRON_TAG)
            and "scripts/import_local.py" not in l]
    write_crontab(kept + block)
    print("已安装 crontab(%d 小时一次):" % hours)
    for l in block:
        print("  " + l)


def uninstall_cron():
    kept = [l for l in crontab_lines()
            if not l.startswith(CRON_TAG)
            and "scripts/import_local.py" not in l]
    removed = len(crontab_lines()) - len(kept)
    write_crontab(kept)
    print("已卸载 hypnotix 定时同步(移除 %d 行)" % removed if removed
          else "crontab 里本来就没有 hypnotix 同步任务")


def trim_log(path, limit=512 * 1024, keep=200):
    """日志超过 limit 就只留最后 keep 行, 防止 update.log 无限膨胀。"""
    try:
        if path.exists() and path.stat().st_size > limit:
            tail = path.read_text(encoding="utf-8",
                                  errors="ignore").splitlines()[-keep:]
            path.write_text("\n".join(tail) + "\n", encoding="utf-8")
    except OSError:
        pass


def do_import(entries, strip=False):
    """entries: [(name, abspath)]。返回 (added, skipped)。"""
    from gi.repository import Gio
    s = Gio.Settings.new("org.x.hypnotix")
    existing = s.get_strv("providers")
    have = {e.split(":::")[0]: e for e in existing}
    result = list(existing)
    added, skipped = [], []
    for name, path in entries:
        if strip:
            path = str(strip_logos(Path(path)))
            name = name + "-Fast"
        ok, n_extinf, n_url = check_m3u(path)
        if not ok or n_extinf == 0:
            print("SKIP  %-14s 文件无效: %s" % (name, path))
            skipped.append(name)
            continue
        entry = provider_str(name, path)
        if name in have:
            if have[name] == entry:
                print("SKIP  %-14s 已存在且路径一致 (%d 台)" % (name, n_extinf))
            else:
                # 同名不同路径:替换
                idx = result.index(have[name])
                result[idx] = entry
                print("UPDATE %-14s 路径更新 -> %s (%d 台)" % (name, path, n_extinf))
                added.append(name)
            continue
        result.append(entry)
        print("ADD   %-14s %s (%d 台)" % (name, path, n_extinf))
        added.append(name)
    if result != existing:
        backup()   # 只有 providers 真变了才备份, 定时任务不堆垃圾文件
    s.set_strv("providers", result)
    #  verify:用 Hypnotix 自己的 Manager 走一遍
    sys.path.insert(0, "/usr/lib/hypnotix")
    import common

    class FakeSettings:
        def get_string(self, k):
            return {"user-agent": "Mozilla/5.0",
                    "http-referer": ""}.get(k, "")

    mg = common.Manager(FakeSettings())
    print("\n--- verify with Hypnotix Manager ---")
    for name, path in entries:
        disp = name + "-Fast" if strip else name
        p = common.Provider(disp, provider_str(disp, path if not strip
                            else str(strip_logos(Path(path)))))
        t0 = time.time()
        ok1 = mg.get_playlist(p)
        ok2 = mg.check_playlist(p) if ok1 else False
        if ok2:
            mg.load_channels(p)
        n = len(p.channels) + len(p.movies) + len(p.series)
        print("%-14s get=%s check=%s total=%d (%.2fs)" %
              (disp, ok1, ok2, n, time.time() - t0))
    print("\nDONE: +%d, skip %d。重启 Hypnotix 即可在 Providers 里看到。" % (
        len(added), len(skipped)))
    print("TIP: 日常只留 News/CN/HK/TW 这类小列表最快; FreeTV(2000+台)会卡分组渲染，"
          "建议加 --strip-logos 或按需导入。")
    return added, skipped


def main():
    ap = argparse.ArgumentParser(description="Hypnotix 本地节目源秒级导入")
    ap.add_argument("--list", action="store_true", help="列出预设")
    ap.add_argument("--all", action="store_true", help="导入全部预设")
    ap.add_argument("--names", nargs="*", default=None, help="导入指定预设名")
    ap.add_argument("--file", default=None, help="任意本地 m3u 文件")
    ap.add_argument("--name", default=None, help="配合 --file 的显示名")
    ap.add_argument("--strip-logos", action="store_true",
                    help="去台标生成 .fast.m3u 后导入(大列表极速模式)")
    ap.add_argument("--update", action="store_true",
                    help="导入前先从上游刷新选中的预设(News 除外)")
    ap.add_argument("--skip-news", action="store_true",
                    help="--update 时不跑 yt-dlp 再生 News-Auto")
    ap.add_argument("--install-cron", action="store_true",
                    help="安装 crontab 定期自动 更新+导入(幂等)")
    ap.add_argument("--uninstall-cron", action="store_true",
                    help="卸载本脚本安装的 crontab 任务")
    ap.add_argument("--interval-hours", type=int, default=6,
                    help="配合 --install-cron, 周期小时数(默认 6)")
    a = ap.parse_args()

    if a.list:
        print("%-14s %-5s %s" % ("NAME", "UPD", "PATH"))
        for k, v in PRESETS.items():
            p = REPO / v
            exists = "OK " if p.exists() else "MISS"
            upd = "yes" if k in SOURCES else "no"
            print("%-14s %-5s [%s] %s" % (k, upd, exists, p))
        print("\n默认组合(不带参数时导入): %s" % " ".join(DEFAULT_NAMES))
        print("UPD=yes 的预设可 --update 联网刷新; News 人工精选, "
              "News-Auto 由 update_playlist.py 再生。")
        return 0

    if a.uninstall_cron:
        uninstall_cron()
        return 0

    names = None
    if a.all:
        names = list(PRESETS)
    elif a.names:
        names = a.names
    elif not a.file:
        names = DEFAULT_NAMES
    if names:
        for n in names:
            if n not in PRESETS:
                print("未知预设: %s (--list 查看)" % n)
                return 1

    if a.install_cron:
        # cron 里重放同样的选择, 但强制 --update; 参数要可复现
        cron_args = [str(REPO / "scripts/import_local.py"), "--update"]
        if a.all:
            cron_args.append("--all")
        elif a.names:
            cron_args += ["--names"] + list(a.names)
        if a.file:
            cron_args += ["--file", a.file]
            if a.name:
                cron_args += ["--name", a.name]
        if a.strip_logos:
            cron_args.append("--strip-logos")
        if a.skip_news:
            cron_args.append("--skip-news")
        install_cron(max(1, a.interval_hours), cron_args)
        print("\n立即执行一次首次同步...\n")
        a.update = True   # 本次运行就地做一次完整 更新+导入

    if a.update:
        if names is None:
            # 只给了 --file 的情况: 无可刷新的预设, 跳过
            print("--- update: 仅 --file 模式, 无预设可刷新 ---")
        else:
            update_sources(names, skip_news=a.skip_news)
            # 若用 --strip-logos, do_import(strip=True) 会在导入时重建 .fast.m3u

    trim_log(REPO / "update.log")
    entries = []
    if a.file:
        p = Path(a.file).expanduser().resolve()
        if not p.exists():
            print("文件不存在: %s" % p)
            return 1
        entries.append((a.name or p.stem, str(p)))
    if names:
        for n in names:
            entries.append((n, str((REPO / PRESETS[n]).resolve())))

    do_import(entries, strip=a.strip_logos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
