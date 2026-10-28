# 恋活 / Koikatsu

## 卡片

- 人物卡、服装卡、场景卡都是 PNG，图片后面追加 Illusion 数据。
- PNG 结束标记后的 payload 包含卡类型、版本、可选人脸图和 MessagePack 块。
- `KKEx` 块里的 `com.bepis.sideloader.universalautoresolver` → `info` 数组 → 每个 `ResolveInfo` 的 `ModID` 就是所需 zipmod 的 GUID。
- 角色/服装卡支持 KK/KKS；场景卡会额外合并内嵌角色的依赖。

## zipmod

- `.zipmod` 本质是 zip；根目录（或一层内）的 `manifest.xml` 提供 `guid/name/version/author`。
- 服装特征走 `Mods_Clothing`，其他走 `Mods`。
- zipmod 内预览图会自动提取为 `_preview.jpg`。

## 目录

先作者、后 IP：

```
11_Koikatsu/<作者>/<IP>/
├ Cards_Characters/<卡名>/
├ Cards_Clothing/<卡名>/
├ Cards_Scenes/<卡名>/
├ Cards/<卡名>/
├ Mods/<包名>/
└ Mods_Clothing/<包名>/
```

- 作者从 `[作者]`、`by`、目录名提取；未知用 `_UnknownAuthor`。
- IP 从作品名和角色映射识别；未知用 `未分IP`。
- 卡片+MOD 混合包进 `_Packs`，先整包不拆。

## 关联

卡片和 zipmod 都入库后：

```bat
python "D:\ASSETS\_SYSTEM\assets.py" koi-link --apply --shortcuts
```

输出：

- 卡片目录 `_mod_links.txt`：已安装/缺失 GUID、MOD 名称、路径；
- 卡片目录 `_mods/*.lnk`：指向所需 MOD 文件夹的快捷方式；
- `_missing_mods.txt`：缺失 GUID；
- `11_Koikatsu\_Index\卡片MOD依赖.xlsx`：全局依赖表，带路径超链接。

`koi-link` 只报告/建快捷方式，不删除、不移动卡片或 MOD。缺失 MOD 需要用户补，不要用同名文件硬凑。

## 歧义

`爱丽丝`、`千夏`、`安洁莉娜` 这类同名/跨作品角色会进入 `ambiguous`；`needs_ip_lookup=true` 时先问用户/联网确认，再用 `--ip` 入库，不要硬归。
