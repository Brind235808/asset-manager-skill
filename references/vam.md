# VAM / Virt-A-Mate

## VAR 包

- `.var` 本质是 zip，放在 `AddonPackages` 任意子目录。
- 一个 VAR 可能同时包含人物、场景、服装、头发、插件、依赖；**不能按类型拆开**。
- 包内 `meta.json` 常见字段：
  - `creatorName`：作者
  - `packageName`：包名
  - `contentList`：内容路径列表
  - `dependencies`：依赖包
- `contentList` 路径用于打标签，不用于拆包：
  - `Saves/scene` → 场景
  - `Custom/Atom/Person` → 外观/人物
  - `Custom/Clothing` → 服装
  - `Custom/Hair` → 头发
  - `Morphs` → 变形
  - `Custom/Scripts`/`.cs` → 插件
  - `Custom/Assets`/`Assets` → 资产
  - `Textures` → 贴图
- 包内预览图会提取为 `_preview.jpg`。

## 目录

```
12_VAM/
├ Packages/<作者>/      .var 整包
├ Scenes/               .vac / 场景 JSON
├ Looks/                外观预设
├ Clothing/             服装预设/散件
├ Hair/                 头发
├ Morphs/               变形
├ Poses/                姿势
├ Animations/           动画/VMD
├ Plugins/              .cslist/.cs/dll
├ Assets/               道具/Unity资产
├ Textures/             贴图
├ Presets/              分不清的预设
├ _Unsorted/            暂不认识
└ _Tools/
```

## 散装文件

- `.vap`：预设，按路径里的 Appearance / Clothing / Hair / Pose / Morph 分类。
- `.vac` 或含 `"atoms"` + `"storables"` 的 JSON：场景。
- `.cslist` / `.cs` / `.dll`：插件。
- VAM 使用的 `.vmd`：动画。
- `.vab/.vaj/.vam`：头发/服装/资产，按路径判断；不确定进 Assets 或 `_Unsorted`。

## 依赖

VAR 的 `dependencies` 会写入 `_asset.json`；目前只记录，不自动下载。VAM 场景缺依赖时，按包管理器提示补，不要把依赖解压进场景目录。
