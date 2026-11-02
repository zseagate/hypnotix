#!/bin/bash
# 在飞牛 NAS 上执行：把本目录（fnmovie/）安装到 /opt/fnmovie-iptv 并启用 systemd 服务。
#
# 用法（在 NAS 上，本目录需存在）：
#   cd <repo>/fnmovie && sudo ./install.sh
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST=/opt/fnmovie-iptv
mkdir -p "$DEST/bin" "$DEST/srv" "$DEST/logs"

cp "$SRC/fnmovie_sync.py" "$DEST/bin/"
cp "$SRC/fnmovie_iptv_web.py" "$DEST/bin/"
cp "$SRC/sync_run.sh" "$DEST/bin/"
cp "$SRC/restart_fnmovie.sh" "$DEST/bin/"
chmod 755 "$DEST/bin"/*.py "$DEST/bin"/*.sh

cp "$SRC/fnmovie-iptv-ip.service" /etc/systemd/system/
cp "$SRC/fnmovie-iptv-web.service" /etc/systemd/system/
cp "$SRC/fnmovie-iptv-sync.service" /etc/systemd/system/
cp "$SRC/fnmovie-iptv-sync.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now fnmovie-iptv-ip.service
systemctl enable --now fnmovie-iptv-web.service

echo "--- 首次同步（停影视 -> 探活 -> 导入 -> 启影视）---"
"$DEST/bin/sync_run.sh"

systemctl enable --now fnmovie-iptv-sync.timer
echo "--- status ---"
systemctl --no-pager --lines=0 status fnmovie-iptv-ip.service \
    fnmovie-iptv-web.service fnmovie-iptv-sync.timer
echo "--- srv ---"
ls -la "$DEST/srv"
echo "--- 网关自检 ---"
curl -fsS -m 10 -o /dev/null -w "cnn.m3u8=%{http_code} size=%{size_download}\n" \
    http://192.168.10.100:18080/cnn.m3u8
