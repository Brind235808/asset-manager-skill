---
name: asset-manager
description: 把 MOD、MMD、VRChat、恋活/Koikatsu 卡片与 MOD、VAM 包与散件、AI 绘画、游戏解包、教学、逆向、作者备份等资源归类到按域分开的资源库，生成预览图、依赖清单、空间预测和可点击总表。Use when the user asks 归类、整理、收纳、放哪、收件箱、资源总表, or mentions MOD/MMD/VRChat/恋活/Koikatsu/人物卡/服装卡/场景卡/zipmod/VAM/Virt-A-Mate/.var/.vap/LoRA/ComfyUI/解包/教程 资源入库. Do not use for business documents, normal code projects, or deleting resources.
---

# Asset Manager / 资源库管理

把收藏型资源按“域优先、时间排序、预览前置、索引驱动”整理。资源单位是文件夹或整包，不是单个文件；模型贴图、动作音频镜头、Koikatsu 卡片依赖、VAM VAR 包都不拆。

## 安装

1. 克隆/复制本仓库到 Qoder 用户技能目录，例如：
   `%USERPROFILE%\.qoder-cn\skills\asset-manager`
2. 在仓库根目录把脚本部署到资源库：
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\install.ps1 -LibraryRoot "D:\ASSETS"
   ```
   脚本会创建 `<LibraryRoot>\_SYSTEM`，复制 Python 工具和默认配置，并执行初始化。不会移动任何现有资源。
3. 依赖：
   ```bat
   python -m pip install -r scripts\requirements.txt
   ```
   Pillow 用于预览，msgpack 用于 Koikatsu 卡片解析，openpyxl 用于 Excel 总表（可选）。

默认资源库根目录 `D:\ASSETS`，可在安装时改；工具文件位于 `<LibraryRoot>\_SYSTEM`。

## 硬性规则

1. **资源单位是文件夹或整包。** 模型贴图、动作 VMD+音频+镜头、Koikatsu 卡片/zipmod、VAM `.var`、作者备份都保持完整，不按扩展名拆。
2. **不删除源文件。** `ingest` 默认预演；`--apply` 才移动；`--copy` 复制入库并保留源盘。
3. **不跨域混放。** MOD、MMD、VRChat、恋活、VAM、AI、逆向、作者备份各自独立大类。
4. **空间不足就停。** 移动/复制前检查目标盘剩余空间和安全水位；低于水位拒绝执行。
5. **业务资料不碰。** 公司、1688、客户、销售资料不在本技能范围。
6. **不确定就问一次。** 分类、IP、作者有歧义时只给出候选，不硬猜。

## 标准流程

### 1. 分析

```bat
python "D:\ASSETS\_SYSTEM\assets.py" analyze "<路径>" --json
```

看 `category`、`confidence`、`needs_review`、`ip`、`ip_source`、`needs_ip_lookup`、`destination`、`space.ok`。

- `needs_ip_lookup=true`：只对这一条联网或问用户确认 IP；不要硬猜，也不要 `--force` 跳过。确认后用 `ip-map-add` 记录，再用 `--ip` 入库。
- `needs_review=true`：说明前两个候选分类，等用户确认后用 `--category`。
- `space.ok=false`：停止，报告缺口，建议清理重复或冷备。

### 2. 执行

```bat
python "D:\ASSETS\_SYSTEM\assets.py" ingest "<路径>" --apply
python "D:\ASSETS\_SYSTEM\assets.py" ingest "<路径>" --copy --apply
```

有歧义但用户已确认：

```bat
python "D:\ASSETS\_SYSTEM\assets.py" ingest "<路径>" --category "02_MMD/Models" --force --apply
```

常用参数：`--game`、`--ip`、`--base`、`--title`、`--author`、`--source`、`--tags`、`--project`、`--register`。

`--register` 只原地登记、不移动，适合正在用或体积大的文件夹。

### 3. 总表

```bat
python "D:\ASSETS\_SYSTEM\assets.py" dashboard
python "D:\ASSETS\_SYSTEM\assets.py" space
python "D:\ASSETS\_SYSTEM\assets.py" dupes
```

输出：

- `资源总表.xlsx`：大类导航 + 资源清单，超链接直接打开资源管理器
- `资源总表.html`：带预览图的搜索/筛选页面
- `space`：各域占用、配额、近 30 天增长预测
- `dupes`：重复资源回收报告，只报告不删除

## 大类与细节

完整目录树见 [references/taxonomy.md](references/taxonomy.md)。

- `01_GameMods`：3dmigoto/XXMI MOD，按游戏分；工程在 `_Projects`，工具在 `_Tools`。
- `02_MMD`：PMX/FBX、动作、MD 布料、材质、参考、场景、工程、工具。
- `03_VRChat`：模型、衣服、工程、工具。
- `04_GameRips`：解包包体、FBX、贴图，按游戏。
- `05_AI_Art`：LoRA/Checkpoint 按底模、工作流、ComfyUI、工具、参考、产出。
- `06_Tutorials`、`07_Reverse`、`08_AuthorBackups`、`09_GitHub`、`10_AI_Work`、`90_Apps`。
- `11_Koikatsu`：**先作者、后 IP**；卡片、zipmod、插件分开，卡片依赖用 GUID 关联。
- `12_VAM`：`.var` 整包进 `Packages/<作者>`；散装 `.vap/.vac/.cslist` 再分类型。

## 恋活

- 卡片 PNG 尾部的 `KKEx` 会解析出 zipmod GUID；zipmod 的 `manifest.xml` 提供自己的 GUID。
- 卡片和 zipmod 入库后：
  ```bat
  python "D:\ASSETS\_SYSTEM\assets.py" koi-link --apply --shortcuts
  ```
  会在每张卡下生成 `_mod_links.txt`、`_mods` 快捷方式和 `_missing_mods.txt`，并输出 `11_Koikatsu\_Index\卡片MOD依赖.xlsx`。
- 详见 [references/koikatsu.md](references/koikatsu.md)。

## VAM

- `.var` 本质是 zip，一个包可能同时含人物、场景、服装、头发、插件；**整包保留**。
- 解析包内 `meta.json` 的 `creatorName`/`packageName`/`contentList`，类型只做标签。
- 散装 `.vap` 按路径里的 Appearance/Clothing/Hair/Pose/Morph 分；`.vac`/场景 JSON、`.cslist`、VAM 用 `.vmd` 分别进 Scenes/Plugins/Animations。
- 详见 [references/vam.md](references/vam.md)。

## IP / 角色映射

- 游戏/MOD 用 `ip_map.json`：IP 别名 → 角色 → 作者提示；未命中或多 IP 会进入 `needs_ip_lookup`，不硬归。
- 构建/刷新：`python "D:\ASSETS\_SYSTEM\wiki_ip_map.py" --apply`（Bangumi + B站 wiki + 可选图标源；需要网络和缓存）。
- 人工补充：`ip-map-add "角色" "作品" --aliases "英文名,别名"`。
- 待确认：`ip-review --apply`。
- ACG/AI 内容整理用单独的 `acg_ip_map.json` 和 `acg_ip_map.py`，不混进 MOD 分类；完整构建方式见 [references/ip-mapping.md](references/ip-mapping.md)。
- 仓库 `data/` 附带构建好的映射快照；安装时只在目标不存在时复制，不覆盖已有表。数据来源与许可见 [DATA_LICENSE.md](DATA_LICENSE.md)。

## 空间、重复与迁移

- 目标盘默认保留 25G 安全水位；C 盘只放软件和索引。
- 配额是软上限，真正阻止爆盘的是水位检查。
- 重复检测按文件夹内容指纹；只报告，不自动删。
- 批量迁移先 `plan` 生成 CSV，再分批 `ingest`，不要静默搬完整盘。详见 [references/space-and-dedup.md](references/space-and-dedup.md)。

## 完成标准

- 源路径已移动/复制到目标，文件数和体积校验一致；
- `_asset.json`、`_preview.jpg`、总表已更新；
- 空间检查通过；
- 没有拆开模型贴图、动作包、Koikatsu 卡片/MOD、VAM VAR 包；
- 汇报目标路径、体积、分类/置信度、预览和空间状态。
