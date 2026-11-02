#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fnMovie IPTV 本地 HTTP 服务。

职责：
  1. 静态服务 /opt/fnmovie-iptv/srv/（chinese.m3u8、logo.png 等），加 CORS。
  2. /cnn.m3u8 —— 把 CNN 上游 CloudFront 的 master 拉平成"单一清晰度媒体播放
     列表"，分片统一改写到本地 /cnn/seg?u=...，这样客户端只访问 NAS 即可，
     不依赖客户端网络能否直达 CloudFront，也绕开了 fnMovie 对相对路径
     (../../../manifest/...) 处理不好导致播放失败的问题。
  3. /cnn/seg —— 反向代理分片，带 CORS。

监听 0.0.0.0:18080：NAS 本机可用 1.1.1.246:18080（fnMovie 内部走），
局域网客户端可用 192.168.10.100:18080（直连模式）。
"""
from __future__ import annotations

import re
import shutil
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
SRV = Path("/opt/fnmovie-iptv/srv")
LAN_BASE = "http://192.168.10.100:18080"
MASTER = ("https://d3bp6dwmpbdajl.cloudfront.net/v1/master/"
          "3722c60a815c199d9c0ef36c5b73da68a62b09d1/cc-ury0meh5m4nzm/index.m3u8")
SEG_PREFIX = "https://d3bp6dwmpbdajl.cloudfront.net/"
# 直播播单必须高频刷新（客户端每 ~6s 拉一次）。缓存过久（旧值 300s）会让
# 客户端拿到已滚出上游滑动窗口的分片，导致每 6s 卡一次。这里只要 1.5s，
# 既避免每请求都打上游，又保证客户端拿到的是新播单。
CACHE_TTL = 1.5
# 分片短缓存：吸收客户端重拉同一分片（播单轻微滞后时）造成的高延迟/卡顿。
SEG_CACHE_TTL = 60.0


def http_get(url: str, timeout: float = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def pick_variant(master_text: str) -> str | None:
    """从 master 里挑带宽最高的变体，返回绝对 URL。"""
    lines = master_text.splitlines()
    best, best_bw = None, -1
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            m = re.search(r"BANDWIDTH=(\d+)", line)
            bw = int(m.group(1)) if m else 0
            for nxt in lines[i + 1:i + 2]:
                if nxt and not nxt.startswith("#"):
                    url = urllib.parse.urljoin(MASTER, nxt)
                    if bw > best_bw:
                        best, best_bw = url, bw
                    break
    return best


class CnnCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._playlist: bytes | None = None
        self._ts = 0.0

    def get(self) -> bytes:
        with self._lock:
            if (self._playlist is not None
                    and time.time() - self._ts < CACHE_TTL):
                return self._playlist
        try:
            master = http_get(MASTER).decode("utf-8", "ignore")
            variant = pick_variant(master)
            if not variant:
                raise RuntimeError("no variant found")
            body = http_get(variant).decode("utf-8", "ignore")

            def seg_url(u: str) -> str:
                abs_u = urllib.parse.urljoin(variant, u)
                return "%s/cnn/seg?u=%s" % (LAN_BASE, urllib.parse.quote(abs_u, safe=""))

            out = []
            for line in body.splitlines():
                s = line.strip()
                if s.startswith("#EXT-X-KEY:") or s.startswith("#EXT-X-MAP:"):
                    out.append(re.sub(r'URI="([^"]*)"',
                                      lambda m: 'URI="%s"' % seg_url(m.group(1)), s))
                elif s.startswith("#"):
                    if not (not out and s.startswith("#EXTM3U")):
                        out.append(s)
                elif s:
                    out.append(seg_url(s))
            data = ("#EXTM3U\n" + "\n".join(out) + "\n").encode("utf-8")
            with self._lock:
                self._playlist = data
                self._ts = time.time()
            return data
        except Exception as e:  # noqa: BLE001
            with self._lock:
                if self._playlist is not None:
                    return self._playlist
            raise


CNN = CnnCache()


class SegCache:
    """按 URL 缓存最近的分片内容（短 TTL），避免重复反代整段。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, tuple[float, bytes]] = {}

    def get(self, url: str) -> bytes | None:
        with self._lock:
            e = self._data.get(url)
            if e and time.time() - e[0] < SEG_CACHE_TTL:
                return e[1]
            return None

    def put(self, url: str, data: bytes) -> None:
        with self._lock:
            self._data[url] = (time.time(), data)
            if len(self._data) > 64:
                now = time.time()
                for k in [k for k, (t, _) in self._data.items()
                          if now - t > SEG_CACHE_TTL]:
                    self._data.pop(k, None)


SEGS = SegCache()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Expose-Headers", "*")

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlsplit(self.path).path
        try:
            if path == "/cnn.m3u8":
                self._send(200, CNN.get(),
                           "application/vnd.apple.mpegurl; charset=utf-8")
                return
            if path == "/cnn/seg":
                q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                u = (q.get("u") or [""])[0]
                if not u.startswith(SEG_PREFIX) or ".." in u:
                    self._send(400, b"bad url", "text/plain")
                    return
                cached = SEGS.get(u)
                if cached is not None:
                    self._send(200, cached, "video/mp2t")
                    return
                req = urllib.request.Request(u, headers={"User-Agent": UA})
                resp = urllib.request.urlopen(req, timeout=30)
                try:
                    self.send_response(200)
                    self._cors()
                    self.send_header("Content-Type", "video/mp2t")
                    cl = resp.headers.get("Content-Length")
                    if cl:
                        self.send_header("Content-Length", cl)
                    self.end_headers()
                    # 流式转发：边收上游边写给客户端，避免整段读完才发首字节
                    buf = bytearray()
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        if len(buf) < 6 * 1024 * 1024:
                            buf.extend(chunk)
                    SEGS.put(u, bytes(buf))
                finally:
                    resp.close()
                return
            # 静态文件
            rel = path.lstrip("/")
            if not rel or "/" in rel and ".." in rel:
                self._send(404, b"not found", "text/plain")
                return
            fp = (SRV / rel).resolve()
            if not str(fp).startswith(str(SRV.resolve())) or not fp.is_file():
                self._send(404, b"not found", "text/plain")
                return
            ctype = ("application/vnd.apple.mpegurl" if fp.suffix in (".m3u8", ".m3u")
                     else "image/png" if fp.suffix == ".png"
                     else "application/octet-stream")
            self._send(200, fp.read_bytes(), ctype + "; charset=utf-8")
        except Exception as e:  # noqa: BLE001
            try:
                self._send(502, ("proxy error: %s" % e).encode("utf-8"), "text/plain")
            except Exception:  # noqa: BLE001
                pass

    def log_message(self, *args) -> None:  # noqa: N802
        pass


def main() -> None:
    srv = ThreadingHTTPServer(("0.0.0.0", 18080), Handler)
    print("fnmovie IPTV web on 0.0.0.0:18080", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
