# Asset Manager Skill

一个面向 **游戏 MOD / MMD / VRChat / 恋活 / VAM / AI 绘画 / 游戏解包 / 教学 / 逆向 / 作者备份** 的本地资源整理 Skill。

它解决三个问题：

1. 不同类型的资源容易混在一起；
2. 资源文件夹只有名字、没有预览，时间久了不知道是什么；
3. 卡片的 MOD 依赖、VAM 整包、模型贴图被误拆，越整理越乱。

核心原则：**域优先、时间排序、预览前置、索引驱动、整包不拆**。

## 功能

- 按域分开：MOD、MMD、VRChat、恋活、VAM、AI、逆向、作者备份等互不混合。
- 资源文件夹统一 `YYYY-MM-DD_名称_作者`，外层分年份。
- 自动生成 `_preview.jpg`；LoRA 额外生成 `.preview.png`。
- 生成 `资源总表.xlsx`（超链接直达文件夹）和 `资源总表.html`（带预览的搜索页）。
- 空间水位 + 软配额 + 近 30 天增长预测，防止爆盘。
- 重复资源按文件夹内容指纹报告，只报告不自动删除。
- 恋活：解析卡片 `KKEx` 和 zipmod `manifest.xml`，按 GUID 生成每卡依赖清单/缺失 MOD/快捷方式。
- VAM：解析 `.var` 的 `meta.json`，整包保留；散装 `.vap/.vac/.cslist` 再分类型。
- IP/角色映射：本地优先，歧义挂起；批量刷新只处理待确认项。
- 支持 `--copy`，外接硬盘资源复制入库、保留源盘。

## 安装

要求：Windows 10/11，Python 3.10+。

```bat
git clone https://github.com/Brind235808/asset-manager-skill.git
cd asset-manager-skill
python -m pip install -r scripts\requirements.txt
powershell -ExecutionPolicy Bypass -File .\install.ps1 -LibraryRoot "D:\ASSETS"
```

`install.ps1` 会：

- 创建 `D:\ASSETS\_SYSTEM`；
- 复制 Python 工具和默认配置；
- 运行 `assets.py init` 创建分类目录、数据库和总表；
- **不会移动任何现有资源**。

然后把仓库目录复制到 Qoder 用户技能目录：

```bat
xcopy /E /I asset-manager-skill "%USERPROFILE%\.qoder-cn\skills\asset-manager"
```

重启 Qoder 后即可在对话里使用 `asset-manager` 技能。

## 快速开始

```bat
python "D:\ASSETS\_SYSTEM\assets.py" analyze "D:\Downloads\某个资源"
python "D:\ASSETS\_SYSTEM\assets.py" ingest "D:\Downloads\某个资源" --apply
python "D:\ASSETS\_SYSTEM\assets.py" scan
python "D:\ASSETS\_SYSTEM\assets.py" dashboard
python "D:\ASSETS\_SYSTEM\assets.py" space
python "D:\ASSETS\_SYSTEM\assets.py" dupes
```

默认 `ingest` 只预演，确认后加 `--apply`。外接盘用 `--copy --apply`。

## 目录结构

```
<LibraryRoot>\
├ 00_INBOX
├ 01_GameMods
├ 02_MMD
├ 03_VRChat
├ 04_GameRips
├ 05_AI_Art
├ 06_Tutorials
├ 07_Reverse
├ 08_AuthorBackups
├ 09_GitHub
├ 10_AI_Work
├ 11_Koikatsu
├ 12_VAM
├ 90_Apps
├ 99_ARCHIVE
└ _SYSTEM
```

完整规则见 [references/taxonomy.md](references/taxonomy.md)。

## 文档

- [SKILL.md](SKILL.md)：Agent 操作说明
- [references/taxonomy.md](references/taxonomy.md)：分类树与命名规则
- [references/koikatsu.md](references/koikatsu.md)：恋活卡片/zipmod/GUID 关联
- [references/vam.md](references/vam.md)：VAM VAR 与散件
- [references/ip-mapping.md](references/ip-mapping.md)：IP/角色映射来源与构建
- [references/space-and-dedup.md](references/space-and-dedup.md)：空间、配额、重复检测、迁移

## 关于映射数据

仓库**不附带**完整的 `ip_map.json` / `acg_ip_map.json` / 第三方抓取缓存，原因：

- Moegirl 数据内容遵循 CC BY-NC-SA，适合个人本地使用，不适合直接再分发大份数据；
- Bangumi / B站 wiki / Fandom 各有使用条款；
- 映射表会随新角色变化，应该本地构建，而不是发布一个快速过期的快照。

仓库提供构建脚本和样例：

```bat
python "D:\ASSETS\_SYSTEM\wiki_ip_map.py" --apply
python "D:\ASSETS\_SYSTEM\acg_ip_map.py" --apply
```

具体数据源、缓存路径和许可说明见 [references/ip-mapping.md](references/ip-mapping.md)。

## 安全边界

- 不删除用户资源；重复项只报告。
- 不移动已安装软件、聊天记录、Qoder 会话、正在引用的工程。
- 业务/公司资料不在范围内。
- 移动前检查空间水位；低于水位直接拒绝。
- 模型贴图、动作包、Koikatsu 卡片/zipmod、VAM VAR 包永远整包处理。

## 许可

代码采用 MIT License，见 [LICENSE](LICENSE)。

第三方数据源、工具与格式参考见 [THIRD_PARTY.md](THIRD_PARTY.md)。仓库中的分类规则和文档可自由修改；用户自己的资源不随仓库分发。
