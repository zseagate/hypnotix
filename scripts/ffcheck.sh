#!/bin/bash
# ffprobe-based playback check: does the stream actually decode video?
NO_PROXY=${1:-0}
set_file=$2

check() {
  local name="$1" url="$2"
  local env_args=(env)
  if [ "$NO_PROXY" = "1" ]; then
    env_args+=( -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY )
  fi
  local out rc vsize
  out=$("${env_args[@]}" timeout 20 ffmpeg -v error -rw_timeout 8000000 -probesize 8M \
        -analyzeduration 4M -user_agent "Mozilla/5.0" -i "$url" -t 4 -c copy -f null - 2>&1)
  rc=$?
  vsize=$("${env_args[@]}" timeout 20 ffprobe -v error -select_streams v:0 \
        -show_entries stream=width,height,codec_name -of csv=p=0 \
        -rw_timeout 8000000 "$url" 2>/dev/null)
  if [ $rc -eq 0 ] && [ -n "$vsize" ]; then
    printf "PLAYABLE  %-26s %s\n" "$name" "$vsize"
  else
    printf "BROKEN    %-26s rc=%-4d %s\n" "$name" "$rc" "$(echo "$out" | tail -1 | cut -c1-72)"
  fi
}

while IFS=$'\t' read -r name url; do
  [ -z "$name" ] && continue
  check "$name" "$url"
done < "$set_file"
