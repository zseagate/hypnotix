#!/bin/bash
# Restart the fnMovie (trim.media) backend process.
# App center has KillMode=process and does not restart child apps, so we
# stop every trim-media process and launch one ourselves.
set -u
LOG=/usr/local/apps/@appdata/trim.media/trim.media.stdout.log

pkill -TERM -x trim-media 2>/dev/null || true
for _ in $(seq 1 20); do
    pgrep -x trim-media >/dev/null || break
    sleep 0.5
done
pkill -KILL -x trim-media 2>/dev/null || true

cd /usr/local/apps/@appcenter/trim.media || exit 1
setsid nohup ./trim-media --port=8005 \
    --root=/usr/local/apps/@appdata/trim.media \
    --meta=/vol1/@appmeta/trim.media \
    --static=/usr/local/apps/@appcenter/trim.media \
    --trim-appname=trim.media --trim-username=trim-media \
    --log-dir=/usr/local/apps/@appdata/trim.media/logs \
    >>"$LOG" 2>&1 &

for _ in $(seq 1 40); do
    if ss -ltn 2>/dev/null | grep -q ':8005 '; then
        echo "trim-media listening on 8005 (pid $(pgrep -x trim-media | tr '\n' ' '))"
        exit 0
    fi
    sleep 0.5
done
echo "trim-media did not start" >&2
exit 1
