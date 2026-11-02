# fnMovie IPTV 维护（飞牛 NAS）

在飞牛 NAS 的 fnMovie（`trim.media`）里维护两个电视直播媒体库，每日自动同步。

## 目标态

| 媒体库 | 频道 | 说明 |
|---|---|---|
| 综合直播 | BBC News（akamaized 4K）+ CNN International（本地代理） | Genre 32 |
| 春节联欢晚会 | 1987—2025 年春晚（kwimgs / 百度 / 24playback） | Genre 106 |

其它库（电影频道 / 体育直播 / 国际频道）会被删除；无法探活的频道会被剔除。

## 架构 / 为什么这样设计

- **fnMovie 自动刷新不可靠**：`iptv-active-refresh-check` 只在客户端请求时触发，命令行无法可靠触发；
  且刷新时 fnMovie 会逐台下载维基台标（`tvg-logo` 触发 403 重试风暴，导入卡几小时）。
  因此**所有频道直接按 fnMovie 导入格式写库**（`item / item_media / item_ancestor / item_tag / item_user`），
  库级 `iptv_refresh_enabled=0` 防止被覆盖。播放列表重建时 EXTINF 只保留时长、group-title、频道名，
  去掉 `tvg-logo / tvg-id / tvg-name / tvg-country`。
- **SSRF 绕过**：fnMovie 拦截内网 URL；用回环假公网 IP `1.1.1.246`（NAS `lo`，systemd `fnmovie-iptv-ip.service`）
  让 fnMovie 只访问 NAS 本机，客户端不可达。
- **CNN 不能直连 CloudFront master**：master 用 `../../../manifest/...` 相对路径，fnMovie/客户端解析失败。
  方案是 NAS 本地 HLS 网关（`fnmovie_iptv_web.py`，`0.0.0.0:18080`）把 master 拉平成单一清晰度媒体播单并代理分片。
  CNN 频道媒体路径改为 `http://192.168.10.100:18080/cnn.m3u8`。
- **直连开关**：`media_server.direct_link_enable=1, direct_link_allowed_level=1`（所有用户直连），
  客户端直接访问 `192.168.10.100:18080`，绕过 fnMovie 代理。
- **BBC 只有一条可播放源**：akamaized `main.m3u8`（200，媒体播单）；
  fastly `iptv_hd_abr_v1.m3u8` 从 NAS **整机 403**（试过无 UA / Referer / Origin 均失败），已剔除；
  akamaized 低码率变体（t=1920/1280/960/720/640 各档）从 NAS 均取不到。故 BBC 为单线路。
- **每日同步**：`fnmovie-iptv-sync.timer`（每日 04:17 + 随机 ≤600s，`Persistent`）→ `sync_run.sh`
  （停影视 → `fnmovie_sync.py` 探活/写播放列表/写库 → 启影视）。任何失败都保证影视最终被拉起。

## 关键常量

- 库 GUID：综合直播 `3e4af7c84e724c5f81827d5cedb0879a`；电影 `122d3f88b4c746388bbb19f3ef51584d`；
  体育 `7d3b63f377624141a5e3cc9d57bc807f`；国际 `9c46f06646964977b9796ff8ed064161`；春晚库运行时按 URL 查找。
- 用户 GUID：`7b680fa9347c4aa6a5810e91b2ce93be`。
- 春晚备份：`/root/fnmovie-backup/trimmedia.db.20261101_220930`（22 条春晚，GALA 来源）；
  BBC/CNN 精确行：`/root/fnmovie-backup/trimmedia.db.libraries.20261101_223031`。
- CNN 上游 master：`https://d3bp6dwmpbdajl.cloudfront.net/v1/master/3722c60a815c199d9c0ef36c5b73da68a62b09d1/cc-ury0meh5m4nzm/index.m3u8`。
- BBC 主媒体：`https://vs-hls-push-ww-live.akamaized.net/x=4/i=urn:bbc:pips:service:bbc_news_channel_hd/t=3840/v=pv14/b=5070016/main.m3u8`。
- Genre：直播专用 `32`=新闻、`101`=体育、`105`=综合/地方、`106`=其他/默认、`111`=少儿；VOD 兼容 `16`=电视电影。综合→32、春晚→106。
- 数据库：`/usr/local/apps/@appdata/trim.media/database/trimmedia.db`（WAL）。

## 文件

- `fnmovie_sync.py`：唯一同步入口（目标态：综合 + 春晚，删其它库，探活，直接写库）。
- `fnmovie_iptv_web.py`：本地 HLS 网关（静态 `srv/` + `/cnn.m3u8` 拉平 + `/cnn/seg` 分片代理，CORS；
  播单缓存 1.5s、分片流式转发 + 60s 短缓存）。
- `sync_run.sh`：停影视 → `fnmovie_sync.py` → 启影视。
- `restart_fnmovie.sh`：`pkill -x trim-media` 后 `setsid nohup ./trim-media ...` 启动并等 8005。
- `fnmovie-iptv-{ip,web,sync}.service`、`fnmovie-iptv-sync.timer`：systemd 单元。
- `install.sh`：在 NAS 上安装本目录到 `/opt/fnmovie-iptv` 并启用服务。

## 手动操作（NAS 上）

```bash
# 停影视
pkill -TERM -x trim-media; sleep 3; pkill -KILL -x trim-media || true
# 手动跑一次同步
/opt/fnmovie-iptv/bin/sync_run.sh        # 内含停影视->sync->启影视
# 或只跑脚本（脚本内部会先停影视）
/usr/bin/python3 /opt/fnmovie-iptv/bin/fnmovie_sync.py
# 查看定时任务
systemctl list-timers fnmovie-iptv-sync.timer --no-pager
```

## 注意事项

- 进程匹配必须用 `pkill -x trim-media`；重启用 `/opt/fnmovie-iptv/bin/restart_fnmovie.sh`。
- 探活结果随片源波动，`fnmovie_sync.py` 每次全量探活，不缓存。
- NAS 密码不要写进仓库或对话（通过 `/tmp/opencode/nas_pass` 供远程执行封装读取）。
- `1.1.1.246:18080` 仅 NAS 本机可用；局域网客户端用 `192.168.10.100:18080`（直连模式）。
