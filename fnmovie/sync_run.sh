#!/bin/bash
# 停影视 -> 跑恢复/探活/导入 -> 启影视。任何失败都保证影视最终被拉起。
set -u
pkill -TERM -x trim-media 2>/dev/null || true
sleep 3
pkill -KILL -x trim-media 2>/dev/null || true
/usr/bin/python3 /opt/fnmovie-iptv/bin/fnmovie_sync.py
rc=$?
/opt/fnmovie-iptv/bin/restart_fnmovie.sh
exit $rc
