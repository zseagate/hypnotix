#!/bin/bash
while IFS='|' read -r name url; do
  case "$name" in \#*|"") continue;; esac
  out=$(curl -s -o s.bin --max-time 12 -L -w "%{http_code} %{size_download}B" -A "Mozilla/5.0" "$url" 2>/dev/null)
  seg=$(grep -c 'EXTINF\|EXTM3U\|EXT-X-STREAM\|\.ts' s.bin 2>/dev/null)
  printf "%-22s %-16s seg=%s\n" "$name" "$out" "$seg"
done < "$1"
