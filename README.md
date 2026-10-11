# hypnotix-news

自动刷新的 Hypnotix 新闻频道播放列表。

YouTube 的直播视频 ID 会频繁轮换——本项目实测中，台湾新闻台 12 个频道里有 5 个的直播 ID 在几小时内就变了，最快的一个半小时内换了两轮。手动维护注定失效，所以这里用一个定时任务保持播放列表最新。

## 快速开始

在 Hypnotix 里添加一个 Provider，URL 填下面任一个（把 `<YOUR_GITHUB_USER>` 换成你的账号）：

```
https://raw.githubusercontent.com/<YOUR_GITHUB_USER>/hypnotix-news/main/playlist.m3u
```

或走 jsdelivr CDN（缓存延迟稍长，但国内网络下通常更稳）：

```
https://cdn.jsdelivr.net/gh/<YOUR_GITHUB_USER>/hypnotix-news@main/playlist.m3u
```

类型选 **url**（不是 local）。这样 Hypnotix 每次刷新播放列表都会拉到 Actions 刚生成的版本，你本机不需要跑任何脚本。

## 仓库结构

```
channels.json                 频道清单（唯一需要手改的文件）
playlist.m3u                  生成的播放列表（别手改，Actions 会覆盖）
status.json                   上次运行的解析结果与失败记录
scripts/update_playlist.py    发现直播 ID 并生成 playlist.m3u
.github/workflows/update.yml  定时任务：每 3 小时刷新一次
```

## 工作原理

### 发现机制

对每个 YouTube 频道，请求

```
https://www.youtube.com/channel/<频道ID>/live
```

拿当前正在直播的视频 ID。**注意**：这个 `/live` 端点只能用来**发现**，不能用来**播放**。生成的播放列表统一写成

```
https://www.youtube.com/watch?v=<ID>
```

因为 `watch?v=` 是 Hypnotix 自带的 mpv（libmpv 0.37 + ytdl_hook）能实际解码的形式；`/live` 形式在该引擎下会失败。实测结论，不是推测。

另外，频道 ID 必须是完整的 24 位。截断的短 ID 会让 `/live` 端点返回错误。

### 失败处理

发现失败时按以下顺序回退，绝不空掉一个频道：

1. `status.json` 里上一次成功解析到的 ID（标记 `stale: true`）
2. `channels.json` 里手动写死的 `last_live_id`（pin）

脚本永远以 0 退出，失败只记进 `status.json`，不会让 Actions 的 job 变红。

## 添加频道

编辑 `channels.json`。

YouTube 频道（自动刷新直播 ID）：

```json
{ "name": "频道名", "group": "分组名", "kind": "youtube",
  "channel_id": "UC开头24位完整ID" }
```

固定 HLS 地址（不参与刷新）：

```json
{ "name": "频道名", "group": "分组名", "kind": "hls",
  "url": "https://.../index.m3u8" }
```

`optional` 数组里的频道会被写成注释行，Hypnotix 会跳过它们。这里放的是「地址可达但本机代理拦截了分片」的国际台——如果你的网络没有那个代理，把它们的行首 `#` 去掉就能播。

### 怎么找频道 ID

```
yt-dlp --flat-playlist -J "ytsearch5:频道名 直播"
```

取结果里 `channel_id` 字段，必须是 24 位完整值。

## 手动运行

```
python3 scripts/update_playlist.py
```

需要先装 yt-dlp。环境变量可调：

| 变量 | 默认 | 含义 |
|---|---|---|
| `YTDLP_BIN` | `yt-dlp` | 可执行文件路径 |
| `YTDLP_TIMEOUT` | `45` | 单次请求超时（秒） |
| `YTDLP_RETRIES` | `2` | 失败重试次数 |

## 频率为什么是 3 小时

不是猜的。采集当天观察到：华视、民视、寰宇、台视、中视 5 个频道的直播 ID 数小时内变更，台視在一个半小时里换了两个 ID。设得更慢就会出现死链；再快会频繁触发 GitHub 的 API 配额。3 小时是当前观测下的折中。

## 已知限制

- 只对 YouTube 频道自动刷新；`hls` 类型的固定地址不做健康检查
- GitHub Actions 的 cron 最慢约 1 分钟精度，且免费额度下可能延迟执行，所以实际刷新间隔会有浮动
- 播放列表只保证「URL 当前指向正在直播的视频」，不保证该流在**你的网络**下能拉通分片
