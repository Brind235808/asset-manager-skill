# 空间、配额、重复与迁移

## 空间水位

默认：

- C 盘保留 20 GB；
- 资源盘（默认 D）保留 25 GB。

`ingest` / `--copy` 前会计算目标盘剩余空间；低于水位直接拒绝。配额是软提醒，真正阻止爆盘的是水位检查。

## 配额与增长

`config.json` 的 `quotas_gb` 可设每个大类软上限。`scan` 会写入空间快照，`space` 按近 30 天增长预测满盘时间：

```bat
python "D:\ASSETS\_SYSTEM\assets.py" space
```

## 重复

按“文件夹内容指纹”检测（相对路径 + 文件大小；单文件用首尾 1MB 哈希）：

```bat
python "D:\ASSETS\_SYSTEM\assets.py" dupes
```

只报告可回收空间，不自动删除。确认后才手动移入 `99_ARCHIVE`。

## 迁移

1. 先只读分析：
   ```bat
   python "D:\ASSETS\_SYSTEM\assets.py" plan "D:\旧目录" --out migration_plan.csv
   ```
2. 按域分批 `ingest`，每批看日志和校验结果。
3. 同盘移动用原子重命名；跨盘复制后再校验文件数/体积，成功才删源。
4. 外接硬盘/手机资源用 `--copy --apply`，保留源盘。
5. 不移动已安装软件、聊天记录、Qoder 会话、正在引用的工程；大工程可 `register` 原地登记。

## 校验

移动/复制后工具会对比文件数和总字节；不一致会报错。`_SYSTEM\logs\moves.csv` 记录每次移动/复制。

## 归档

`99_ARCHIVE` 只进不出：

- `_DUPES`：确认后的重复项；
- `_COLD`：长期不用的冷备；
- 不把活资源直接移入归档。

## VAM/Koikatsu

- VAM `.var` 可能几十 GB，先 `space`，再 `--copy` 或移动；
- Koikatsu 卡片很小，zipmod 可能很大；依赖缺失先补，不要重复下载整包；
- 大包不要解压后再入库，直接使用整包。
