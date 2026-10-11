#!/bin/bash
check() {
  url="$1"
  for i in 1 2 3; do
    out=$(curl -s -o /tmp/opencode/body.bin --max-time 20 -L -w "%{http_code} %{size_download} %{time_total}" "$url")
    code=$(echo "$out" | awk '{print $1}')
    size=$(echo "$out" | awk '{print $2}')
    if [ "$code" = "200" ] && [ "$size" -gt 100 ]; then break; fi
    sleep 1
  done
  lines=$(grep -c '^#EXTINF' /tmp/opencode/body.bin 2>/dev/null || echo 0)
  printf "%-62s code=%s size=%-9s ch=%s\n" "$url" "$code" "$size" "$lines"
}
while read -r u; do [ -z "$u" ] && continue; check "$u"; done < urls.txt
