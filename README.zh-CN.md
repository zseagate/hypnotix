# hypnotix

**简体中文** | [English](README.md)

一套让 [Hypnotix](https://hypnotix.org) 电视在 Ubuntu（Cinnamon 桌面）上顺畅工作的配置记录、精选新闻播放列表和配套工具，
整理自 2026 年 10 月的一次排障过程。所有结论都在这台机器的真实播放引擎 `libmpv 0.37` 上验证过，
而不是只看「HTTP 返回 200」。

---

## 目录结构

```
channels.json               新闻频道清单（YouTube / HLS 混排），Actions 据此再生 playlist.m3u
playlist.m3u                由 GitHub Actions 每 3 小时自动再生的直播列表（勿手改）
status.json                 最近一次再生的结果（成功/失败频道）
sync.sh                     本地一键同步器：拉仓库快照 + 刷新上游 + 导入 Hypnotix
playlists/
  news.m3u                  人工精选新闻列表，每个频道都经过播放验证
  iptvorg*.m3u              来自 iptv-org 的各国/各类列表（CN/HK/TW/ZH/Sports/Movies）
  freetv.m3u freetvcdn.m3u  来自 Free-TV/IPTV 的公共频道大列表
scripts/
  import_local.py           一键本地秒级导入（推荐）：local/file:// 不走下载，--strip-logos 去台标极速模式
  update_playlist.py        用 yt-dlp 解析 YouTube 直播 ID 并再生 playlist.m3u
  add_providers.py          把经过验证的 provider 写入 org.x.hypnotix.providers
  verify_providers.py       用 Hypnotix 自己的 Manager 代码测试候选 provider
  verify_news.py            校验已配置的 provider（也可传入额外参数）
  classify.py               逐流 libmpv 解码测试，对比走代理 / 直连
  mpv_all.py                权威播放矩阵（新闻 + YouTube 直播 + 基准流）
  playback_test.py          libmpv 探测，要求音视频格式齐全且时间在推进
  yttest.py                 单条 YouTube 直播流探测并 dump mpv 日志
  durtest.py                YouTube 频道 /live 与 @handle/live 两种 URL 形式对比
  ffcheck.sh                ffmpeg/ffprobe 批量播放检查（CSV：名称<TAB>URL）
  check.sh                  curl 版播放列表 HTTP/大小/频道数检查
  t.sh                      curl 版快速分片计数检查
  diag.py  mpvopt.py        mpv 日志 dump / 选项敏感性探测
  init_test.py              在 Hypnotix 的参数集下 libmpv 能否初始化
  zbdstest.py               单流探测，逐 tick 记录属性
```

---

## 快速开始

### 1. 安装依赖

```bash
sudo apt install hypnotix yt-dlp ffmpeg curl
```

### 2. 先体检，再导入

```bash
# 检查新闻列表是否健康
python3 scripts/verify_news.py

# 安装公共 provider 集合
python3 scripts/add_providers.py
```

### 3. 本地快速导入（推荐，秒级）

关键点：用 `file://` 的 **local** 类型，Hypnotix 直接读本地文件，**完全不发起下载**，
比 `url` 类型快 1~2 个数量级。

```bash
python3 scripts/import_local.py --list                 # 查看预设
python3 scripts/import_local.py                        # 默认导入 News/News-Auto/CN/HK/TW
python3 scripts/import_local.py --all --strip-logos    # 全部 + 去台标极速版（2000+ 台也不卡）
python3 scripts/import_local.py --name MyTV --file ~/my.m3u   # 导入任意本地 m3u
```

### 4. 校验 Hypnotix 实际加载的频道

```bash
python3 scripts/verify_news.py
```

### 手动把新闻列表加为本地 provider

```bash
python3 - <<'EOF'
from gi.repository import Gio
s = Gio.Settings.new("org.x.hypnotix")
p = s.get_strv("providers")
n = "News:::local:::file:///path/to/playlists/news.m3u:::::::::"
if n not in p:
    s.set_strv("providers", p + [n])
EOF
```

> **动手改 dconf 前一定要先备份——dconf 没有撤销：**
> ```bash
> dconf dump /org/x/hypnotix/ > /tmp/hypnotix_backup_$(date +%Y%m%d_%H%M%S).txt
> ```

mpv 相关脚本会把日志写到临时目录，默认 `/tmp/opencode`：

```bash
mkdir -p /tmp/opencode
```

`scripts/verify_news.py` 默认相对仓库解析 `playlists/news.m3u`，
也可以用 `NEWS_M3U=/path/to/file.m3u` 指向别处。

---

## 定期自动更新

节目源会失效、YouTube 直播 ID 会轮换，所以需要定时刷新。这里有两套方案，按需要选用。

### 方案 A：`sync.sh` 全量同步（推荐，本项目实际使用）

`sync.sh` 做四件事：

1. 从 `codeload.github.com` 拉取 `main` 分支的仓库快照（本机直连 github.com 的 TLS 被拦，走 codeload 等价通道）；
2. 用快照刷新本地 `playlists/*.m3u`、`playlist.m3u`、`channels.json`、`status.json`；
3. 从上游刷新各国列表：iptv-org（`import_local.py --update`）+ Free-TV（改用 jsDelivr CDN，因为 raw.githubusercontent 被拦）；
4. 以 `local(file://)` + 去台标极速模式导入 Hypnotix providers。

手动执行：

```bash
./sync.sh
```

默认导入参数可在脚本头部修改（`IMPORT_ARGS`），默认是：

```bash
IMPORT_ARGS=(--all --strip-logos --update --skip-news)
```

日志写到仓库根目录 `update.log`，超过 512KB 自动截尾。

**部署成 systemd user timer（每 3 小时，对齐 GitHub Actions 周期）：**

```ini
# ~/.config/systemd/user/hypnotix-news-sync.service
[Unit]
Description=Hypnotix 播放列表同步+导入 (sync.sh)

[Service]
Type=oneshot
WorkingDirectory=/home/<你的用户名>/project/hypnotix
ExecStart=/home/<你的用户名>/project/hypnotix/sync.sh
```

```ini
# ~/.config/systemd/user/hypnotix-news-sync.timer
[Unit]
Description=每 3 小时同步 hypnotix 播放列表

[Timer]
OnBootSec=5min
OnUnitActiveSec=3h
RandomizedDelaySec=10min
AccuracySec=1min
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now hypnotix-news-sync.timer

# 让它在注销后也能运行（需要 sudo 密码）
sudo loginctl enable-linger "$USER"

# 查看
systemctl --user list-timers hypnotix-news-sync.timer
systemctl --user status hypnotix-news-sync.service
journalctl --user -u hypnotix-news-sync.service -e
```

> 未开启 linger 时，user 级 systemd 只在登录状态下运行；开启后即使注销图形界面也会照常定时执行。

### 方案 B：`import_local.py --install-cron`（轻量，crontab）

只刷新 iptv-org / Free-TV 上游并重新导入，不拉仓库快照：

```bash
# 先从上游刷新再导入，并装上 crontab 每 6 小时自动重复（装完立即跑一次）
python3 scripts/import_local.py --update --install-cron

python3 scripts/import_local.py --update --install-cron --interval-hours 12  # 改周期
python3 scripts/import_local.py --update --skip-news    # 手动刷新一次，跳过 yt-dlp 再生
python3 scripts/import_local.py --uninstall-cron        # 卸载定时任务
```

> 注意：部分环境下 `/var/spool/cron` 写权限受限，`crontab` 可能报 `权限不够`。
> 遇到这种情况改用方案 A 的 systemd user timer 即可，不依赖 cron 权限。

---

## 工作原理与关键要点

### Hypnotix provider 是「位置式」格式

```
name:::type:::url:::user:::pass:::epg
```

六个字段，空字段也要保留 `:`。`type` 为 `url` 或 `local`；
`local` 时 `url` 字段填 `file://` 路径，Hypnotix 会剥掉前缀当作本地文件读取。

### 本地 `file://` 导入为什么快

`type=url` 时 Hypnotix 每次打开都要用 `requests` 下载整个 m3u；`type=local` + `file://`
则直接读磁盘，省掉网络往返，大列表从「几十秒」降到「毫秒级」。

### 大列表为什么要去台标

freetv / iptv-org 这类列表每个频道都带 `tvg-logo`。Hypnotix 打开分组后会**逐个请求台标**
（每个最多 10s 超时），2000 个频道就是灾难。`--strip-logos` 生成去掉 `tvg-logo` 的
`<原名>.fast.m3u` 再导入，列表秒开，**不影响播放**。

### GitHub Actions 每 3 小时刷新一次

`.github/workflows/update.yml` 每 3 小时（`0 */3 * * *`）运行一次：
用 `yt-dlp` 解析 `channels.json` 里每个 YouTube 频道的当前直播 ID，再生 `playlist.m3u`，
并把结果（含失败清单）写进 `status.json`。台湾新闻频道的直播 ID 几小时内就会轮换，
周期再慢就会留下失效的死链。

### YouTube 直播要用 `watch?v=`，不要用 `/live`

Hypnotix 内置的 `mpv 0.37` 带 `ytdl_hook`：能正常解析
`https://www.youtube.com/watch?v=<id>`，但解析不了
`https://www.youtube.com/channel/<ID>/live` 这种形式。
频道的 `/live` 地址只适合用来**发现**当前直播 ID，不适合用来**播放**。

### 「HTTP 200」不等于「能播」

很多新闻 HLS CDN 会正常返回 master playlist，但本机的本地 HTTP 代理（`127.0.0.1:3067`）
会切断 `.ts` 分片请求，导致 mpv 卡住。`scripts/classify.py` 会把每条流分别走代理和不走代理
各跑一次，帮你区分「真的坏了」还是「本地环境问题」。处于这种状态的频道在 `news.m3u` 里保持注释掉。

### `mpv 0.37` 只暴露旧式属性名

要用连字符形式 `m._get_property("video-format")` / `"time-pos"`，camelCase 简写会抛异常。
另外 `audio-format` 在这个版本即使音频正常也会返回 `"no"`；
请改用 `audio-params` 和日志里的 `AAC 2ch 48000Hz` 来判断。

### 导入脚本的安全设计

`import_local.py --update` 下载新列表时会：

- 先写 `.tmp`，校验 `#EXTM3U` 头；
- 检查台数不骤降（不低于旧文件的 20%）；
- 通过后才原子替换，**任何一步失败都保留旧文件**。

因此定时任务不会把可用的列表搞坏。此外只有 providers 真正变化时才写 dconf 备份，避免堆垃圾文件。

---

## 安全说明

仓库中不包含任何凭据、令牌或密钥。所有流地址均为公开的广播端点。
