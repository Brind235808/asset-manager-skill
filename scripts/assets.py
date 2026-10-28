#!/usr/bin/env python3
"""Asset library manager for D:\\ASSETS.

Commands: init, analyze, ingest, register, scan, dashboard, space, dupes, plan, list.
Only the standard library is required; Pillow is optional and used for previews.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import uuid
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import koi as koi_tool
except Exception:
    koi_tool = None

IP_HINTS = {
    "原神", "genshin", "崩铁", "星穹", "starrail", "hsr", "鸣潮", "wuthering", "wuwa",
    "绝区零", "zenless", "zzz", "蔚蓝档案", "blue archive", "bluearchive",
    "碧蓝航线", "azur lane", "azurlane", "少女前线", "girls frontline", "gfl",
    "明日方舟", "arknights", "nikke", "胜利女神", "终末地", "endfield",
    "无限暖暖", "尘白", "snowbreak", "东方", "touhou", "fgo", "型月",
    "偶像大师", "idolmaster", "崩坏3", "honkai", "战双", "punishing",
    "原创", "original character", "kk", "kks", "koikatsu", "恋活",
}

SYSTEM = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("ASSETS_ROOT") or SYSTEM.parent).resolve()
CONFIG_PATH = SYSTEM / "config.json"
IP_MAP_PATH = SYSTEM / "ip_map.json"
DB_PATH = SYSTEM / "catalog.db"
INDEX_PATH = ROOT / "资源总表.html"
XLSX_PATH = ROOT / "资源总表.xlsx"
LOG_PATH = SYSTEM / "logs" / "moves.csv"

GB = 1024 ** 3
SKIP_DIRS = {"node_modules", ".git", "__pycache__", "$RECYCLE.BIN", "System Volume Information"}
GENERATED = {"_asset.json", "_preview.jpg"}
BROWSER_IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
ASSET_NAME_EXTS = {
    ".pmx", ".pmd", ".vmd", ".fbx", ".obj", ".gltf", ".glb", ".blend", ".blend1",
    ".zip", ".7z", ".rar", ".zipmod", ".var", ".vap", ".vab", ".vaj", ".vam", ".vac",
    ".cslist", ".png", ".jpg", ".jpeg", ".webp",
    ".safetensors", ".ckpt", ".pt", ".pth", ".unitypackage", ".vrm",
    ".mp4", ".mkv", ".pdf", ".docx", ".pptx", ".txt",
}
VAM_EXTS = {".var", ".vap", ".vab", ".vaj", ".vam", ".vac", ".cslist"}
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".flv", ".wmv", ".mov", ".webm", ".m4v", ".ts"}
DOC_EXTS = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".md", ".txt", ".html", ".htm", ".epub"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tga", ".dds", ".tif", ".tiff"}
ARCHIVE_EXTS = {".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz", ".zipmod", ".var"}
MODEL_EXTS = {".pmx", ".pmd", ".fbx", ".obj", ".gltf", ".glb", ".vrm", ".blend"}
WEIGHT_EXTS = {".safetensors", ".ckpt", ".pt", ".pth"}

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception:
        pass


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def human(num: float) -> str:
    num = float(num or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024 or unit == "TB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.2f} {unit}"
        num /= 1024
    return f"{num:.2f} TB"


def sanitize(name: str, max_len: int = 110) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name)).strip(" .")
    name = re.sub(r"\s+", " ", name)
    if len(name) > max_len:
        name = name[:max_len].rstrip(" .")
    return name or "未命名"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(f"缺少配置文件: {CONFIG_PATH}\n先运行: python \"{Path(__file__)}\" init")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def drive_letter(path) -> str:
    return (os.path.splitdrive(str(Path(path).resolve()))[0].rstrip(":") or "C").upper()


def free_gb(path) -> float:
    return shutil.disk_usage(drive_letter(path) + ":\\").free / GB


def reserve_gb(path, cfg: dict) -> float:
    return float(cfg.get("reserve_gb", {}).get(drive_letter(path), 20))


def is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def split_name(name: str) -> tuple[str, str]:
    stem = Path(name).stem if Path(name).suffix else name
    author = ""
    patterns = [
        r"_by_([^_]+)",
        r"(?:^|[_\-\s])by[_\-\s]+([^_\-\(\)\[\]]+)",
        r"作者[：:_\-\s]*([^\s_\-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, stem, re.I)
        if match:
            author = match.group(1).strip()
            break
    title = stem
    bracket = re.match(r"^\s*[\[【]([^\]】]{2,40})[\]】]\s*", title)
    if not author and bracket:
        candidate = bracket.group(1).strip()
        if candidate.lower() not in IP_HINTS and not any(hint in candidate.lower() for hint in IP_HINTS):
            author = candidate
    if author:
        title = re.sub(r"^\s*[\[【][^\]】]{2,40}[\]】]\s*", "", title)
    title = re.sub(r"_by_[^_]+.*$", "", title, flags=re.I)
    title = re.sub(r"(?:^|[_\-\s])by[_\-\s]+[^_\-\(\)\[\]]+.*$", "", title, flags=re.I)
    title = re.sub(r"[_\-\s]*作者[：:_\-\s]*[^\s_\-]+.*$", "", title)
    title = re.sub(r"[_\-][0-9a-f]{24,}$", "", title, flags=re.I)
    title = re.sub(r"[_\-\s]*[\(\[]\d+[\)\]]$", "", title)
    title = title.strip(" ._-")
    return title or stem, author


def detect_games(text: str, cfg: dict) -> str:
    lower = text.lower()
    for game in cfg.get("games", []):
        for keyword in game.get("keywords", []):
            if keyword.lower() in lower:
                return game["name"]
    return ""


def detect_ip(text: str, cfg: dict) -> str:
    game = detect_games(text, cfg)
    if game:
        return game
    lower = text.lower()
    for item in cfg.get("ips", []):
        for keyword in item.get("keywords", []):
            if keyword.lower() in lower:
                return item["name"]
    if re.search(r"(?<![a-z])oc(?![a-z])", lower):
        return "原创"
    return "未分IP"


def load_ip_map(cfg: dict) -> dict:
    aliases: dict[str, list[str]] = {}
    for game in cfg.get("games", []):
        if game.get("keywords"):
            aliases.setdefault(game["name"], []).extend(game["keywords"])
    for item in cfg.get("ips", []):
        aliases.setdefault(item["name"], []).extend(item.get("keywords", []))
    data = {"version": 1, "ip_aliases": aliases, "characters": {}, "author_hints": {}}
    if IP_MAP_PATH.exists():
        try:
            stored = json.loads(IP_MAP_PATH.read_text(encoding="utf-8"))
            if isinstance(stored.get("conflicts"), list):
                data["conflicts"] = stored["conflicts"]
            for key in ("ip_aliases", "characters", "author_hints", "ambiguous", "character_sources", "meta", "manual_resolutions"):
                if not isinstance(stored.get(key), dict):
                    continue
                if key == "ip_aliases":
                    for ip, values in stored[key].items():
                        existing = data["ip_aliases"].setdefault(ip, [])
                        for value in values:
                            if value not in existing:
                                existing.append(value)
                else:
                    data[key] = stored[key]
        except Exception:
            pass
    return data


def save_ip_map(data: dict):
    IP_MAP_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _term_matches(term: str, hay: str, lower: str) -> bool:
    term_l = term.strip().lower()
    if not term_l:
        return False
    if re.fullmatch(r"[a-z0-9 ._\-]+", term_l):
        return re.search(rf"(?<![a-z0-9]){re.escape(term_l)}(?![a-z0-9])", lower) is not None
    if len(term_l) == 1:
        return re.search(rf"(^|[\\/_\-\s.]){re.escape(term_l)}([\\/_\-\s.]|$)", lower) is not None
    return term_l in lower


def detect_ip_info(text: str, cfg: dict, koi: dict | None = None, author: str = "", strong_text: str | None = None) -> dict:
    data = load_ip_map(cfg)
    hay = text
    if koi and isinstance(koi.get("character"), dict):
        hay += " " + " ".join(str(value) for value in koi["character"].values() if value)
    strong = (strong_text or text)
    if koi and isinstance(koi.get("character"), dict):
        strong += " " + " ".join(str(value) for value in koi["character"].values() if value)
    lower = hay.lower()
    strong_lower = strong.lower()
    candidates = []
    for ip, aliases in data.get("ip_aliases", {}).items():
        best = None
        for alias in aliases:
            if _term_matches(alias, hay, lower):
                score = 100 + len(alias)
                if best is None or score > best[0]:
                    best = (score, alias)
        if best:
            candidates.append({"ip": ip, "source": "alias", "term": best[1], "score": best[0]})
    matched_characters = []
    for term, ip in data.get("manual_resolutions", {}).items():
        if _term_matches(term, strong, strong_lower):
            candidates.append({"ip": ip, "source": "manual", "term": term, "score": 95 + len(term)})
    for term, ip in data.get("characters", {}).items():
        if _term_matches(term, strong, strong_lower):
            matched_characters.append(term)
            candidates.append({"ip": ip, "source": "character", "term": term, "score": 60 + len(term)})
    for term, options in data.get("ambiguous", {}).items():
        if not isinstance(options, list) or not _term_matches(term, strong, strong_lower):
            continue
        term_l = term.lower()
        if any(term_l in longer.lower() and len(longer) > len(term) for longer in matched_characters):
            continue
        candidates.append({
            "ip": "未分IP", "source": "ambiguous", "term": term,
            "score": 90 + len(term), "options": options,
        })
    if author:
        for key, ip in data.get("author_hints", {}).items():
            if key.lower() == author.lower():
                candidates.append({"ip": ip, "source": "author", "term": key, "score": 70})
    if not candidates:
        return {"ip": "未分IP", "source": "unknown", "candidates": [], "needs_lookup": True}
    candidates.sort(key=lambda item: item["score"], reverse=True)
    top_score = candidates[0]["score"]
    top = [item for item in candidates if item["score"] == top_score]
    if len({item["ip"] for item in top}) > 1:
        return {"ip": "未分IP", "source": "ambiguous", "candidates": candidates, "needs_lookup": True}
    best = top[0]
    if best["source"] == "ambiguous":
        return {"ip": "未分IP", "source": "ambiguous", "candidates": candidates, "needs_lookup": True}
    return {"ip": best["ip"], "source": best["source"], "candidates": candidates, "needs_lookup": False}


def detect_base(text: str, meta: dict, cfg: dict) -> str:
    parts = [text]
    for value in meta.get("safetensors_meta", []):
        parts.append(json.dumps(value, ensure_ascii=False))
    blob = " ".join(parts).lower()
    for base in cfg.get("base_models", []):
        for keyword in base.get("keywords", []):
            if keyword.lower() in blob:
                return base["name"]
    return "Other"


def detect_source(path: Path) -> str:
    text = str(path).lower()
    if "tencent files" in text or "qq" in text:
        return "QQ"
    if "baidu" in text or "百度" in text:
        return "百度云"
    if "bilibili" in text or "b站" in text:
        return "B站"
    if "civitai" in text:
        return "Civitai"
    if "github" in text:
        return "GitHub"
    if "3dm" in text:
        return "3DM"
    return ""


def detect_leading_date(name: str) -> str:
    match = re.match(r"^(20\d{2})[-_.](\d{1,2})[-_.](\d{1,2})", name)
    if not match:
        return ""
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
    except ValueError:
        return ""


def detect_date(path: Path, meta: dict, explicit: str | None = None) -> str:
    if explicit:
        try:
            return date.fromisoformat(explicit).isoformat()
        except ValueError:
            pass
    leading = detect_leading_date(path.name)
    if leading:
        return leading
    stamp = meta.get("newest_mtime") or 0
    try:
        result = datetime.fromtimestamp(stamp).date() if stamp else date.today()
    except (OverflowError, OSError, ValueError):
        result = date.today()
    if result > date.today():
        result = date.today()
    if result.year < 2000:
        result = date.today()
    return result.isoformat()


def read_safetensors_meta(path: Path) -> dict:
    try:
        with open(path, "rb") as handle:
            length = int.from_bytes(handle.read(8), "little")
            if 0 < length < 20_000_000:
                header = json.loads(handle.read(length).decode("utf-8", "ignore"))
                return header.get("__metadata__", {}) or {}
    except Exception:
        pass
    return {}


def looks_like_workflow(path: Path) -> bool:
    if path.suffix.lower() != ".json":
        return False
    try:
        if path.stat().st_size > 20_000_000:
            return False
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        return isinstance(data, dict) and "nodes" in data and "links" in data
    except Exception:
        return False


def list_archive(path: Path, cfg: dict, limit: int = 400) -> list[str]:
    names: list[str] = []
    suffix = path.suffix.lower()
    if suffix in {".zip", ".zipmod", ".var"}:
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()[:limit]
        except Exception:
            pass
        return names
    if suffix in {".7z", ".rar"}:
        seven_raw = cfg.get("seven_zip") or ""
        seven = Path(seven_raw) if seven_raw else None
        if not seven or not seven.exists():
            return names
        try:
            result = subprocess.run(
                [str(seven), "l", "-slt", str(path)],
                capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=30,
            )
            for line in result.stdout.splitlines():
                if line.startswith("Path = "):
                    candidate = line[7:].strip()
                    if candidate and Path(candidate).suffix.lower() != suffix:
                        names.append(candidate)
                if len(names) >= limit:
                    break
        except Exception:
            pass
    return names


def compute_stats(path: Path, cfg: dict, collect_names: bool = False, max_entries: int = 300_000) -> dict:
    suffixes: Counter = Counter()
    names: list[str] = []
    entries: list[str] = []
    archives: list[str] = []
    total = 0
    count = 0
    newest = 0.0
    workflow = False
    safetensors_meta: list[dict] = []
    json_checks = 0
    archive_checks = 0

    def add_file(file_path: Path, relative: str):
        nonlocal total, count, newest, workflow, json_checks, archive_checks
        try:
            stat = file_path.stat()
        except OSError:
            return
        total += stat.st_size
        count += 1
        newest = max(newest, stat.st_mtime)
        suffixes[file_path.suffix.lower()] += 1
        if collect_names and len(names) < 400:
            names.append(relative)
        if len(entries) < max_entries:
            entries.append(f"{relative}\t{stat.st_size}")
        suffix = file_path.suffix.lower()
        if suffix in ARCHIVE_EXTS and len(archives) < 1500 and archive_checks < 20:
            archive_checks += 1
            archives.extend(list_archive(file_path, cfg, 300))
        if suffix == ".json" and not workflow and json_checks < 10:
            json_checks += 1
            workflow = looks_like_workflow(file_path)
        if suffix == ".safetensors" and len(safetensors_meta) < 5:
            info = read_safetensors_meta(file_path)
            if info:
                safetensors_meta.append(info)

    if path.is_file():
        add_file(path, path.name)
    else:
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for filename in filenames:
                lower = filename.lower()
                if filename in GENERATED or lower.endswith(".preview.png"):
                    continue
                file_path = Path(dirpath) / filename
                try:
                    relative = file_path.relative_to(path).as_posix()
                except ValueError:
                    relative = filename
                add_file(file_path, relative)

    entries.sort()
    if len(entries) >= max_entries:
        entries.append(f"__truncated__\t{count}\t{total}")
    signature = hashlib.sha1("\n".join(entries).encode("utf-8", "ignore")).hexdigest()
    if count == 1 and path.is_file():
        try:
            with open(path, "rb") as handle:
                head = handle.read(1024 * 1024)
                handle.seek(max(0, path.stat().st_size - 1024 * 1024))
                tail = handle.read(1024 * 1024)
            signature = hashlib.sha1(head + tail + str(total).encode()).hexdigest()
        except OSError:
            pass
    return {
        "size_bytes": total,
        "file_count": count,
        "suffixes": suffixes,
        "names": names,
        "archive_names": archives,
        "newest_mtime": newest,
        "is_workflow": workflow,
        "safetensors_meta": safetensors_meta,
        "signature": signature,
    }


def find_preview(path: Path) -> Path | None:
    candidates: list[Path] = []

    def consider(file_path: Path):
        if file_path.suffix.lower() not in BROWSER_IMAGES:
            return
        try:
            if file_path.stat().st_size < 512:
                return
        except OSError:
            return
        candidates.append(file_path)

    if path.is_file():
        stem = path.stem.lower()
        try:
            for sibling in path.parent.iterdir():
                if sibling.is_file():
                    consider(sibling)
        except OSError:
            pass

        def prelim(candidate: Path) -> float:
            name = candidate.stem.lower()
            score = 60 if name == stem else 0
            if name in {"preview", "cover", "folder", "_preview", "预览", "封面", "thumb", "01", "1", "sample"}:
                score += 70
            if "preview" in name or "cover" in name or "预览" in name:
                score += 40
            return score
    else:
        base = path
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            depth = len(Path(dirpath).relative_to(base).parts)
            if depth > 2:
                dirnames[:] = []
                continue
            for filename in filenames:
                consider(Path(dirpath) / filename)
            if len(candidates) >= 600:
                break

        def prelim(candidate: Path) -> float:
            name = candidate.stem.lower()
            try:
                depth = len(candidate.relative_to(base).parts) - 1
            except ValueError:
                depth = 1
            score = max(0, 30 - depth * 10)
            if name in {"preview", "cover", "folder", "_preview", "预览", "封面", "thumb"}:
                score += 100
            elif name in {"01", "1", "sample"}:
                score += 65
            if "preview" in name or "cover" in name or "预览" in name or "封面" in name:
                score += 55
            if candidate.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                score += 10
            return score

    ranked = sorted(candidates, key=prelim, reverse=True)[:60]
    best = None
    best_score = -1.0
    for candidate in ranked:
        score = prelim(candidate)
        try:
            from PIL import Image
            with Image.open(candidate) as image:
                width, height = image.size
            if width >= 240 and height >= 240:
                score += 20
            if width < 120 or height < 120:
                score -= 20
            score += min(15, (width * height) ** 0.5 / 100)
        except Exception:
            pass
        if score > best_score:
            best_score = score
            best = candidate
    return best


def save_jpeg(source: Path, target: Path, max_px: int) -> bool:
    try:
        from PIL import Image, ImageOps
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", image.size, (255, 255, 255))
                converted = image.convert("RGBA")
                background.paste(converted, mask=converted.split()[-1])
                image = background
            else:
                image = image.convert("RGB")
            image.thumbnail((max_px, max_px), Image.LANCZOS)
            target.parent.mkdir(parents=True, exist_ok=True)
            image.save(target, "JPEG", quality=86, optimize=True)
        return True
    except Exception:
        return False


def make_preview(asset_dir: Path, source: Path | None, cfg: dict) -> Path | None:
    target = asset_dir / "_preview.jpg"
    if target.exists():
        return target
    if not source or not source.exists():
        return None
    if source.resolve() == target.resolve():
        return target
    if save_jpeg(source, target, int(cfg.get("preview_max_px", 900))):
        return target
    if source.suffix.lower() in BROWSER_IMAGES:
        fallback = asset_dir / f"_preview{source.suffix.lower()}"
        try:
            shutil.copy2(source, fallback)
            return fallback
        except OSError:
            return None
    return None


def make_lora_previews(asset_dir: Path, source: Path | None, cfg: dict) -> int:
    if not source:
        return 0
    created = 0
    for model in asset_dir.iterdir():
        if not model.is_file() or model.suffix.lower() not in WEIGHT_EXTS:
            continue
        target = model.with_suffix(".preview.png")
        if target.exists():
            continue
        try:
            from PIL import Image
            with Image.open(source) as image:
                image.thumbnail((512, 512), Image.LANCZOS)
                image.convert("RGB").save(target, "PNG")
            created += 1
        except Exception:
            break
    return created


def preview_from_archive(asset_dir: Path, cfg: dict) -> Path | None:
    target = asset_dir / "_preview.jpg"
    if target.exists():
        return target
    archives = [
        item for item in asset_dir.iterdir()
        if item.is_file() and item.suffix.lower() in ARCHIVE_EXTS
    ][:10]
    for archive in archives:
        if archive.suffix.lower() not in {".zip", ".zipmod", ".var"}:
            continue
        try:
            with zipfile.ZipFile(archive) as bundle:
                images = [
                    name for name in bundle.namelist()
                    if Path(name).suffix.lower() in BROWSER_IMAGES and not name.endswith("/")
                ]
                if not images:
                    continue
                images.sort(key=lambda name: (
                    0 if Path(name).stem.lower() in {"preview", "cover", "_preview", "预览", "封面", "01", "1"} else 1,
                    len(name),
                ))
                for name in images[:5]:
                    data = bundle.read(name)
                    if len(data) > 30_000_000:
                        continue
                    temp = SYSTEM / "thumbs" / f"_tmp_{uuid.uuid4().hex}{Path(name).suffix.lower()}"
                    temp.write_bytes(data)
                    try:
                        if save_jpeg(temp, target, int(cfg.get("preview_max_px", 900))):
                            return target
                    finally:
                        temp.unlink(missing_ok=True)
        except Exception:
            continue
    return None


def build_text(path: Path, meta: dict) -> str:
    context = " ".join(path.parts[-4:])
    return (context + " " + " ".join(meta.get("names", [])) + " " + " ".join(meta.get("archive_names", []))).lower()


def build_strong_text(path: Path, meta: dict) -> str:
    parts = list(path.parts[-4:])
    if path.is_dir():
        try:
            for child in path.iterdir():
                if child.is_dir():
                    parts.append(child.name)
                elif child.suffix.lower() in ASSET_NAME_EXTS:
                    parts.append(child.name)
        except OSError:
            pass
    raw = " ".join(parts)
    raw = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", raw)
    return raw.lower()


def parse_vam_var(path: Path) -> dict | None:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            meta_name = next(
                (name for name in names if name.lower().endswith("meta.json") and name.count("/") <= 1),
                None,
            )
            if not meta_name:
                return None
            data = json.loads(archive.read(meta_name).decode("utf-8", "ignore"))
            package = str(data.get("packageName") or data.get("package") or "").strip()
            creator = str(data.get("creatorName") or data.get("creator") or "").strip()
            contents = data.get("contentList") or []
            if isinstance(contents, dict):
                contents = list(contents.keys())
            if not (package or creator or contents):
                return None
            types = set()
            for item in contents if isinstance(contents, list) else []:
                text = str(item).lower().replace("\\", "/")
                if "saves/scene" in text:
                    types.add("Scenes")
                elif "custom/clothing" in text:
                    types.add("Clothing")
                elif "custom/hair" in text:
                    types.add("Hair")
                elif "morph" in text:
                    types.add("Morphs")
                elif "pose" in text:
                    types.add("Poses")
                elif "animation" in text or text.endswith(".vmd"):
                    types.add("Animations")
                elif "custom/scripts" in text or text.endswith((".cs", ".cslist")):
                    types.add("Plugins")
                elif "custom/assets" in text or text.startswith("assets/"):
                    types.add("Assets")
                elif "textures" in text:
                    types.add("Textures")
                elif "custom/atom/person" in text or "saves/person" in text or "appearance" in text:
                    types.add("Looks")
            return {
                "type": "package",
                "package": re.sub(r"\.var$", "", package, flags=re.I),
                "creator": creator,
                "types": sorted(types),
                "content_count": len(contents) if isinstance(contents, list) else 0,
                "dependencies": data.get("dependencies") or {},
            }
    except Exception:
        return None


def looks_like_vam_scene(path: Path) -> bool:
    if path.suffix.lower() != ".json":
        return False
    try:
        if path.stat().st_size > 50_000_000:
            return False
        text = path.read_text(encoding="utf-8", errors="ignore")[:2_000_000]
        return '"atoms"' in text and ('"storables"' in text or '"scene"' in text)
    except Exception:
        return False


def classify(path: Path, meta: dict, cfg: dict) -> dict:
    text = build_text(path, meta)
    combined = meta["suffixes"].copy()
    for name in meta.get("archive_names", []):
        combined[Path(name).suffix.lower()] += 1
    scores: dict[str, float] = defaultdict(float)
    reasons: dict[str, list[str]] = defaultdict(list)

    def add(category: str, weight: float, reason: str):
        scores[category] += weight
        if reason not in reasons[category]:
            reasons[category].append(reason)

    def has(*keywords: str) -> bool:
        return any(keyword.lower() in text for keyword in keywords)

    def has_ext(*suffixes: str) -> bool:
        return any(combined.get(suffix, 0) for suffix in suffixes)

    def has_word(word: str) -> bool:
        return re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", text) is not None

    tool_code = has_ext(".exe", ".dll", ".py", ".cs", ".sln", ".js") or any(
        name.lower().endswith(("requirements.txt", "package.json", ".sln", "pyproject.toml"))
        for name in meta.get("archive_names", [])
    )
    mod_tool_words = has(
        "3dmigoto", "xxmi", "gimi", "wwmi", "srma", "efmi", "zzmi", "model-importer",
        "model importer", "wwmi-tools", "mcmi", "dbmt", "velo-tools", "tryfixtools",
        "hash-to-slot", "修hash", "mod管理器", "mod工具", "mod loader",
    )
    mmd_tool_words = has(
        "mmd_tools", "mmd tools", "pmxeditor", "pmx editor", "mmd插件", "mmd 插件",
        "dds2png", "inteltextureworks", "openpose-editor", "mmd bridge",
    )
    vrc_tool_words = has("creator companion", "vrchat sdk", "vrc sdk", "vrc工具", "vrchat工具")
    ai_tool_words = has(
        "sd-webui", "stable diffusion", "openpose", "kohya", "lora manager",
        "comfyui manager", "realesrgan", "upscayl", "civitai helper",
    )

    game = detect_games(text, cfg)
    mod_words = (
        has("3dmigoto", "xxmi", "gimi", "wwmi", "srma", "efmi", "zzmi", "mod管理器", "mod工具")
        or has_word("mod")
        or has_word("mods")
        or path.stem.lower().endswith(("mod", "_mod", "-mod"))
    )
    reverse_words = has(
        "逆向", "reverse", "ida", "ghidra", "frida", "il2cpp", "脱壳", "注入", "hook",
        "inject", "解包脚本", "dll劫持", "内存dump",
    )
    tutorial_words = has("教程", "教学", "tutorial", "course", "课程", "讲解", "入门", "训练", "学习", "guide", "介绍")
    tutorial_name = any(word in path.name.lower() for word in ("教程", "教学", "tutorial"))
    vrc_words = has("vrchat", "vrc", "avatar", "booth", "avatar改", "虚拟形象")
    koi_context = has("koikatsu", "恋活", "コイカツ", "kks", "koikatsu sunshine", "[kk]", "illusion")

    if has_ext(".pmx", ".pmd"):
        add("02_MMD/Models", 8, "含 PMX/PMD 模型")
    if has_ext(".vmd"):
        add("02_MMD/Motions", 7, "含 VMD 动作")
        if has_ext(".mp3", ".wav", ".flac", ".ogg", ".m4a"):
            add("02_MMD/Motions", 2, "动作与音频同包")
        if has("镜头", "camera", "カメラ", "运镜"):
            add("02_MMD/Motions", 1, "含镜头")
    if has_ext(".fbx", ".obj", ".gltf", ".glb"):
        if has("解包", "unpack", "rip", "dump", "assetbundle", "原始游戏", "游戏资源"):
            add("04_GameRips", 5, "游戏解包模型")
        elif vrc_words:
            add("03_VRChat/Avatars", 5, "VRChat 模型")
        else:
            add("02_MMD/Models_FBX", 4, "FBX/OBJ 模型")
    if has_ext(".unitypackage", ".vrca", ".vrcw", ".vrm"):
        add("03_VRChat/Avatars", 7, "含 VRChat/Unity 资源")
    if vrc_words and not has_ext(".pmx", ".pmd"):
        add("03_VRChat/Avatars", 4, "名称指向 VRChat")
    if has("衣", "服", "cloth", "outfit", "dress", "bikini", "swimsuit", "costume", "服装"):
        add("03_VRChat/Clothing", 2, "服装特征")
    koi_mod = has_ext(".zipmod") or any(
        name.lower().endswith(".zipmod") for name in meta.get("archive_names", [])
    )
    koi_card = koi_context and has_ext(".png", ".jpg", ".jpeg", ".bmp")
    koi_clothing = has(
        "cloth", "服", "衣", "coordinate", "outfit", "dress", "裙", "袜", "泳装", "bikini"
    )
    koi_scene = has("scene", "场景", "studio", "スタジオ")
    parsed_koi = meta.get("koi") or {}
    koi_type = parsed_koi.get("type")
    if koi_type == "character":
        add("11_Koikatsu/Cards_Characters", 14, "解析为恋活人物卡")
    elif koi_type == "clothes":
        add("11_Koikatsu/Cards_Clothing", 14, "解析为恋活服装卡")
    elif koi_type == "scene":
        add("11_Koikatsu/Cards_Scenes", 14, "解析为恋活场景卡")
    elif koi_type == "zipmod":
        if koi_clothing:
            add("11_Koikatsu/Mods_Clothing", 14, "解析为恋活服装 zipmod")
        else:
            add("11_Koikatsu/Mods", 14, "解析为恋活 zipmod")
    elif koi_type == "pack":
        pack_types = set(parsed_koi.get("card_types") or [])
        if parsed_koi.get("has_mods") and pack_types:
            add("11_Koikatsu/_Packs", 14, "解析为卡片+MOD 混合包")
        elif pack_types == {"character"}:
            add("11_Koikatsu/Cards_Characters", 12, "解析为恋活人物卡包")
        elif pack_types == {"clothes"}:
            add("11_Koikatsu/Cards_Clothing", 12, "解析为恋活服装卡包")
        elif pack_types == {"scene"}:
            add("11_Koikatsu/Cards_Scenes", 12, "解析为恋活场景卡包")
        elif parsed_koi.get("has_mods"):
            add("11_Koikatsu/Mods_Clothing" if koi_clothing else "11_Koikatsu/Mods", 12, "解析为恋活 MOD 包")
        elif pack_types:
            add("11_Koikatsu/Cards", 12, "解析为恋活混合卡片包")
    vam = meta.get("vam") or {}
    vam_suffix = path.suffix.lower()
    vam_path = str(path).lower().replace("\\", "/")
    vam_context = bool(vam) or vam_suffix in VAM_EXTS or has(
        "vam", "virt-a-mate", "virtamate", "addonpackages"
    )
    if vam.get("type") == "package" or (vam_suffix == ".var" and not vam):
        add("12_VAM/Packages", 15, "VAM VAR 包")
    if vam_suffix == ".vap":
        if "/appearance/" in vam_path or "/look/" in vam_path or "/looks/" in vam_path or has("appearance", "look", "外观", "人物预设"):
            add("12_VAM/Looks", 12, "VAM 外观预设")
        elif "/clothing/" in vam_path or "/cloth/" in vam_path or has("cloth", "服", "衣", "outfit"):
            add("12_VAM/Clothing", 12, "VAM 服装预设")
        elif "/hair/" in vam_path or has("hair", "发"):
            add("12_VAM/Hair", 12, "VAM 头发预设")
        elif "/pose/" in vam_path or "/poses/" in vam_path or has("pose", "姿势"):
            add("12_VAM/Poses", 12, "VAM 姿势预设")
        elif "/morph" in vam_path or has("morph", "变形"):
            add("12_VAM/Morphs", 12, "VAM 变形预设")
        elif vam_context:
            add("12_VAM/Presets", 10, "VAM 预设待分")
    if vam_suffix in {".vab", ".vaj", ".vam"} and vam_context:
        if "/hair/" in vam_path or has("hair", "发"):
            add("12_VAM/Hair", 10, "VAM 头发资产")
        elif "/clothing/" in vam_path or "/cloth/" in vam_path or has("cloth", "服", "衣", "outfit"):
            add("12_VAM/Clothing", 10, "VAM 服装资产")
        else:
            add("12_VAM/Assets", 8, "VAM 资产")
    if vam_suffix == ".vac" or (vam_suffix == ".json" and vam.get("type") == "scene"):
        add("12_VAM/Scenes", 12, "VAM 场景")
    if vam_context and vam_suffix in {".cs", ".cslist", ".dll"}:
        add("12_VAM/Plugins", 10, "VAM 插件/脚本")
    if vam_context and vam_suffix == ".vmd":
        add("12_VAM/Animations", 10, "VAM 舞蹈/动画")
    if vam_context and vam_suffix in BROWSER_IMAGES and (
        "/textures/" in vam_path or has("texture", "贴图", "皮肤", "skin")
    ):
        add("12_VAM/Textures", 6, "VAM 贴图")
    if koi_context and koi_mod and meta["suffixes"].get(".zipmod") and meta["suffixes"].get(".png", 0) >= 3:
        add("11_Koikatsu/_Packs", 10, "恋活卡片+MOD 混合包")
    if koi_mod:
        if koi_clothing:
            add("11_Koikatsu/Mods_Clothing", 9, "恋活服装 MOD")
        else:
            add("11_Koikatsu/Mods", 9, "恋活 MOD")
    if koi_card:
        if koi_scene:
            add("11_Koikatsu/Cards_Scenes", 8, "恋活场景卡")
        elif koi_clothing:
            add("11_Koikatsu/Cards_Clothing", 8, "恋活服装卡")
        elif has("chara", "character", "人物", "角色", "人物卡", "角色卡"):
            add("11_Koikatsu/Cards_Characters", 8, "恋活人物卡")
        else:
            add("11_Koikatsu/Cards", 5, "恋活卡片")
    if has_ext(".dll") and koi_context:
        add("11_Koikatsu/Plugins", 8, "恋活插件")
    if has("kkmanager", "materialeditor", "koikatsu manager", "恋活工具") and tool_code:
        add("11_Koikatsu/_Tools", 8, "恋活工具")
    if has_ext(".safetensors", ".ckpt", ".pt", ".pth"):
        lora_meta = any(info.get("ss_network_module") for info in meta.get("safetensors_meta", []))
        if has_word("lora") or "lora" in text or lora_meta:
            add("05_AI_Art/LoRA", 7, "LoRA 权重")
        elif meta["size_bytes"] > 1.5 * GB or has("checkpoint", "底模", "大模型"):
            add("05_AI_Art/Checkpoints", 5, "Checkpoint 权重")
        else:
            add("05_AI_Art/LoRA", 3.5, "safetensors 权重")
    if meta.get("is_workflow"):
        add("05_AI_Art/Workflows", 7, "ComfyUI 工作流 JSON")
    elif has_ext(".json") and has("workflow", "comfyui", "工作流"):
        add("05_AI_Art/Workflows", 3, "工作流文件")
    if has("comfyui", "custom_nodes", "custom nodes") and has_ext(".py", ".js", ".json"):
        add("05_AI_Art/ComfyUI", 4, "ComfyUI 节点/资源")
    if has_ext(".blend"):
        if mod_words and has("mod", "工程", "project"):
            add("01_GameMods/_Projects", 3, "MOD 工程")
        if vrc_words:
            add("03_VRChat/_Projects", 3, "VRChat 工程")
        if has("布料", "cloth", "解算") or has_word("md"):
            add("02_MMD/Cloth_MD", 4, "MD 布料工程")
        if has("cloth", "布料", "丝袜", "裙", "泳装", "衣", "服") and has(
            "工程", "project", "权重", "绑骨", "解算", "对骨"
        ):
            add("02_MMD/Cloth_MD", 6, "布料/衣服工程")
        elif has("衣", "服", "cloth", "丝袜", "裙", "泳装", "袜"):
            add("02_MMD/Cloth_MD", 4, "衣服/布料资源")
        if has("mmd", "pmx", "vmd", "mmd_tools"):
            add("02_MMD/_Projects", 3.5, "MMD Blender 工程")
    if "mmd" in path.name.lower() and has_ext(".blend", ".pmx", ".pmd", ".vmd"):
        add("02_MMD/_Projects", 5, "MMD 工程/备份")
    if has_ext(".psd", ".dds", ".tga", ".png", ".jpg", ".jpeg", ".webp") and has(
        "matcap", "材质", "肌質感", "贴图", "texture", "tex", "id图", "色板", "palette"
    ):
        add("02_MMD/Materials", 4, "MMD 材质/贴图资源")
    if has("参考", "reference", "图片资料") and has_ext(*BROWSER_IMAGES):
        add("02_MMD/References", 3, "MMD 参考图")
    if mod_words:
        add("01_GameMods", 5, "游戏 MOD 特征")
    if mod_tool_words and tool_code:
        add("01_GameMods/_Tools", 8, "MOD 工具/插件")
    if mmd_tool_words and tool_code:
        add("02_MMD/_Tools", 7, "MMD 工具/插件")
    if vrc_tool_words and tool_code:
        add("03_VRChat/_Tools", 7, "VRChat 工具/插件")
    if ai_tool_words and tool_code:
        add("05_AI_Art/Tools", 7, "AI 工具/插件")
    if has("assetstudio", "assetdaemon", "uabe", "assetbundle") and tool_code:
        add("07_Reverse/Tools", 7, "资源解包工具")
    if has_ext(".ini", ".dds") and has("mod", "3dmigoto", "reload"):
        add("01_GameMods", 3, "MOD 配置/贴图")
    if reverse_words:
        add("07_Reverse", 4, "逆向特征")
        if has_ext(".py", ".cs", ".cpp", ".c", ".lua", ".js"):
            add("07_Reverse/Scripts", 3, "逆向脚本")
        if has_ext(".exe", ".dll"):
            add("07_Reverse/Tools", 3, "逆向工具")
        if has_ext(*DOC_EXTS):
            add("07_Reverse/Docs", 3, "逆向资料")
    if tutorial_words:
        if has_ext(*VIDEO_EXTS):
            add("06_Tutorials/Video", 6, "教学视频")
        if has_ext(*DOC_EXTS):
            add("06_Tutorials/Docs", 4, "教学文档")
    elif has_ext(*VIDEO_EXTS):
        add("06_Tutorials/Video", 2, "视频资料")
    if tutorial_name:
        if has_ext(*VIDEO_EXTS):
            add("06_Tutorials/Video", 11, "名称明确为教程视频")
        elif has_ext(*DOC_EXTS) or has_ext(*BROWSER_IMAGES):
            add("06_Tutorials/Docs", 11, "名称明确为教程图文")
    if has("解包", "unpack", "assetbundle", "游戏包体", "pak", "bundle", "dump游戏"):
        add("04_GameRips", 5, "游戏解包资源")
    if has("解包", "unpack", "netease", "denpk", "unnpk") and tool_code and not has_ext(
        ".fbx", ".pmx", ".pmd", ".unitypackage"
    ):
        add("07_Reverse/Tools", 6, "解包工具")
    if has("跑路", "backup", "备份", "archive", "存档"):
        add("08_AuthorBackups", 2, "备份包")
    if "github" in path.name.lower() or (has_ext(".zip", ".7z") and re.search(r"-(main|master)(\s*\(\d+\))?$", path.stem, re.I)):
        add("09_GitHub", 9, "GitHub 仓库快照")
    if any(name.endswith(".git") for name in meta.get("names", [])) or has_ext(".gitignore"):
        add("09_GitHub", 8, "Git 仓库")
    if has("agent", "prompt", "对话", "chat", "会话", "工作内容") and not meta.get("is_workflow"):
        add("10_AI_Work", 2, "AI 工作产物")
    if has_ext(".exe", ".msi") and not reverse_words:
        add("90_Apps", 2, "安装包/可执行文件")

    scores = {key: value for key, value in scores.items() if value > 0}
    if not scores:
        return {
            "category": "00_INBOX", "confidence": 0.0, "needs_review": True,
            "reasons": ["没有足够特征，先放收件箱"], "game": game,
        }

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_category, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    if top_score < 3:
        return {
            "category": "00_INBOX", "confidence": 0.2, "needs_review": True,
            "reasons": reasons[top_category] + ["特征偏弱，先放收件箱"], "game": game,
        }
    ambiguity = top_score - second_score
    confidence = min(0.96, 0.52 + top_score * 0.035 + ambiguity * 0.045)
    needs_review = confidence < 0.62 or ambiguity < 1.0
    return {
        "category": top_category,
        "confidence": round(confidence, 2),
        "needs_review": needs_review,
        "reasons": reasons[top_category],
        "game": game,
        "runner_up": ranked[1][0] if len(ranked) > 1 else "",
    }


def detect_kind(meta: dict) -> str:
    combined = meta["suffixes"].copy()
    for name in meta.get("archive_names", []):
        combined[Path(name).suffix.lower()] += 1
    if combined.get(".fbx") or combined.get(".gltf") or combined.get(".glb") or combined.get(".obj"):
        return "Models_FBX"
    if combined.get(".dds") or any(combined.get(ext) for ext in BROWSER_IMAGES):
        return "Textures"
    if any(combined.get(ext) for ext in ARCHIVE_EXTS):
        return "Packages"
    return "Assets"


def resolve_category(value: str, cfg: dict) -> str | None:
    if not value:
        return None
    categories = cfg["categories"]
    if value in categories:
        return value
    lowered = value.lower()
    for key, info in categories.items():
        if info.get("label", "").lower() == lowered:
            return key
    for key in categories:
        if key.lower().endswith(lowered) or lowered in key.lower():
            return key
    return None


def build_dest(category: str, meta: dict, cfg: dict) -> Path:
    if category == "00_INBOX":
        return ROOT / "00_INBOX" / sanitize(f"{meta['acquired']}_{meta['title']}")
    info = cfg["categories"].get(category)
    if not info:
        raise ValueError(f"未知分类: {category}")
    values = {
        "year": meta["acquired"][:4],
        "month": meta["acquired"][:7],
        "game": meta.get("game") or "其他游戏",
        "group": meta.get("game") or "通用",
        "ip": meta.get("ip") or meta.get("game") or "未分IP",
        "base": meta.get("base") or "Other",
        "kind": meta.get("kind") or "Assets",
        "author": meta.get("author") or "_UnknownAuthor",
        "source": meta.get("source") or "Unknown",
    }
    values["author"] = sanitize(str(values["author"]), 40) or "_UnknownAuthor"
    values["ip"] = sanitize(str(values["ip"]), 40) or "未分IP"
    relative = info["template"].format(**values)
    dated = "{year}" in info["template"] or "{month}" in info["template"]
    name = meta["title"]
    if dated and not re.match(r"^\d{4}-\d{2}-\d{2}", name):
        name = f"{meta['acquired']}_{name}"
    if meta.get("author") and "{author}" not in info["template"] and meta["author"].lower() not in name.lower():
        name = f"{name}_{meta['author']}"
    return ROOT / relative / sanitize(name)


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.name}_{index}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"目标重名过多: {path}")


def check_space(source: Path, destination: Path, size_bytes: int, cfg: dict, copy: bool = False) -> dict:
    same = drive_letter(source) == drive_letter(destination)
    free = free_gb(destination)
    reserve = reserve_gb(destination, cfg)
    needed = size_bytes / GB if (copy or not same) else 0
    after = free - needed
    return {
        "same_volume": same,
        "free_gb": round(free, 2),
        "reserve_gb": reserve,
        "needed_gb": round(needed, 2),
        "after_gb": round(after, 2),
        "ok": after >= reserve,
    }


def analyze_path(path: Path, cfg: dict, explicit_date: str | None = None) -> dict:
    meta = compute_stats(path, cfg, collect_names=True)
    text = build_text(path, meta)
    base = detect_base(text, meta, cfg)

    koi = None
    if koi_tool:
        suffix = path.suffix.lower()
        try:
            if path.is_file():
                if suffix == ".zipmod" or suffix == ".zip":
                    koi = koi_tool.parse_zipmod(path)
                elif suffix == ".png":
                    koi = koi_tool.parse_card(path)
            elif any(word in str(path).lower() for word in ("koikatsu", "恋活", "コイカツ")):
                koi = koi_tool.scan_folder(path)
            elif meta["suffixes"].get(".zipmod"):
                koi = koi_tool.scan_folder(path)
        except Exception:
            koi = None
    if koi:
        meta["koi"] = koi

    vam = None
    if path.is_file():
        suffix = path.suffix.lower()
        try:
            if suffix == ".var" or (suffix == ".zip" and path.stat().st_size > 0):
                vam = parse_vam_var(path)
            elif suffix == ".json" and looks_like_vam_scene(path):
                vam = {"type": "scene", "types": ["Scenes"], "package": path.stem}
            elif suffix in VAM_EXTS:
                vam = {"type": suffix.lstrip("."), "types": [], "package": path.stem}
        except Exception:
            vam = None
    if vam:
        meta["vam"] = vam

    title, author = split_name(path.name)
    if vam:
        if vam.get("creator"):
            author = vam["creator"]
        if vam.get("package"):
            title = vam["package"]
    if not author and koi and koi.get("type") == "zipmod":
        author = koi.get("author", "")
    if not author:
        _, parent_author = split_name(path.parent.name)
        author = parent_author
    if title.isdigit() and path.parent.name:
        title = f"{path.parent.name}_{title}"

    ip_info = detect_ip_info(text, cfg, koi, author, build_strong_text(path, meta))
    ip = ip_info["ip"]
    game = detect_games(text, cfg)
    if not game and ip != "未分IP":
        game = ip
    category_info = classify(path, meta, cfg)
    koi_like = bool(koi) or any(
        word in str(path).lower() for word in ("koikatsu", "恋活", "コイカツ")
    )
    koi_type = (koi or {}).get("type")
    needs_ip = bool(
        ip_info["needs_lookup"]
        and (
            koi_type in {"character", "clothes", "scene"}
            or (koi_type == "pack" and (koi or {}).get("card_types"))
        )
    )
    acquired = detect_date(path, meta, explicit_date)
    if category_info["category"].startswith("11_Koikatsu") and not game:
        game = ip
    meta.update({
        "title": sanitize(title, 90),
        "author": sanitize(author, 40) if author else "",
        "game": game,
        "ip": ip,
        "ip_source": ip_info["source"],
        "ip_candidates": ip_info["candidates"],
        "needs_ip_lookup": needs_ip,
        "koi": koi,
        "vam": vam,
        "base": base,
        "kind": detect_kind(meta),
        "source": detect_source(path),
        "acquired": acquired,
        "category": category_info["category"],
        "confidence": category_info["confidence"],
        "needs_review": category_info["needs_review"],
        "reasons": category_info["reasons"],
        "runner_up": category_info.get("runner_up", ""),
    })
    destination = build_dest(meta["category"], meta, cfg)
    space = check_space(path, destination, meta["size_bytes"], cfg)
    meta["destination"] = str(destination)
    meta["space"] = space
    return meta


def connect_db() -> sqlite3.Connection:
    SYSTEM.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            game TEXT,
            author TEXT,
            source TEXT,
            source_url TEXT,
            acquired TEXT,
            tags TEXT,
            path TEXT NOT NULL UNIQUE,
            preview TEXT,
            size_bytes INTEGER DEFAULT 0,
            file_count INTEGER DEFAULT 0,
            signature TEXT,
            notes TEXT,
            registered TEXT,
            scanned TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_assets_category ON assets(category);
        CREATE INDEX IF NOT EXISTS idx_assets_signature ON assets(signature);
        CREATE TABLE IF NOT EXISTS snapshots (
            ts TEXT NOT NULL,
            category TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            file_count INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS moves (
            ts TEXT NOT NULL,
            src TEXT NOT NULL,
            dst TEXT NOT NULL,
            bytes INTEGER NOT NULL,
            files INTEGER NOT NULL,
            asset_id TEXT
        );
        """
    )
    return connection


def upsert_asset(connection: sqlite3.Connection, data: dict):
    existing = connection.execute("SELECT id FROM assets WHERE path=?", (data["path"],)).fetchone()
    if existing and existing["id"] != data["id"]:
        data["id"] = existing["id"]
    tags = data.get("tags", [])
    if isinstance(tags, str):
        tags = [tag for tag in tags.split(",") if tag]
    values = (
        data["id"], data["title"], data["category"], data.get("game", ""),
        data.get("author", ""), data.get("source", ""), data.get("source_url", ""),
        data.get("acquired", ""), json.dumps(tags, ensure_ascii=False),
        data["path"], data.get("preview", ""), int(data.get("size_bytes", 0)),
        int(data.get("file_count", 0)), data.get("signature", ""),
        data.get("notes", ""), data.get("registered", now_iso()), now_iso(),
    )
    connection.execute(
        """
        INSERT INTO assets (id,title,category,game,author,source,source_url,acquired,tags,path,
                            preview,size_bytes,file_count,signature,notes,registered,scanned)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title, category=excluded.category, game=excluded.game,
            author=excluded.author, source=excluded.source, source_url=excluded.source_url,
            acquired=excluded.acquired, tags=excluded.tags, path=excluded.path,
            preview=excluded.preview, size_bytes=excluded.size_bytes,
            file_count=excluded.file_count, signature=excluded.signature,
            notes=excluded.notes, scanned=excluded.scanned
        """,
        values,
    )


def sidecar_payload(asset_dir: Path, meta: dict, preview: Path | None, asset_id: str, cfg: dict) -> dict:
    preview_rel = ""
    if preview:
        try:
            preview_rel = preview.relative_to(asset_dir).as_posix()
        except ValueError:
            preview_rel = ""
    stats = compute_stats(asset_dir, cfg, collect_names=False)
    return {
        "schema": 1,
        "id": asset_id,
        "title": meta["title"],
        "category": meta["category"],
        "game": meta.get("game", ""),
        "ip": meta.get("ip", ""),
        "ip_source": meta.get("ip_source", ""),
        "ip_candidates": meta.get("ip_candidates", []),
        "needs_ip_lookup": bool(meta.get("needs_ip_lookup")),
        "author": meta.get("author", ""),
        "source": meta.get("source", ""),
        "source_url": meta.get("source_url", ""),
        "acquired": meta["acquired"],
        "tags": meta.get("tags", []),
        "preview": preview_rel,
        "path": str(asset_dir),
        "original_path": str(meta.get("original_path", "")),
        "notes": meta.get("notes", ""),
        "signature": meta.get("signature", ""),
        "size_bytes": stats["size_bytes"],
        "file_count": stats["file_count"],
        "registered": now_iso(),
        "koi": meta.get("koi"),
        "vam": meta.get("vam"),
    }


def write_sidecar(asset_dir: Path, payload: dict):
    (asset_dir / "_asset.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def log_move(source: Path, destination: Path, bytes_moved: int, files: int, asset_id: str):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    new_file = not LOG_PATH.exists()
    with open(LOG_PATH, "a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(["time", "source", "destination", "bytes", "files", "asset_id"])
        writer.writerow([now_iso(), str(source), str(destination), bytes_moved, files, asset_id])


def move_verified(source: Path, destination: Path, cfg: dict, expected: dict | None = None) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(str(destination))
    expected = expected or compute_stats(source, cfg)
    same = drive_letter(source) == drive_letter(destination)
    if same:
        os.rename(source, destination)
    else:
        temp = destination.with_name(destination.name + f".__moving_{uuid.uuid4().hex[:6]}")
        try:
            if source.is_dir():
                shutil.copytree(source, temp)
            else:
                shutil.copy2(source, temp)
            copied = compute_stats(temp, cfg)
            if copied["file_count"] != expected["file_count"] or copied["size_bytes"] != expected["size_bytes"]:
                raise RuntimeError("跨盘复制校验失败，源文件未删除")
            os.rename(temp, destination)
            if source.is_dir():
                shutil.rmtree(source)
            else:
                source.unlink()
        finally:
            if temp.exists():
                shutil.rmtree(temp, ignore_errors=True)
    actual = compute_stats(destination, cfg)
    if actual["file_count"] != expected["file_count"] or actual["size_bytes"] != expected["size_bytes"]:
        raise RuntimeError(f"移动后校验失败: {source} -> {destination}")
    return actual


def copy_verified(source: Path, destination: Path, cfg: dict, expected: dict | None = None) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(str(destination))
    expected = expected or compute_stats(source, cfg)
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination / source.name)
    actual = compute_stats(destination, cfg)
    if actual["file_count"] != expected["file_count"] or actual["size_bytes"] != expected["size_bytes"]:
        raise RuntimeError(f"复制后校验失败: {source} -> {destination}")
    return actual


def cmd_init(args, cfg: dict):
    dirs = list(cfg.get("init_dirs", []))
    for game in cfg.get("games", []):
        dirs.append(f"01_GameMods/{game['name']}")
        dirs.append(f"01_GameMods/{game['name']}/_Projects")
    for relative in dirs:
        (ROOT / relative).mkdir(parents=True, exist_ok=True)
    (SYSTEM / "logs").mkdir(parents=True, exist_ok=True)
    (SYSTEM / "thumbs").mkdir(parents=True, exist_ok=True)
    (SYSTEM / "backups").mkdir(parents=True, exist_ok=True)
    connection = connect_db()
    connection.close()
    rebuild_dashboard(cfg)
    print(f"资源库已初始化: {ROOT}")
    print(f"总表: {INDEX_PATH}")
    print(f"Excel: {XLSX_PATH}")


def format_ip_candidates(candidates: list[dict] | None, limit: int = 5) -> str:
    parts = []
    for item in (candidates or [])[:limit]:
        if item.get("options"):
            parts.append(f"{item.get('term')} -> {'/'.join(item['options'])}")
        else:
            parts.append(f"{item.get('ip')}({item.get('term')})")
    return " / ".join(parts)


def cmd_analyze(args, cfg: dict):
    path = Path(args.path).expanduser().resolve()
    if not path.exists():
        sys.exit(f"路径不存在: {path}")
    info = analyze_path(path, cfg, args.date)
    info["path"] = str(path)
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2, default=str))
        return
    category_label = cfg["categories"].get(info["category"], {}).get("label", info["category"])
    print(f"路径      {path}")
    print(f"体积      {human(info['size_bytes'])} / {info['file_count']} 个文件")
    print(f"分类      {info['category']}  {category_label}  置信度 {info['confidence']:.2f}"
          + ("  [需要确认]" if info["needs_review"] else ""))
    print(f"理由      {'；'.join(info['reasons'])}")
    if info.get("runner_up"):
        print(f"次选      {info['runner_up']}")
    print(f"游戏      {info.get('game') or '-'}")
    print(f"作者      {info.get('author') or '-'}")
    if info.get("ip") and (info["category"].startswith("11_Koikatsu") or info.get("needs_ip_lookup")):
        print(f"IP        {info['ip']}  (来源 {info.get('ip_source')})")
    if info.get("needs_ip_lookup"):
        candidates = format_ip_candidates(info.get("ip_candidates"))
        print(f"IP待确认  {'候选: ' + candidates if candidates else '需要联网/人工确认'}")
    if info.get("koi"):
        koi_info = info["koi"]
        required = len(koi_info.get("required") or koi_info.get("guids") or [])
        print(f"恋活解析  {koi_info.get('type')}  依赖 {required} 个 GUID")
    if info.get("vam"):
        vam_info = info["vam"]
        print(f"VAM解析   {vam_info.get('package', '')}  类型: {', '.join(vam_info.get('types') or []) or '未识别'}")
    print(f"日期      {info['acquired']}")
    if info["category"].startswith("05_AI_Art/LoRA"):
        print(f"底模      {info.get('base')}")
    print(f"目标      {info['destination']}")
    space = info["space"]
    print(f"空间      {drive_letter(info['destination'])} 剩余 {space['free_gb']:.2f} GB，"
          f"安全水位 {space['reserve_gb']:.0f} GB，移动后 {space['after_gb']:.2f} GB -> "
          f"{'可以' if space['ok'] else '空间不足'}")


def cmd_ingest(args, cfg: dict):
    register_mode = bool(getattr(args, "register", False))
    source = Path(args.path).expanduser().resolve()
    if not source.exists():
        sys.exit(f"路径不存在: {source}")
    if register_mode and source.is_file():
        sys.exit("register 只支持文件夹；单个文件请用 ingest。")
    if is_inside(source, ROOT) and not register_mode:
        sys.exit("源路径已在资源库内。若要重新登记请用 register 或 scan。")
    info = analyze_path(source, cfg, getattr(args, "date", None))
    category_arg = getattr(args, "category", None)
    category = resolve_category(category_arg, cfg) if category_arg else info["category"]
    if not category:
        sys.exit(f"无法识别的分类: {category_arg}")
    if getattr(args, "project", False):
        if category.startswith("01_GameMods"):
            category = "01_GameMods/_Projects"
        elif category.startswith("02_MMD"):
            category = "02_MMD/_Projects"
        elif category.startswith("03_VRChat"):
            category = "03_VRChat/_Projects"
    info["category"] = category
    info["title"] = sanitize(args.title, 90) if getattr(args, "title", None) else info["title"]
    info["author"] = sanitize(args.author, 40) if getattr(args, "author", None) else info["author"]
    info["game"] = getattr(args, "game", None) or info.get("game") or ""
    info["ip"] = getattr(args, "ip", None) or info.get("ip") or "未分IP"
    if getattr(args, "ip", None):
        info["ip_source"] = "manual"
        info["needs_ip_lookup"] = False
    info["base"] = getattr(args, "base", None) or info.get("base") or "Other"
    info["kind"] = getattr(args, "kind", None) or info.get("kind") or "Assets"
    info["source"] = getattr(args, "source", None) or info.get("source") or ""
    info["source_url"] = getattr(args, "source_url", "") or ""
    info["tags"] = [tag.strip() for tag in (getattr(args, "tags", "") or "").split(",") if tag.strip()]
    info["notes"] = getattr(args, "notes", "") or ""
    info["original_path"] = str(source)
    if register_mode:
        destination = source
    else:
        destination = unique_path(build_dest(category, info, cfg))

    if category_arg is None and info["needs_review"] and not getattr(args, "force", False):
        print(f"需要确认：{info['title']} -> {category} (置信度 {info['confidence']:.2f})")
        print(f"理由：{'；'.join(info['reasons'])}")
        print("确认后加 --force，或直接用 --category 指定分类。")
        sys.exit(2)

    if info.get("needs_ip_lookup") and not getattr(args, "ip", None):
        print(f"IP 不确定：{info['title']}")
        candidates = format_ip_candidates(info.get("ip_candidates"))
        print(f"候选：{candidates or '无本地映射'}")
        print("请先 --ip 指定，或联网确认后用 ip-map-add 写入映射；确认放未分IP可加 --ip 未分IP。")
        sys.exit(2)

    if not register_mode:
        space = check_space(source, destination, info["size_bytes"], cfg, copy=getattr(args, "copy", False))
        if not space["ok"]:
            print(f"空间不足：{drive_letter(destination)} 剩余 {space['free_gb']:.2f} GB，"
                  f"移动后 {space['after_gb']:.2f} GB，低于安全水位 {space['reserve_gb']:.0f} GB。")
            sys.exit(3)
        top = category.split("/")[0]
        quota = cfg.get("quotas_gb", {}).get(top)
        if quota:
            connection = connect_db()
            current = connection.execute(
                "SELECT COALESCE(SUM(size_bytes),0) FROM assets WHERE category LIKE ?",
                (top + "%",),
            ).fetchone()[0]
            connection.close()
            if (current + info["size_bytes"]) / GB >= quota * 0.9:
                print(f"提醒：{category_label(top, cfg)} 将占用 "
                      f"{(current + info['size_bytes']) / GB:.1f} GB，接近或超过配额 {quota} GB。")
    else:
        space = {"same_volume": True, "free_gb": round(free_gb(destination), 2),
                 "reserve_gb": reserve_gb(destination, cfg), "needed_gb": 0,
                 "after_gb": round(free_gb(destination), 2), "ok": True}

    print(f"{'登记' if register_mode else '目标'}  {destination}")
    print(f"体积      {human(info['size_bytes'])} / {info['file_count']} 个文件")
    print(f"分类      {category}  置信度 {info['confidence']:.2f}")
    if category.startswith("11_Koikatsu"):
        print(f"IP        {info.get('ip')}  (来源 {info.get('ip_source')})")
    print(f"空间      {space['free_gb']:.2f} GB 可用 -> 移动后 {space['after_gb']:.2f} GB")
    if not getattr(args, "apply", False):
        print("这是预演，未移动任何文件。确认无误后加 --apply。")
        return

    if register_mode:
        preview_source = find_preview(source)
        preview = make_preview(source, preview_source, cfg) or preview_from_archive(source, cfg)
        if not preview_source:
            preview_source = preview
        if category.startswith("05_AI_Art/LoRA"):
            make_lora_previews(source, preview_source, cfg)
        asset_id = str(uuid.uuid4())
        payload = sidecar_payload(source, info, preview, asset_id, cfg)
        write_sidecar(source, payload)
        connection = connect_db()
        upsert_asset(connection, payload)
        connection.execute(
            "INSERT INTO moves(ts,src,dst,bytes,files,asset_id) VALUES(?,?,?,?,?,?)",
            (now_iso(), str(source), str(source), info["size_bytes"], info["file_count"], asset_id),
        )
        connection.commit()
        connection.close()
        log_move(source, source, info["size_bytes"], info["file_count"], asset_id)
    else:
        expected = {"file_count": info["file_count"], "size_bytes": info["size_bytes"]}
        copy_mode = bool(getattr(args, "copy", False))
        if source.is_file():
            if copy_mode:
                copy_verified(source, destination, cfg, expected)
            else:
                destination.mkdir(parents=True, exist_ok=True)
                final_file = destination / source.name
                move_verified(source, final_file, cfg, expected)
            asset_dir = destination
        else:
            if copy_mode:
                copy_verified(source, destination, cfg, expected)
            else:
                move_verified(source, destination, cfg, expected)
            asset_dir = destination
        preview_source = find_preview(asset_dir)
        preview = make_preview(asset_dir, preview_source, cfg) or preview_from_archive(asset_dir, cfg)
        if not preview_source:
            preview_source = preview
        if category.startswith("05_AI_Art/LoRA"):
            make_lora_previews(asset_dir, preview_source, cfg)
        asset_id = str(uuid.uuid4())
        payload = sidecar_payload(asset_dir, info, preview, asset_id, cfg)
        write_sidecar(asset_dir, payload)
        connection = connect_db()
        upsert_asset(connection, payload)
        connection.execute(
            "INSERT INTO moves(ts,src,dst,bytes,files,asset_id) VALUES(?,?,?,?,?,?)",
            (now_iso(), str(source), str(asset_dir), info["size_bytes"], info["file_count"], asset_id),
        )
        connection.commit()
        connection.close()
        log_move(source, asset_dir, info["size_bytes"], info["file_count"], asset_id)

    print(f"预览      {'已生成 ' + preview.name if preview else '未找到可用图片'}")
    rebuild_dashboard(cfg)
    print(f"已登记    {asset_id}")
    print(f"总表      {INDEX_PATH}")
    print(f"Excel     {XLSX_PATH}")


def upsert_from_sidecar(connection: sqlite3.Connection, sidecar: Path, cfg: dict) -> str | None:
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception:
        return None
    asset_dir = sidecar.parent
    data["path"] = str(asset_dir)
    data.setdefault("id", str(uuid.uuid4()))
    data.setdefault("title", asset_dir.name)
    data.setdefault("category", "00_INBOX")
    data.setdefault("acquired", date.today().isoformat())
    preview_name = data.get("preview", "")
    preview_path = asset_dir / preview_name if preview_name else None
    if not preview_path or not preview_path.exists():
        existing = asset_dir / "_preview.jpg"
        data["preview"] = "_preview.jpg" if existing.exists() else ""
    stats = compute_stats(asset_dir, cfg, collect_names=False)
    data["size_bytes"] = stats["size_bytes"]
    data["file_count"] = stats["file_count"]
    if not data.get("signature"):
        data["signature"] = stats["signature"]
    upsert_asset(connection, data)
    return data["id"]


def cmd_scan(args, cfg: dict):
    connection = connect_db()
    skip = set(cfg.get("skip_scan_dirs", []))
    seen: set[str] = set()
    count = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in skip]
        if "_asset.json" not in filenames:
            continue
        asset_id = upsert_from_sidecar(connection, Path(dirpath) / "_asset.json", cfg)
        if asset_id:
            seen.add(asset_id)
            count += 1
    if not args.keep_missing:
        for row in connection.execute("SELECT id FROM assets").fetchall():
            if row["id"] not in seen:
                connection.execute("DELETE FROM assets WHERE id=?", (row["id"],))
    stamp = now_iso()
    by_category: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in connection.execute("SELECT category, size_bytes, file_count FROM assets"):
        top = row["category"].split("/")[0]
        by_category[top][0] += row["size_bytes"] or 0
        by_category[top][1] += row["file_count"] or 0
    for category, (size, files) in by_category.items():
        connection.execute(
            "INSERT INTO snapshots(ts,category,size_bytes,file_count) VALUES(?,?,?,?)",
            (stamp, category, size, files),
        )
    connection.commit()
    connection.close()
    print(f"已扫描 {count} 个资源")
    if not args.no_dashboard:
        rebuild_dashboard(cfg)


def load_assets(connection: sqlite3.Connection) -> list[dict]:
    rows = connection.execute("SELECT * FROM assets ORDER BY acquired DESC, title").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["tags"] = json.loads(item.get("tags") or "[]")
        except Exception:
            item["tags"] = []
        result.append(item)
    return result


def category_label(key: str, cfg: dict) -> str:
    if "/" not in key:
        return cfg.get("top_labels", {}).get(key, cfg["categories"].get(key, {}).get("label", key))
    return cfg["categories"].get(key, {}).get("label", key.split("/")[-1])


def rebuild_xlsx(cfg: dict, assets: list[dict], free: float, reserve: float, last_scan: str):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except Exception:
        return

    link_font = Font(color="0563C1", underline="single")
    header_fill = PatternFill("solid", fgColor="0F766E")
    header_font = Font(color="FFFFFF", bold=True)
    title_font = Font(size=18, bold=True, color="0F766E")
    dim_font = Font(size=10, color="6B7785")

    def style_header(sheet, row: int, columns: int):
        for column in range(1, columns + 1):
            cell = sheet.cell(row=row, column=column)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(vertical="center")
        sheet.row_dimensions[row].height = 22

    def link(cell, target: Path | str, text: str | None = None):
        cell.value = text if text is not None else str(target)
        cell.hyperlink = str(target)
        cell.font = link_font

    wb = Workbook()
    nav = wb.active
    nav.title = "大类导航"
    nav.sheet_view.showGridLines = False
    nav.merge_cells("A1:E1")
    nav["A1"] = "资源总表 · 大类导航"
    nav["A1"].font = title_font
    nav.merge_cells("A2:E2")
    nav["A2"] = (
        f"最后扫描 {last_scan} · {drive_letter(ROOT)} 盘可用 {free:.2f} GB · "
        f"安全水位 {reserve:.0f} GB · 点击蓝色文字直接打开文件夹"
    )
    nav["A2"].font = dim_font
    headers = ["大类", "资源数", "占用", "打开文件夹", "路径"]
    for column, text in enumerate(headers, 1):
        nav.cell(row=4, column=column, value=text)
    style_header(nav, 4, len(headers))

    counts = {top: 0 for top in cfg.get("top_categories", [])}
    sizes = {top: 0 for top in cfg.get("top_categories", [])}
    for item in assets:
        top = item["category"].split("/")[0]
        if top in counts:
            counts[top] += 1
            sizes[top] += item.get("size_bytes") or 0

    row = 5
    for top in cfg.get("top_categories", []):
        path = ROOT / top
        label = category_label(top, cfg)
        link(nav.cell(row=row, column=1), path, label)
        nav.cell(row=row, column=2, value=counts[top])
        size_cell = nav.cell(row=row, column=3, value=round(sizes[top] / GB, 3))
        size_cell.number_format = "0.000"
        link(nav.cell(row=row, column=4), path, "打开文件夹")
        nav.cell(row=row, column=5, value=str(path)).font = dim_font
        row += 1

    inbox = ROOT / "00_INBOX"
    inbox_count = sum(1 for _ in inbox.iterdir()) if inbox.exists() else 0
    link(nav.cell(row=row, column=1), inbox, "收件箱")
    nav.cell(row=row, column=2, value=inbox_count)
    nav.cell(row=row, column=3, value=0).number_format = "0.000"
    link(nav.cell(row=row, column=4), inbox, "打开文件夹")
    nav.cell(row=row, column=5, value=str(inbox)).font = dim_font

    for column, width in zip("ABCDE", (26, 10, 12, 14, 62)):
        nav.column_dimensions[column].width = width
    nav.freeze_panes = "A5"

    sheet = wb.create_sheet("资源清单")
    sheet.sheet_view.showGridLines = False
    headers = ["日期", "大类", "分类", "名称", "作者", "游戏", "来源", "标签", "体积GB", "打开文件夹", "预览图", "路径"]
    for column, text in enumerate(headers, 1):
        sheet.cell(row=1, column=column, value=text)
    style_header(sheet, 1, len(headers))

    row = 2
    for item in assets:
        path = Path(item["path"])
        preview = path / item["preview"] if item.get("preview") else None
        sheet.cell(row=row, column=1, value=item.get("acquired") or "")
        sheet.cell(row=row, column=2, value=category_label(item["category"].split("/")[0], cfg))
        sheet.cell(row=row, column=3, value=category_label(item["category"], cfg))
        link(sheet.cell(row=row, column=4), path, item["title"])
        sheet.cell(row=row, column=5, value=item.get("author") or "")
        sheet.cell(row=row, column=6, value=item.get("game") or "")
        sheet.cell(row=row, column=7, value=item.get("source") or "")
        sheet.cell(row=row, column=8, value=" / ".join(item.get("tags") or []))
        size_cell = sheet.cell(row=row, column=9, value=round((item.get("size_bytes") or 0) / GB, 3))
        size_cell.number_format = "0.000"
        link(sheet.cell(row=row, column=10), path, "打开")
        if preview and preview.exists():
            link(sheet.cell(row=row, column=11), preview, "查看")
        sheet.cell(row=row, column=12, value=str(path)).font = dim_font
        row += 1

    sheet.auto_filter.ref = f"A1:L{max(1, row - 1)}"
    sheet.freeze_panes = "A2"
    for column, width in zip("ABCDEFGHIJKL", (12, 12, 18, 38, 14, 16, 10, 24, 10, 12, 10, 70)):
        sheet.column_dimensions[column].width = width

    guide = wb.create_sheet("使用说明")
    guide.sheet_view.showGridLines = False
    guide["A1"] = "资源库使用说明"
    guide["A1"].font = title_font
    lines = [
        "1. 大类导航页点击蓝色文字可直接打开对应文件夹。",
        "2. 资源清单页支持筛选、排序；名称和“打开”列可直接打开资源文件夹。",
        "3. 新资源先丢进 D:\\ASSETS\\00_INBOX，然后让 AI 执行“归类”。",
        "4. 每个资源文件夹内的 _asset.json 是元数据；_preview.jpg 是总表预览图。",
        "5. 移动资源请用 assets.py ingest，不要手工拖拽，否则总表不会更新。",
        "6. 空间低于安全水位时，ingest 会拒绝移动，先清理 99_ARCHIVE 或重复项。",
        "7. 重复资源只报告，不自动删除；确认后用 dupes 报告处理。",
        "",
        "常用命令：",
        f'python "{SYSTEM / "assets.py"}" analyze "<路径>"',
        f'python "{SYSTEM / "assets.py"}" ingest "<路径>" --apply',
        f'python "{SYSTEM / "assets.py"}" scan',
        f'python "{SYSTEM / "assets.py"}" space',
        f'python "{SYSTEM / "assets.py"}" dupes',
    ]
    for index, text in enumerate(lines, 3):
        guide.cell(row=index, column=1, value=text)
    guide.column_dimensions["A"].width = 110

    temp = XLSX_PATH.with_name(XLSX_PATH.name + ".tmp")
    try:
        wb.save(temp)
        os.replace(temp, XLSX_PATH)
    except Exception as exc:
        temp.unlink(missing_ok=True)
        print(f"警告: 资源总表.xlsx 更新失败（可能正被 Excel 占用）: {exc}")


def rebuild_dashboard(cfg: dict):
    connection = connect_db()
    assets = load_assets(connection)
    dupes = connection.execute(
        """
        SELECT signature, COUNT(*) c, SUM(size_bytes) total, MAX(size_bytes) keep
        FROM assets WHERE signature <> '' GROUP BY signature HAVING c > 1
        """
    ).fetchall()
    reclaim = sum((row["total"] or 0) - (row["keep"] or 0) for row in dupes)
    last_scan_row = connection.execute("SELECT MAX(scanned) AS ts FROM assets").fetchone()
    last_scan = last_scan_row["ts"] if last_scan_row and last_scan_row["ts"] else "尚未扫描"
    connection.close()

    top_categories = cfg.get("top_categories", [])
    counts = {top: 0 for top in top_categories}
    sizes = {top: 0 for top in top_categories}
    for item in assets:
        top = item["category"].split("/")[0]
        if top in counts:
            counts[top] += 1
            sizes[top] += item.get("size_bytes") or 0
    total_size = sum(item.get("size_bytes") or 0 for item in assets)
    max_size = max(sizes.values()) if sizes else 1
    drive = drive_letter(ROOT)
    free = free_gb(ROOT)
    reserve = reserve_gb(ROOT, cfg)
    inbox_dir = ROOT / "00_INBOX"
    inbox_count = sum(1 for _ in inbox_dir.iterdir()) if inbox_dir.exists() else 0

    cards = []
    for top in top_categories:
        label = category_label(top, cfg)
        percent = (sizes[top] / max_size * 100) if max_size else 0
        top_path = (ROOT / top).resolve()
        cards.append(
            f'<a class="card" href="#" data-copy="{html.escape(str(top_path))}">'
            f'<div class="card-top"><span class="card-label">{html.escape(label)}</span>'
            f'<span class="card-count">{counts[top]} 项</span></div>'
            f'<div class="card-size">{human(sizes[top])}</div>'
            f'<div class="bar"><i style="width:{percent:.1f}%"></i></div>'
            f'<div class="card-path">{html.escape(top)}</div></a>'
        )

    labels = {key: info.get("label", key) for key, info in cfg["categories"].items()}
    tops = {top: category_label(top, cfg) for top in top_categories}
    payload_assets = []
    for item in assets:
        folder = Path(item["path"])
        preview_name = item.get("preview") or ""
        preview_path = folder / preview_name if preview_name else None
        try:
            relative = folder.relative_to(ROOT).as_posix()
        except ValueError:
            relative = str(folder)
        payload_assets.append({
            "title": item["title"],
            "author": item.get("author") or "",
            "category": item["category"],
            "category_label": labels.get(item["category"], item["category"]),
            "top": item["category"].split("/")[0],
            "top_label": tops.get(item["category"].split("/")[0], ""),
            "game": item.get("game") or "",
            "source": item.get("source") or "",
            "acquired": item.get("acquired") or "",
            "size": item.get("size_bytes") or 0,
            "size_h": human(item.get("size_bytes") or 0),
            "tags": item.get("tags") or [],
            "rel_path": relative,
            "folder_path": str(folder.resolve()),
            "folder_uri": folder.resolve().as_uri(),
            "preview_uri": preview_path.resolve().as_uri() if preview_path and preview_path.exists() else "",
        })
    payload_cats = [{"key": top, "label": tops[top]} for top in top_categories]
    payload_labels = labels
    data_json = json.dumps(payload_assets, ensure_ascii=False).replace("</", "<\\/")
    cats_json = json.dumps(payload_cats, ensure_ascii=False)
    labels_json = json.dumps(payload_labels, ensure_ascii=False)

    warning = ""
    if free < reserve:
        warning = (
            f'<div class="warning">D 盘可用空间 {free:.2f} GB 已低于安全水位 {reserve:.0f} GB，'
            f'新资源入库会被拒绝，请先清理 99_ARCHIVE 或重复资源。</div>'
        )

    template = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>资源总表</title>
<style>
:root{--bg:#f4f6f8;--panel:#ffffff;--ink:#1f2933;--dim:#6b7785;--line:#e2e8f0;--accent:#0f766e;--accent-soft:#ccfbf1;--warn:#b91c1c;--warn-bg:#fef2f2}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 "Segoe UI","Microsoft YaHei",system-ui,sans-serif}
header{display:flex;justify-content:space-between;gap:20px;align-items:flex-end;padding:26px 30px 16px;background:linear-gradient(135deg,#0f766e,#134e4a);color:#f8fafc}
h1{margin:0;font-size:26px;letter-spacing:.5px}
.sub{margin:6px 0 0;color:#ccfbf1;font-size:13px}
.actions{display:flex;gap:8px;flex-wrap:wrap}
.btn{display:inline-block;padding:8px 13px;border-radius:7px;background:rgba(255,255,255,.14);color:#fff;text-decoration:none;border:1px solid rgba(255,255,255,.25)}
.btn:hover{background:rgba(255,255,255,.23)}
main{padding:20px 30px 40px;max-width:1500px;margin:0 auto}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:18px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.stat b{display:block;font-size:25px;line-height:1.2}
.stat span{color:var(--dim);font-size:12px}
.warning{background:var(--warn-bg);color:var(--warn);border:1px solid #fecaca;border-radius:9px;padding:12px 14px;margin-bottom:16px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-bottom:22px}
.card{display:block;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px;text-decoration:none;color:inherit;transition:transform .12s,box-shadow .12s}
.card:hover{transform:translateY(-2px);box-shadow:0 6px 18px rgba(15,23,42,.08);border-color:#99f6e4}
.card-top{display:flex;justify-content:space-between;gap:6px;align-items:center}
.card-label{font-weight:650;font-size:15px}
.card-count{color:var(--dim);font-size:12px}
.card-size{font-size:20px;margin:5px 0 8px;color:var(--accent);font-weight:600}
.bar{height:4px;background:#edf2f7;border-radius:99px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--accent);border-radius:99px}
.card-path{color:#94a3b8;font-size:11px;margin-top:7px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:12px}
.note{background:#fffbeb;border:1px solid #fde68a;color:#92400e;border-radius:9px;padding:10px 14px;margin:0 0 12px;font-size:12px}
input,select{border:1px solid var(--line);border-radius:7px;padding:8px 10px;font:inherit;color:inherit;background:#fff}
input{flex:1;min-width:220px}
input:focus,select:focus{outline:2px solid var(--accent-soft);border-color:var(--accent)}
#shown{color:var(--dim);font-size:12px;margin-left:auto}
.table-wrap{background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:auto}
table{border-collapse:collapse;width:100%;min-width:980px}
th,td{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}
th{position:sticky;top:0;background:#f8fafc;z-index:1;font-size:12px;color:#475569;font-weight:600}
tr:last-child td{border-bottom:0}
tbody tr:hover{background:#f8fffe}
.thumb{width:74px}
.thumb img,.ph{width:64px;height:64px;border-radius:7px;object-fit:cover;background:#e2e8f0;display:block}
.ph{display:flex;align-items:center;justify-content:center;color:#64748b;font-size:12px;background:linear-gradient(135deg,#e2e8f0,#f1f5f9)}
.name{font-weight:600;line-height:1.35;max-width:390px}
.dim{color:var(--dim);font-size:12px}
.tag{display:inline-block;padding:2px 8px;border-radius:99px;background:var(--accent-soft);color:#115e59;font-size:12px;white-space:nowrap}
.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.open{display:inline-block;padding:5px 10px;border-radius:6px;background:#0f766e;color:#fff;text-decoration:none;font-size:12px;white-space:nowrap}
.open:hover{background:#115e59}
.toast{position:fixed;left:50%;bottom:28px;transform:translateX(-50%) translateY(20px);background:#0f172a;color:#fff;padding:10px 16px;border-radius:8px;font-size:13px;opacity:0;pointer-events:none;transition:.2s;z-index:99;max-width:80vw;word-break:break-all}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
footer{padding:18px 30px 30px;color:#94a3b8;font-size:12px;text-align:center}
@media (max-width:700px){header{padding:20px 16px 14px;flex-direction:column;align-items:flex-start}main{padding:14px 14px 30px}.name{max-width:220px}}
</style>
</head>
<body>
<header>
  <div><h1>资源总表</h1><p class="sub">最后扫描 __LAST_SCAN__ · 点击卡片或“打开文件夹”复制路径；Excel 总表可单击直达</p></div>
  <div class="actions"><a class="btn" href="#" data-copy="__INBOX_PATH__">复制收件箱路径 (__INBOX_COUNT__)</a><a class="btn" href="#" data-copy="__ROOT_PATH__">复制资源库路径</a></div>
</header>
<main>
  __WARNING__
  <section class="stats">
    <div class="stat"><b>__TOTAL_ASSETS__</b><span>已登记资源</span></div>
    <div class="stat"><b>__TOTAL_SIZE__</b><span>资源总占用</span></div>
    <div class="stat"><b>__FREE_GB__ GB</b><span>__DRIVE__ 盘可用 · 安全水位 __RESERVE_GB__ GB</span></div>
    <div class="stat"><b>__RECLAIM__</b><span>重复资源可回收</span></div>
  </section>
  <section class="cards">__CARDS__</section>
  <section class="toolbar">
    <input id="q" type="search" placeholder="搜索名称、作者、游戏、来源、标签、路径…">
    <select id="cat"><option value="">全部分类</option></select>
    <select id="sort">
      <option value="date_desc">日期：新到旧</option>
      <option value="date_asc">日期：旧到新</option>
      <option value="size_desc">体积：大到小</option>
      <option value="size_asc">体积：小到大</option>
      <option value="name_asc">名称：A-Z</option>
    </select>
    <span id="shown"></span>
  </section>
  <div class="note">浏览器不能直接唤起资源管理器：点击卡片或“打开文件夹”会复制路径（Win+E 粘贴）。要单击直达文件夹，请打开同目录的 <b>资源总表.xlsx</b>。</div>
  <section class="table-wrap">
    <table>
      <thead><tr><th>预览</th><th>名称 / 作者</th><th>分类</th><th>日期</th><th class="num">体积</th><th>来源 / 标签</th><th>操作</th></tr></thead>
      <tbody id="rows"></tbody>
    </table>
  </section>
</main>
<footer>资源库 __ROOT__ · 由 assets.py 生成</footer>
<script>
const ASSETS = __ASSETS_JSON__;
const CATS = __CATS_JSON__;
const LABELS = __LABELS_JSON__;
const $ = id => document.getElementById(id);
function esc(value){return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function render(){
  const q = $("q").value.trim().toLowerCase();
  const cat = $("cat").value;
  const sort = $("sort").value;
  let rows = ASSETS.filter(a => {
    if(cat && a.top !== cat) return false;
    if(!q) return true;
    const hay = [a.title,a.author,a.game,a.source,a.category_label,a.rel_path,(a.tags||[]).join(" ")].join(" ").toLowerCase();
    return hay.includes(q);
  });
  rows.sort((a,b) => {
    if(sort === "date_asc") return (a.acquired||"").localeCompare(b.acquired||"") || a.title.localeCompare(b.title);
    if(sort === "size_desc") return (b.size||0)-(a.size||0);
    if(sort === "size_asc") return (a.size||0)-(b.size||0);
    if(sort === "name_asc") return a.title.localeCompare(b.title, "zh-Hans-CN");
    return (b.acquired||"").localeCompare(a.acquired||"") || a.title.localeCompare(b.title);
  });
  $("shown").textContent = `显示 ${rows.length} / ${ASSETS.length} 项`;
  $("rows").innerHTML = rows.map(a => `<tr>
    <td class="thumb">${a.preview_uri ? `<img loading="lazy" src="${a.preview_uri}" alt="">` : `<div class="ph">${esc((a.top_label||"?").slice(0,2))}</div>`}</td>
    <td><div class="name">${esc(a.title)}</div><div class="dim">${esc(a.author || "未知作者")}${a.game ? " · " + esc(a.game) : ""}</div></td>
    <td><span class="tag">${esc(a.category_label)}</span></td>
    <td>${esc(a.acquired || "")}</td>
    <td class="num">${esc(a.size_h)}</td>
    <td><div class="dim">${esc(a.source || "")}</div><div class="dim">${esc((a.tags||[]).join(" / "))}</div></td>
    <td><a class="open" href="#" data-copy="${esc(a.folder_path)}">打开文件夹</a></td>
  </tr>`).join("");
}
CATS.forEach(c => { const option = document.createElement("option"); option.value = c.key; option.textContent = c.label; $("cat").appendChild(option); });
function toast(message){
  const el = $("toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}
function fallbackCopy(text, done){
  const area = document.createElement("textarea");
  area.value = text;
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  try { document.execCommand("copy"); done(); } catch(e) { prompt("复制路径", text); }
  area.remove();
}
function copyPath(text){
  const done = () => toast("路径已复制：" + text);
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
  } else {
    fallbackCopy(text, done);
  }
}
document.addEventListener("click", event => {
  const el = event.target.closest("[data-copy]");
  if(!el) return;
  event.preventDefault();
  copyPath(el.getAttribute("data-copy"));
});
$("q").addEventListener("input", render);
$("cat").addEventListener("change", render);
$("sort").addEventListener("change", render);
render();
</script>
<div id="toast" class="toast"></div>
</body>
</html>"""

    page = (template
            .replace("__LAST_SCAN__", html.escape(last_scan))
            .replace("__INBOX_URI__", (ROOT / "00_INBOX").resolve().as_uri())
            .replace("__INBOX_PATH__", html.escape(str((ROOT / "00_INBOX").resolve())))
            .replace("__INBOX_COUNT__", str(inbox_count))
            .replace("__ROOT_URI__", ROOT.resolve().as_uri())
            .replace("__ROOT_PATH__", html.escape(str(ROOT.resolve())))
            .replace("__WARNING__", warning)
            .replace("__TOTAL_ASSETS__", str(len(assets)))
            .replace("__TOTAL_SIZE__", human(total_size))
            .replace("__FREE_GB__", f"{free:.2f}")
            .replace("__DRIVE__", drive)
            .replace("__RESERVE_GB__", f"{reserve:.0f}")
            .replace("__RECLAIM__", human(reclaim) if reclaim else "0 B")
            .replace("__CARDS__", "\n".join(cards))
            .replace("__ROOT__", html.escape(str(ROOT)))
            .replace("__ASSETS_JSON__", data_json)
            .replace("__CATS_JSON__", cats_json)
            .replace("__LABELS_JSON__", labels_json))
    INDEX_PATH.write_text(page, encoding="utf-8")
    rebuild_xlsx(cfg, assets, free, reserve, last_scan)


def cmd_dashboard(args, cfg: dict):
    rebuild_dashboard(cfg)
    print(f"总表已生成: {INDEX_PATH}")
    print(f"Excel: {XLSX_PATH}")


def snapshot_growth(connection: sqlite3.Connection, days: int = 30) -> tuple[dict[str, float], int]:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    rows = connection.execute(
        "SELECT ts, category, size_bytes FROM snapshots WHERE ts >= ? ORDER BY ts", (cutoff,)
    ).fetchall()
    by_category: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for row in rows:
        by_category[row["category"]].append((row["ts"], row["size_bytes"]))
    growth = {}
    for category, items in by_category.items():
        if len(items) < 2:
            growth[category] = 0.0
            continue
        first_time = datetime.fromisoformat(items[0][0])
        last_time = datetime.fromisoformat(items[-1][0])
        elapsed = max((last_time - first_time).total_seconds() / 86400, 1.0)
        delta = items[-1][1] - items[0][1]
        growth[category] = delta / GB / elapsed * days
    return growth, len(rows)


def cmd_space(args, cfg: dict):
    connection = connect_db()
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in connection.execute("SELECT category,size_bytes,file_count FROM assets"):
        top = row["category"].split("/")[0]
        totals[top][0] += 1
        totals[top][1] += row["size_bytes"] or 0
    growth, samples = snapshot_growth(connection)
    dupes = connection.execute(
        "SELECT signature, COUNT(*) c, SUM(size_bytes) total, MAX(size_bytes) keep "
        "FROM assets WHERE signature <> '' GROUP BY signature HAVING c > 1"
    ).fetchall()
    reclaim = sum((row["total"] or 0) - (row["keep"] or 0) for row in dupes)
    top_assets = connection.execute(
        "SELECT title,path,size_bytes FROM assets ORDER BY size_bytes DESC LIMIT ?", (args.top,)
    ).fetchall()
    connection.close()
    drive = drive_letter(ROOT)
    free = free_gb(ROOT)
    reserve = reserve_gb(ROOT, cfg)
    print(f"磁盘 {drive}: 可用 {free:.2f} GB，安全水位 {reserve:.0f} GB，可入库余量 {max(0, free - reserve):.2f} GB")
    print(f"{'大类':<24}{'数量':>8}{'占用':>12}{'配额':>10}{'月增长':>10}")
    for top in cfg.get("top_categories", []):
        count, size = totals.get(top, [0, 0])
        quota = cfg.get("quotas_gb", {}).get(top)
        g = growth.get(top, 0.0)
        print(f"{category_label(top, cfg):<24}{count:>8}{human(size):>12}{(str(quota) + ' GB') if quota else '-':>10}{(f'{g:+.2f} GB' if g else '-'):>10}")
        if quota and size / GB >= quota * 0.9:
            print(f"  ! {category_label(top, cfg)} 已用 {size / GB:.1f} GB，达到配额 {quota} GB 的 90% 以上。")
    total_growth = sum(growth.values())
    if total_growth > 0.05:
        remain = max(0, free - reserve)
        months = remain / total_growth if total_growth else 0
        print(f"\n近 30 天总增长约 {total_growth:+.2f} GB/月；按此速度约 {months:.1f} 个月触及安全水位。")
    else:
        print(f"\n增长快照样本 {samples} 条，暂不足以预测；多跑几次 scan 后自动计算。")
    if reclaim:
        print(f"重复资源可回收 {human(reclaim)}（只报告，不自动删除）。")
    print("\n最大的资源：")
    for row in top_assets:
        print(f"  {human(row['size_bytes']):>10}  {row['title']}  {row['path']}")


def cmd_dupes(args, cfg: dict):
    connection = connect_db()
    rows = connection.execute(
        "SELECT signature, COUNT(*) c, SUM(size_bytes) total, MAX(size_bytes) keep "
        "FROM assets WHERE signature <> '' GROUP BY signature HAVING c > 1 ORDER BY total DESC"
    ).fetchall()
    if not rows:
        print("没有发现重复资源。")
        connection.close()
        return
    reclaim = 0
    for row in rows:
        items = connection.execute(
            "SELECT title,path,size_bytes,acquired FROM assets WHERE signature=? ORDER BY size_bytes DESC",
            (row["signature"],),
        ).fetchall()
        waste = (row["total"] or 0) - (row["keep"] or 0)
        reclaim += waste
        print(f"\n重复组 {row['signature'][:10]}  {len(items)} 份，可回收 {human(waste)}")
        for item in items:
            print(f"  {human(item['size_bytes']):>10}  {item['acquired']}  {item['path']}")
    print(f"\n合计可回收: {human(reclaim)}。确认后再手动移入 99_ARCHIVE 或删除。")
    connection.close()


def cmd_koi_link(args, cfg: dict):
    if koi_tool is None:
        sys.exit("需要 msgpack 才能解析恋活卡片：python -m pip install msgpack")
    summary = koi_tool.link_library(ROOT, apply=args.apply, shortcuts=args.shortcuts)
    print(f"卡片 {summary['cards']} 个，MOD {summary['mods']} 个，依赖条目 {summary['rows']} 条")
    print(f"已安装 {summary['installed']} 条，缺失 {summary['missing']} 条")
    if args.apply:
        print(f"依赖表: {ROOT / '11_Koikatsu' / '_Index' / '卡片MOD依赖.xlsx'}")
        print("每个卡片文件夹内已生成 _mod_links.txt")
        if args.shortcuts:
            print(f"已生成 MOD 快捷方式 {summary['shortcuts']} 个（卡片文件夹下的 _mods）")
    else:
        print("这是预演，未写入报告。确认后加 --apply。")


def cmd_ip_map_add(args, cfg: dict):
    data = load_ip_map(cfg)
    names = [args.character] + [item.strip() for item in (args.aliases or "").split(",") if item.strip()]
    changed = 0
    for name in names:
        old = data["characters"].get(name)
        if old and old != args.ip and not args.force:
            print(f"跳过 {name}: 已映射到 {old}（要覆盖加 --force）")
            continue
        data["characters"][name] = args.ip
        data.setdefault("manual_resolutions", {})[name] = args.ip
        if isinstance(data.get("ambiguous"), dict):
            data["ambiguous"].pop(name, None)
        changed += 1
    save_ip_map(data)
    print(f"已写入 {changed} 条角色映射 -> {args.ip}")


def cmd_learn_ip_map(args, cfg: dict):
    data = load_ip_map(cfg)
    aliases = data.get("ip_aliases", {})
    skip = {
        "Cards_Characters", "Cards_Clothing", "Cards_Scenes", "Cards", "Mods",
        "Mods_Clothing", "Plugins", "_Plugins", "_Packs", "_Tools", "_Index",
        "_Projects", "Projects", "Textures", "textures", "tex", "toon", "spa", "sph",
        "未分IP", "_UnknownAuthor", "Koikatsu", "恋活",
    }

    def find_ip(part: str):
        lowered = part.lower()
        for ip, values in aliases.items():
            for value in values:
                if lowered == value.lower():
                    return ip
        return None

    additions: dict[str, set[str]] = defaultdict(set)
    for raw in args.paths:
        root = Path(raw).expanduser().resolve()
        if not root.exists():
            continue
        roots = [root.parent] if root.is_file() else [root]
        for base in roots:
            for dirpath, dirnames, filenames in os.walk(base):
                depth = len(Path(dirpath).relative_to(base).parts)
                if depth > 4:
                    dirnames[:] = []
                    continue
                parts = Path(dirpath).parts
                for index, part in enumerate(parts[:-1]):
                    ip = find_ip(part)
                    if not ip:
                        continue
                    child = parts[index + 1]
                    if child in skip or child == part:
                        break
                    title, _ = split_name(child)
                    if title and title not in {"卡", "图", "图片", "未命名"}:
                        additions[title].add(ip)
                    break

    base = ROOT / "11_Koikatsu"
    if base.exists():
        for sidecar in base.rglob("_asset.json"):
            try:
                item = json.loads(sidecar.read_text(encoding="utf-8"))
            except Exception:
                continue
            ip = item.get("ip") or item.get("game")
            if not ip or ip == "未分IP":
                continue
            names = [item.get("title", "")]
            character = (item.get("koi") or {}).get("character")
            if isinstance(character, dict):
                names.extend(str(value) for value in character.values() if value)
            for name in names:
                title, _ = split_name(str(name))
                if title and title not in {"卡", "图", "图片", "未命名"}:
                    additions[title].add(ip)

    conflicts = []
    new_items = {}
    for title, ips in additions.items():
        if len(ips) > 1:
            conflicts.append((title, sorted(ips)))
            continue
        ip = next(iter(ips))
        old = data["characters"].get(title)
        if old == ip:
            continue
        if old and old != ip:
            conflicts.append((title, [old, ip]))
            continue
        new_items[title] = ip

    for title, ip in sorted(new_items.items()):
        print(f"学习: {title} -> {ip}")
    for title, ips in conflicts:
        print(f"冲突: {title} -> {', '.join(ips)}（未写入，需要人工确认）")
    print(f"可新增 {len(new_items)} 条，冲突 {len(conflicts)} 条")
    if args.apply:
        data["characters"].update(new_items)
        data.setdefault("manual_resolutions", {}).update(new_items)
        if isinstance(data.get("ambiguous"), dict):
            for name in new_items:
                data["ambiguous"].pop(name, None)
        save_ip_map(data)
        print(f"已写入: {IP_MAP_PATH}")
    else:
        print("这是预演，确认后加 --apply。")


def cmd_ip_review(args, cfg: dict):
    base = ROOT / "11_Koikatsu"
    rows = []
    if base.exists():
        for sidecar in base.rglob("_asset.json"):
            try:
                item = json.loads(sidecar.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not item.get("needs_ip_lookup") and item.get("ip") not in {"", "未分IP"}:
                continue
            candidates = format_ip_candidates(item.get("ip_candidates"))
            rows.append({
                "卡片": item.get("title", ""),
                "类型": (item.get("koi") or {}).get("type", ""),
                "作者": item.get("author", ""),
                "当前IP": item.get("ip", "未分IP"),
                "候选": candidates,
                "路径": str(sidecar.parent),
            })
    print(f"IP 待确认 {len(rows)} 条")
    for row in rows:
        print(f"  {row['当前IP']:<8} {row['卡片']}  候选: {row['候选'] or '-'}")
    if args.apply and rows:
        index_dir = base / "_Index"
        index_dir.mkdir(parents=True, exist_ok=True)
        target = index_dir / "IP待确认.csv"
        with open(target, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"已写入: {target}")


def cmd_plan(args, cfg: dict):
    rows = []
    for raw in args.paths:
        path = Path(raw).expanduser().resolve()
        if not path.exists():
            print(f"跳过（不存在）: {path}")
            continue
        print(f"分析: {path}")
        info = analyze_path(path, cfg, args.date)
        rows.append({
            "source": str(path),
            "category": info["category"],
            "label": category_label(info["category"], cfg),
            "confidence": info["confidence"],
            "needs_review": info["needs_review"],
            "game": info.get("game", ""),
            "ip": info.get("ip", ""),
            "ip_source": info.get("ip_source", ""),
            "needs_ip_lookup": info.get("needs_ip_lookup", False),
            "title": info["title"],
            "author": info.get("author", ""),
            "date": info["acquired"],
            "destination": info["destination"],
            "size_gb": round(info["size_bytes"] / GB, 3),
            "files": info["file_count"],
            "reason": "；".join(info["reasons"]),
        })
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else [])
            writer.writeheader()
            writer.writerows(rows)
        print(f"迁移建议已写入: {out}")
    if not rows:
        return
    print(f"\n{'源':<44}{'分类':<22}{'体积':>10}{'确认':>8}")
    for row in rows:
        print(f"{row['source'][:43]:<44}{row['category']:<22}{row['size_gb']:>9.2f}G"
              f"{'是' if row['needs_review'] else '否':>8}")


def cmd_list(args, cfg: dict):
    connection = connect_db()
    sql = "SELECT * FROM assets"
    conditions = []
    params = []
    if args.category:
        category = resolve_category(args.category, cfg) or args.category
        conditions.append("category LIKE ?")
        params.append(category + "%")
    if args.search:
        conditions.append("(title LIKE ? OR author LIKE ? OR game LIKE ? OR tags LIKE ? OR path LIKE ?)")
        pattern = f"%{args.search}%"
        params.extend([pattern] * 5)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY acquired DESC, title"
    rows = connection.execute(sql, params).fetchall()
    connection.close()
    for row in rows:
        print(f"{row['acquired']}  {human(row['size_bytes']):>10}  {row['category']:<22}  {row['title']}")
    print(f"\n共 {len(rows)} 项")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="资源库批量管理工具")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="创建目录并初始化数据库")

    analyze = sub.add_parser("analyze", help="只分析，不改动文件")
    analyze.add_argument("path")
    analyze.add_argument("--date", help="覆盖日期 YYYY-MM-DD")
    analyze.add_argument("--json", action="store_true")

    ingest = sub.add_parser("ingest", help="归类并移动资源（默认只预演）")
    ingest.add_argument("path")
    ingest.add_argument("--category", help="目标分类 key，如 02_MMD/Models")
    ingest.add_argument("--game")
    ingest.add_argument("--ip", help="恋活 IP/作品，如 原神、蔚蓝档案、原创")
    ingest.add_argument("--kind", help="GameRips 子类：Packages/Models_FBX/Textures/Docs")
    ingest.add_argument("--base", help="LoRA/Checkpoint 底模")
    ingest.add_argument("--title")
    ingest.add_argument("--author")
    ingest.add_argument("--date")
    ingest.add_argument("--source")
    ingest.add_argument("--source-url")
    ingest.add_argument("--tags")
    ingest.add_argument("--notes")
    ingest.add_argument("--project", action="store_true", help="归入对应域的 _Projects")
    ingest.add_argument("--register", action="store_true", help="原地登记，不移动")
    ingest.add_argument("--copy", action="store_true", help="复制入库，保留源文件（适合外接硬盘）")
    ingest.add_argument("--force", action="store_true", help="低置信度也执行")
    ingest.add_argument("--apply", action="store_true", help="真正执行")

    register = sub.add_parser("register", help="原地登记一个已有文件夹")
    register.add_argument("path")
    register.add_argument("--category", required=True)
    register.add_argument("--game")
    register.add_argument("--ip")
    register.add_argument("--base")
    register.add_argument("--title")
    register.add_argument("--author")
    register.add_argument("--source")
    register.add_argument("--tags")
    register.add_argument("--date")
    register.add_argument("--apply", action="store_true")
    register.set_defaults(register=True)

    scan = sub.add_parser("scan", help="扫描库内的 _asset.json 并刷新总表")
    scan.add_argument("--keep-missing", action="store_true")
    scan.add_argument("--no-dashboard", action="store_true")

    sub.add_parser("dashboard", help="重新生成总表")

    space = sub.add_parser("space", help="空间与增长预测")
    space.add_argument("--top", type=int, default=10)

    sub.add_parser("dupes", help="报告重复资源")

    koi_link = sub.add_parser("koi-link", help="解析恋活卡片依赖并关联 zipmod")
    koi_link.add_argument("--apply", action="store_true")
    koi_link.add_argument("--shortcuts", action="store_true", help="在卡片目录 _mods 下生成 MOD 快捷方式")

    ip_add = sub.add_parser("ip-map-add", help="添加角色 -> IP 映射")
    ip_add.add_argument("character")
    ip_add.add_argument("ip")
    ip_add.add_argument("--aliases", help="逗号分隔的别名/英文名")
    ip_add.add_argument("--force", action="store_true")

    ip_learn = sub.add_parser("learn-ip-map", help="从已按 IP/角色整理的目录学习映射")
    ip_learn.add_argument("paths", nargs="+")
    ip_learn.add_argument("--apply", action="store_true")

    ip_review = sub.add_parser("ip-review", help="列出 IP 未定的恋活资源")
    ip_review.add_argument("--apply", action="store_true")

    plan = sub.add_parser("plan", help="批量生成迁移建议，不改动文件")
    plan.add_argument("paths", nargs="+")
    plan.add_argument("--date")
    plan.add_argument("--out", default=str(SYSTEM / "migration_plan.csv"))

    listing = sub.add_parser("list", help="列出已登记资源")
    listing.add_argument("--category")
    listing.add_argument("--search")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    cfg = load_config()
    commands = {
        "init": cmd_init,
        "analyze": cmd_analyze,
        "ingest": cmd_ingest,
        "register": cmd_ingest,
        "scan": cmd_scan,
        "dashboard": cmd_dashboard,
        "space": cmd_space,
        "dupes": cmd_dupes,
        "koi-link": cmd_koi_link,
        "ip-map-add": cmd_ip_map_add,
        "learn-ip-map": cmd_learn_ip_map,
        "ip-review": cmd_ip_review,
        "plan": cmd_plan,
        "list": cmd_list,
    }
    if args.command == "register" and not args.apply:
        print("提示：register 默认只预演，加 --apply 才会写入 _asset.json。")
    commands[args.command](args, cfg)


if __name__ == "__main__":
    main()
