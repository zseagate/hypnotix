#!/usr/bin/env bash
# hypnotix 播放列表本地同步器
#
# 作用:
#   1. 从 github.com/zseagate/hypnotix 拉取最新仓库快照
#      (经 codeload.github.com —— 本机直连 github.com 的 TLS 被拦, 走 codeload 等价)
#   2. 用快照刷新本地 playlists/*.m3u 与 playlist.m3u / channels.json / status.json
#   3. 从上游刷新各国列表: iptv-org(import_local.py --update) + Free-TV(jsDelivr)
#   4. 以 local(file://) 方式导入 Hypnotix providers (默认去台标极速模式)
#
# 由 systemd user timer (hypnotix-news-sync.timer) 定时调用, 也可手动执行: ./sync.sh
# 日志: 本目录下 update.log (超过 512KB 自动截尾)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARBALL_URL="https://codeload.github.com/zseagate/hypnotix/tar.gz/refs/heads/main"
ARCHIVE_ROOT="hypnotix-main"
# Free-TV 上游: import_local.py 走 raw.githubusercontent.com(本机被拦),
# 这里改用 jsDelivr 的 GitHub CDN 直接取 playlist.m3u8 刷新 freetv/freetvcdn
FREETV_URL="https://cdn.jsdelivr.net/gh/Free-TV/IPTV@master/playlist.m3u8"
LOG="$REPO_DIR/update.log"
PYTHON="${PYTHON:-python3}"

# ---- 要导入 Hypnotix 的预设与模式 (按需修改) ------------------------------
# 全部预设 + 去台标极速版 (README 推荐, 2000+ 台也不卡)
# --update: 导入前从上游刷新 iptv-org / Free-TV 列表(仓库内是静态快照)
# --skip-news: 不跑 yt-dlp 再生 News-Auto, 直接用仓库里 Actions 已刷新的版本
IMPORT_ARGS=(--all --strip-logos --update --skip-news)

# 只想要日常小列表(更快), 且不需要上游刷新时:
# IMPORT_ARGS=(--names News News-Auto CN HK TW)
# 只想用仓库快照、不联网拉上游时:
# IMPORT_ARGS=(--all --strip-logos)
# ---------------------------------------------------------------------------

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}"

log() { echo "[$(date '+%F %T')] $*"; }

# 用 Free-TV 仓库的 playlist.m3u8(经 jsDelivr CDN)刷新 freetv/freetvcdn。
# 任何异常都保留旧文件。
refresh_freetv() {
  local tmp; tmp="$(mktemp -d)"
  local f="$tmp/freetv.m3u8" new old
  if curl -fL --retry 3 --retry-delay 5 --max-time 120 -o "$f" "$FREETV_URL" \
     && [ -s "$f" ] && grep -q '^#EXTM3U' "$f"; then
    new="$(grep -c '^#EXTINF' "$f" || true)"
    old="$(grep -c '^#EXTINF' "$REPO_DIR/playlists/freetv.m3u" 2>/dev/null || echo 0)"
    if [ "$new" -gt 0 ] && { [ "$old" -eq 0 ] || [ "$new" -ge $((old / 5)) ]; }; then
      cp -f "$f" "$REPO_DIR/playlists/freetv.m3u"
      cp -f "$f" "$REPO_DIR/playlists/freetvcdn.m3u"
      log "  Free-TV: $old -> $new 台"
    else
      log "  Free-TV 台数异常 $old -> $new, 保留旧文件"
    fi
  else
    log "  Free-TV 下载失败或内容异常, 保留旧文件"
  fi
  rm -rf "$tmp"
}

main() {
  log "===== hypnotix sync 开始 ====="
  log "下载仓库快照: $TARBALL_URL"

  local tmp; tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN

  if ! curl -fL --retry 3 --retry-delay 5 --max-time 180 -o "$tmp/repo.tgz" "$TARBALL_URL"; then
    log "ERROR: 下载失败, 保留本地现有播放列表"; return 1
  fi
  if ! tar xzf "$tmp/repo.tgz" -C "$tmp"; then
    log "ERROR: 解压失败, 保留本地现有播放列表"; return 1
  fi

  local src="$tmp/$ARCHIVE_ROOT"
  if [ ! -s "$src/playlist.m3u" ] || [ ! -d "$src/playlists" ]; then
    log "ERROR: 快照内容异常, 保留现有文件"; return 1
  fi
  # 基本健康校验: 头部 + 台数不为 0
  if ! grep -q '^#EXTM3U' "$src/playlist.m3u"; then
    log "ERROR: playlist.m3u 不是合法 m3u, 保留现有文件"; return 1
  fi
  if [ "$(grep -c '^#EXTINF' "$src/playlist.m3u" || true)" -eq 0 ]; then
    log "ERROR: playlist.m3u 台数为 0, 保留现有文件"; return 1
  fi

  log "刷新本地播放列表文件"
  rsync -a --delete "$src/playlists/" "$REPO_DIR/playlists/"
  mkdir -p "$REPO_DIR/scripts"
  rsync -a "$src/scripts/" "$REPO_DIR/scripts/"
  cp -f "$src/playlist.m3u" "$src/channels.json" "$src/status.json" "$src/README.md" "$REPO_DIR/"

  log "刷新 Free-TV 上游(jsDelivr)"
  refresh_freetv

  # 统计一下刷进来的台数, 便于看日志
  local total=0 f n
  for f in "$REPO_DIR"/playlist.m3u "$REPO_DIR"/playlists/*.m3u; do
    n="$(grep -c '^#EXTINF' "$f" || true)"
    total=$((total + n))
    log "  $(basename "$f"): $n 台"
  done
  log "本地合计 $total 台"

  log "导入 Hypnotix providers (${IMPORT_ARGS[*]})"
  "$PYTHON" "$REPO_DIR/scripts/import_local.py" "${IMPORT_ARGS[@]}"
  log "===== hypnotix sync 完成 ====="
}

# 全部输出同时写屏幕与日志
main 2>&1 | tee -a "$LOG"
rc="${PIPESTATUS[0]}"

# 日志截尾, 防止无限增长
if [ "$(stat -c %s "$LOG" 2>/dev/null || echo 0)" -gt 524288 ]; then
  tail -n 200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
exit "$rc"
