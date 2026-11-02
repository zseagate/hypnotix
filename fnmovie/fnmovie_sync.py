#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fnMovie IPTV 同步：维持"综合直播(BBC/CNN) + 春节联欢晚会"两个库。

- 综合直播：BBC News（akamaized 直连）和 CNN International（走本地拉平
  /cnn.m3u8，避免 fnMovie 播 master 相对路径失败）。
- 春节联欢晚会：沿用用户原先 22 个春晚条目（备份库 220930）。
- 删除 电影频道 / 体育直播 / 国际频道。
- 逐条探活，只保留可播放的；按 fnMovie 导入格式直接写库（它的自动刷新
  不可靠）。幂等可重复执行。
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import os
import sqlite3
import ssl
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

DB = "/usr/local/apps/@appdata/trim.media/database/trimmedia.db"
GALA_BACKUP = "/root/fnmovie-backup/trimmedia.db.20261101_220930"
ALL_BACKUP = "/root/fnmovie-backup/trimmedia.db.libraries.20261101_223031"
SRV = Path("/opt/fnmovie-iptv/srv")
CHINESE_M3U = SRV / "chinese.m3u8"
GALA_M3U = SRV / "gala.m3u8"
USER = "7b680fa9347c4aa6a5810e91b2ce93be"
CN_LIB = "3e4af7c84e724c5f81827d5cedb0879a"           # 综合直播
DEL_LIBS = [
    "122d3f88b4c746388bbb19f3ef51584d",   # 电影频道
    "7d3b63f377624141a5e3cc9d57bc807f",   # 体育直播
    "9c46f06646964977b9796ff8ed064161",   # 国际频道
]
CNN_URL = "http://192.168.10.100:18080/cnn.m3u8"
CNN_MEDIA = "21656301cb52fc1dcd2eecaacece0f4c901a991931c31c44c313544012b1bc95"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def log(m: str) -> None:
    print("[%s] %s" % (time.strftime("%F %T"), m), flush=True)


def probe_one(url: str) -> bool:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "*/*", "Range": "bytes=0-2047"})
    try:
        with urllib.request.urlopen(req, timeout=8, context=CTX) as r:
            code = r.getcode()
            data = r.read(4096)
            return (200 <= code < 400
                    and (len(data) > 0 or
                         int(r.headers.get("Content-Length") or 0) > 0))
    except Exception:  # noqa: BLE001
        return False


def probe(urls: list[str]) -> dict[str, bool]:
    ok = {}
    with cf.ThreadPoolExecutor(max_workers=40) as ex:
        futs = {ex.submit(probe_one, u): u for u in urls}
        for i, fut in enumerate(cf.as_completed(futs), 1):
            u = futs[fut]
            try:
                ok[u] = fut.result()
            except Exception:  # noqa: BLE001
                ok[u] = False
            if i % 100 == 0:
                log("  探活 %d/%d" % (i, len(urls)))
    return ok


def read_gala() -> list[tuple[str, str, str]]:
    c = sqlite3.connect(GALA_BACKUP)
    rows = c.execute(
        "select i.guid, i.title, m.path from item i "
        "join item_media m on m.item_guid=i.guid "
        "where i.type='LiveChannel' and i.title like '%春晚%' "
        "order by i.title").fetchall()
    c.close()
    return rows


def read_bbccnn() -> list[tuple[str, str, str, int]]:
    """返回 [(item_guid, title, media_guid, media_path)]，按 sort_num 排序。

    BBC 有两条媒体：akamaized 固定 4K 和 fastly 多码率自适应。把 fastly
    自适应流放第一位（默认加载），akamaized 4K 放第二位（手动可切换），
    这样开播先起低码率、启动更快。
    """
    c = sqlite3.connect(ALL_BACKUP)
    rows = []
    for name in ("BBC News", "CNN International"):
        g = c.execute("select guid from item where type='LiveChannel' and title=?",
                      (name,)).fetchone()
        if not g:
            continue
        media = c.execute("select guid, path, sort_num from item_media "
                          "where item_guid=? order by sort_num", (g[0],)).fetchall()
        # fastly 自适应流优先，akamaized 次之
        media.sort(key=lambda m: (0 if "fastly" in (m[1] or "") else 1))
        for m in media:
            rows.append((g[0], name, m[0], m[1]))
    c.close()
    return rows


def delete_library(cur, lib: str) -> None:
    ch = [r[0] for r in cur.execute(
        "select item_guid from item_ancestor where ancestor_guid=?", (lib,))]
    for table, col in [("item_tag", "item_guid"), ("item_ancestor", "item_guid"),
                       ("item_ancestor", "ancestor_guid"), ("item_media", "item_guid"),
                       ("item_user", "item_guid"), ("item", "guid")]:
        for i in range(0, len(ch), 500):
            chunk = ch[i:i + 500]
            if chunk:
                cur.execute('delete from "%s" where "%s" in (%s)'
                            % (table, col, ",".join("?" * len(chunk))), chunk)
    for table, col in [("item_ancestor", "ancestor_guid"),
                       ("mediadb_config", "item_guid"),
                       ("item_user", "item_guid"),
                       ("item", "guid")]:
        cur.execute('delete from "%s" where "%s"=?' % (table, col), (lib,))


def upsert_library(cur, guid: str, title: str, url: str) -> None:
    now = int(time.time() * 1000)
    hit = cur.execute("select item_guid from mediadb_config where iptv_source_url=?",
                      (url,)).fetchone()
    if hit and hit[0] != guid:
        # 同 URL 不同 guid（理论不会发生）：改绑
        delete_library(cur, hit[0])
    cur.execute("delete from item where guid=?", (guid,))
    cur.execute("delete from mediadb_config where item_guid=?", (guid,))
    cur.execute("delete from item_user where item_guid=?", (guid,))
    cur.execute("""insert into item (guid, type, title, sort_title, sort_num,
                   status, fetch_status, parent_guid, create_time, update_time)
                   values (?, 'MediaDB', ?, ?, 2147483647, '1', 0, '', ?, ?)""",
                (guid, title, title, now, now))
    cur.execute("""insert into mediadb_config
                   (item_guid, dir_list, subtitle_lan, auto_scrap_subtitle, category,
                    create_time, update_time, include_adult, view_type,
                    auto_progress_thumb, skip_filesize, poster_type, prefer_local_nfo,
                    iptv_source_type, iptv_source_url, iptv_refresh_interval,
                    iptv_refresh_enabled, iptv_last_refresh_status,
                    iptv_last_refresh_time, iptv_last_success_time, iptv_last_error,
                    iptv_channel_count, iptv_line_count, iptv_invalid_count)
                   values (?, '[]', '', 0, 'IPTV', ?, ?, 0, 0, 0, 3, 0, 0,
                           'url', ?, 21600, 0, 'success', 1, 1, '', 0, 0, 0)""",
                (guid, now, now, url))
    cur.execute("""insert into item_user (user_guid, item_guid, is_admin,
                   create_time, update_time) values (?, ?, 1, ?, ?)""",
                (USER, guid, now, now))


def import_channel(cur, lib: str, item_guid: str, title: str,
                   media_guid: str, media_path: str, genre: str, sort_num: int,
                   media_sort: int = 0) -> None:
    now = int(time.time() * 1000)
    d = media_path.rsplit("/", 1)[0]
    cur.execute("""insert or replace into item
                   (guid, type, title, sort_title, sort_num, status, fetch_status,
                    parent_guid, path, create_time, update_time)
                   values (?, 'LiveChannel', ?, ?, ?, '1', 1, '', '', ?, ?)""",
                (item_guid, title, "2|" + title.lower(), sort_num, now, now))
    cur.execute("""insert or replace into item_media
                   (guid, item_guid, dir, path, size, can_play, type, sort_num,
                    mod_time, file_hash, create_time, update_time, file_birth_time,
                    recognition_status, cloud_storage_type, mount_path)
                   values (?, ?, ?, ?, 0, 1, 3, ?, 0, ?, ?, ?, 0, 1, 0, '')""",
                (media_guid, item_guid, d, media_path, media_sort,
                 media_guid, now, now))
    # item_ancestor 无主键：先删后插，避免同一频道多媒体时重复插入
    cur.execute("delete from item_ancestor where item_guid=? and ancestor_guid=?",
                (item_guid, lib))
    cur.execute("insert into item_ancestor "
                "(item_guid, ancestor_guid, create_time, update_time) "
                "values (?, ?, ?, ?)", (item_guid, lib, now, now))
    cur.execute("insert or replace into item_tag (item_guid, tag, type) "
                "values (?, ?, 'Genre')", (item_guid, genre))
    cur.execute("insert or replace into item_user "
                "(user_guid, item_guid, is_admin, create_time, update_time) "
                "values (?, ?, 1, ?, ?)", (USER, item_guid, now, now))


def main() -> None:
    SRV.mkdir(parents=True, exist_ok=True)

    gala = read_gala()
    bbcnn = read_bbccnn()
    log("春晚 %d 条，BBC/CNN 媒体 %d 条" % (len(gala), len(bbcnn)))

    # 探活：春晚 + BBC/CNN 上游（CNN 用本地代理无需探上游）
    urls = sorted({u for _, _, u in gala} | {p for _, _, _, p in bbcnn
                                            if "cloudfront" not in p})
    log("探活 %d 个地址……" % len(urls))
    ok = probe(urls)

    good_gala = [(g, t, u) for g, t, u in gala if ok.get(u)]
    # BBC/CNN：CNN 主媒体改走本地代理；BBC 直连保持。
    # 只保留探活可用的媒体（fastly 整机 403 会被探活剔除，避免"切换无法播放"）。
    entries = []
    for ig, title, mg, mp in bbcnn:
        if "CNN International" == title and "cloudfront" in mp:
            mp = CNN_URL
        if mp == CNN_URL or ok.get(mp):
            entries.append((ig, title, mg, mp))
    log("春晚可用 %d/%d；BBC/CNN 保留 %d 条媒体（剔除探活失败）"
        % (len(good_gala), len(gala), len(entries)))

    # 写播放列表
    def write_m3u(path: Path, group: str, rows: list[tuple[str, str]]) -> None:
        body = ["#EXTM3U"]
        for title, url in rows:
            body.append('#EXTINF:-1 group-title="%s",%s' % (group, title))
            body.append(url)
        path.write_text("\n".join(body) + "\n", encoding="utf-8")

    write_m3u(GALA_M3U, "春晚", [(t, u) for _, t, u in good_gala])
    # 综合直播列表：BBC 主媒体 + CNN(本地代理)
    ch_rows = []
    for ig, title, mg, mp in entries:
        if title == "CNN International":
            ch_rows.append(("CNN International", CNN_URL))
    for ig, title, mg, mp in entries:
        if title == "BBC News":
            ch_rows.append((title, mp))
            break
    write_m3u(CHINESE_M3U, "综合", ch_rows)
    log("已写 chinese.m3u8（%d）和 gala.m3u8（%d）" % (len(ch_rows), len(good_gala)))

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    try:
        for lib in DEL_LIBS:
            delete_library(cur, lib)
            log("已删除库 %s" % lib)
        upsert_library(cur, CN_LIB, "综合直播", "http://1.1.1.246:18080/chinese.m3u8")
        gala_lib = uuid.uuid4().hex
        upsert_library(cur, gala_lib, "春节联欢晚会", "http://1.1.1.246:18080/gala.m3u8")

        # 清空待导入库的旧频道
        for lib in (CN_LIB, gala_lib):
            ch = [r[0] for r in cur.execute(
                "select item_guid from item_ancestor where ancestor_guid=?", (lib,))]
            for table, col in [("item_tag", "item_guid"), ("item_ancestor", "item_guid"),
                               ("item_media", "item_guid"), ("item_user", "item_guid"),
                               ("item", "guid")]:
                for i in range(0, len(ch), 500):
                    chunk = ch[i:i + 500]
                    if chunk:
                        cur.execute('delete from "%s" where "%s" in (%s)'
                                    % (table, col, ",".join("?" * len(chunk))), chunk)

        n1 = 0
        media_idx = {}
        for ig, title, mg, mp in entries:
            msort = media_idx.get(ig, 0)
            import_channel(cur, CN_LIB, ig, title, mg, mp, "32", n1 + 1, msort)
            media_idx[ig] = msort + 1
            n1 += 1
        n2 = 0
        for g, t, u in good_gala:
            import_channel(cur, gala_lib, g, t, hashlib.sha256(u.encode()).hexdigest(),
                           u, "106", n2 + 1, 0)
            n2 += 1

        now = int(time.time() * 1000)
        for lib, n in ((CN_LIB, n1), (gala_lib, n2)):
            cur.execute("""update mediadb_config set
                iptv_last_refresh_time=?, iptv_last_success_time=?,
                iptv_last_refresh_status='success', iptv_last_error='',
                iptv_channel_count=?, iptv_line_count=?, iptv_invalid_count=0,
                iptv_refresh_enabled=0, update_time=?
                where item_guid=?""", (now, now, n, n, now, lib))
        conn.commit()
        log("导入综合 %d、春晚 %d" % (n1, n2))
        for r in conn.execute("""select i.title, c.iptv_source_url,
                                 (select count(*) from item_ancestor a
                                  where a.ancestor_guid=i.guid)
                          from mediadb_config c join item i on i.guid=c.item_guid
                          where c.category='IPTV' order by i.sort_num"""):
            log("  %s -> %d 台" % (r[0], r[2]))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
