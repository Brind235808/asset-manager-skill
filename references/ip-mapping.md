# IP / 角色映射

## 两套表，不要混

| 表 | 用途 | 默认位置 |
|---|---|---|
| `ip_map.json` | 游戏 MOD、MMD、Koikatsu 卡片的 IP/游戏识别 | `<LibraryRoot>\_SYSTEM\ip_map.json` |
| `acg_ip_map.json` | AI 生成内容、动漫角色的 IP/作品查询 | `<LibraryRoot>\_SYSTEM\acg_ip_map.json` |

游戏表只有几千个角色，避免几万个动漫角色名干扰 MOD 分类；ACG 表可到几万条，专门给 AI 内容整理用。

## 本地优先

`analyze` 的识别顺序：

1. 路径/文件名里的 IP 别名（原神、Genshin、WWMI…）
2. 角色 → IP 映射
3. 作者提示
4. 仍未命中/多候选 → `needs_ip_lookup=true`，只对这一条联网或问用户，不硬猜

`ingest` 对 `needs_ip_lookup=true` 的恋活卡片/场景卡/卡包会拒绝执行；确认要放未分IP时加 `--ip 未分IP`。

## 构建游戏表

```bat
python "D:\ASSETS\_SYSTEM\wiki_ip_map.py" --apply
```

默认来源：

- **Bangumi v0**：`/v0/search/subjects` + `/v0/subjects/{id}/characters`；
- **B站游戏 wiki**：`https://wiki.biligame.com/<站点>/api.php` 的 `categorymembers`；
- **No-Reload-Mod-Manager auto_icon**：`assets/cloud_data/auto_icon/<游戏>/_icon.json`，用于补新角色英文/罗马音别名。

脚本限速、缓存到 `_SYSTEM\ip_sources`，写入 `meta` / `character_sources`；多 IP/冲突角色进 `ambiguous`，不硬写。旧表会备份为 `ip_map.backup.json`。

人工补充/待确认：

```bat
python "D:\ASSETS\_SYSTEM\assets.py" ip-map-add "角色名" "原神" --aliases "英文名,别名"
python "D:\ASSETS\_SYSTEM\assets.py" ip-review --apply
python "D:\ASSETS\_SYSTEM\assets.py" learn-ip-map "D:\你的\IP\角色目录" --apply
```

## 构建 ACG 表

`acg_ip_map.py` 读取本地缓存：

```
_SYSTEM\ip_sources\moegirl\char2subject.json
_SYSTEM\ip_sources\anime_character_db\characters-data.json
_SYSTEM\ip_sources\anime_character_db\ip-data.json
```

来源：

- [Zzzzzzyt/moegirl-dataset](https://github.com/Zzzzzzyt/moegirl-dataset)（MIT 仓库；萌百内容 CC BY-NC-SA）
- [HatsuSumi/anime-character-database](https://github.com/HatsuSumi/anime-character-database)（仓库未声明统一许可证，公开分发前先确认）

运行：

```bat
python "D:\ASSETS\_SYSTEM\acg_ip_map.py" --apply
python "D:\ASSETS\_SYSTEM\acg_ip_map.py" --lookup "甘雨"
```

结果包含 `characters`、`ambiguous`、`character_subjects` 和来源元数据。多作品角色（如 `爱丽丝`）不会硬归。

## 许可提醒

仓库不附带完整 `ip_map.json` / `acg_ip_map.json` / 抓取缓存。原因是第三方数据条款不同，而且映射会随新角色变化。使用者应自行从来源构建，并遵守各站点条款：

- 萌娘百科内容：CC BY-NC-SA，个人/非商业使用并署名；
- Bangumi、B站 wiki、Fandom、Wikipedia：各自的 API/内容条款；
- No-Reload-Mod-Manager auto_icon：来自公开仓库，使用时保留来源；
- 游戏官方/论坛资料：可能滞后，只用于补新角色，不要当唯一来源。

## 歧义处理

多 IP 角色会进入 `ambiguous`。处理方式：

1. 先问用户有没有明确作品；
2. 或联网确认角色出处；
3. 用 `ip-map-add` 写入 `manual_resolutions`；
4. 单条卡片仍可用 `--ip` 覆盖。

不要用同名文件或猜测硬归。
