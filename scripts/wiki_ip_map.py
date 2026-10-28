"""Build ip_map.json from encyclopedic sources.

Primary: Bangumi v0 characters (structured, Chinese names for CN games).
Cross-check: Bilibili game wikis (MediaWiki category members, current CN names).
Alias supplement: Brind235808/No-Reload-Mod-Manager auto_icon JSON
(mod hash -> character icon; folder name gives the game/IP).
Wikipedia and Moegirl are kept as manual/spot-check sources; Moegirl's anonymous
content API is blocked by Cloudflare, so it is not scraped in bulk here.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

SYSTEM = Path(__file__).resolve().parent
ROOT = SYSTEM.parent
MAP_PATH = SYSTEM / "ip_map.json"
CACHE_DIR = SYSTEM / "ip_sources"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = "asset-manager/1.0 (local library mapping; non-commercial)"

BANGUMI_SUBJECTS = [
    ("原神", 284157),
    ("崩坏星穹铁道", 360097),
    ("绝区零", 380974),
    ("鸣潮", 385208),
    ("蔚蓝档案", 300648),
    ("碧蓝航线", 208559),
    ("少女前线", 136802),
    ("明日方舟", 225878),
    ("NIKKE", 343054),
    ("明日方舟终末地", 374638),
    ("无限暖暖", 409324),
    ("尘白禁区", 378389),
]

BILIGAME_CATEGORIES = [
    ("原神", "ys", "Category:角色"),
    ("崩坏星穹铁道", "sr", "Category:角色"),
    ("绝区零", "zzz", "Category:角色"),
    ("明日方舟", "arknights", "Category:干员"),
    ("NIKKE", "nikke", "Category:角色"),
]

ICON_SOURCES = [
    ("原神", "genshin"),
    ("崩坏星穹铁道", "hsr"),
    ("鸣潮", "wuwa"),
    ("绝区零", "zzz"),
    ("明日方舟终末地", "endfield"),
]

GENERIC_NAMES = {
    "主角", "玩家", "闲角", "路人", "客串", "NPC", "モブキャラクター",
    "企业", "光辉", "独角兽", "胜利", "荣耀", "博士", "老师",
    "指挥官", "管理员", "分析员", "绳匠", "店长", "所长",
}

SINGLE_CHAR_WHITELIST = {"心", "椿", "鹿", "琴", "魈", "刻"}


def cached_json(url: str, cache_name: str, refresh: bool = False, data: bytes | None = None):
    path = CACHE_DIR / cache_name
    if path.exists() and not refresh:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    headers = {"User-Agent": USER_AGENT}
    if data is not None:
        headers["Content-Type"] = "application/json"
    last_error = None
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(request, timeout=40) as response:
                payload = json.loads(response.read().decode("utf-8"))
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return payload
        except Exception as exc:
            last_error = exc
            time.sleep(8 + attempt * 7)
    raise last_error


def bangumi_names(subject_id: int, refresh: bool) -> tuple[list[str], dict]:
    url = f"https://api.bgm.tv/v0/subjects/{subject_id}/characters"
    payload = cached_json(url, f"bangumi_{subject_id}.json", refresh)
    names = []
    for item in payload:
        relation = item.get("relation") or ""
        if relation in {"闲角", "客串"}:
            continue
        name = (item.get("name") or "").strip()
        if name:
            names.append(name)
    meta = {"url": f"https://bgm.tv/subject/{subject_id}/characters", "count": len(names)}
    return names, meta


def biligame_names(site: str, category: str, refresh: bool) -> tuple[list[str], dict]:
    params = {
        "action": "query", "list": "categorymembers", "cmtitle": category,
        "cmlimit": "500", "cmnamespace": "0", "format": "json", "formatversion": "2",
    }
    url = f"https://wiki.biligame.com/{site}/api.php?" + urllib.parse.urlencode(params)
    payload = cached_json(url, f"biligame_{site}_{re.sub(r'[^0-9A-Za-z]+', '_', category)}.json", refresh)
    names = [item.get("title", "").strip() for item in payload.get("query", {}).get("categorymembers", [])]
    meta = {"url": f"https://wiki.biligame.com/{site}/{category}", "count": len(names)}
    return [name for name in names if name], meta


def icon_names(game: str, refresh: bool) -> tuple[list[str], dict]:
    url = (
        "https://raw.githubusercontent.com/Brind235808/No-Reload-Mod-Manager/"
        f"main/assets/cloud_data/auto_icon/{game}/_icon.json"
    )
    payload = cached_json(url, f"icons_{game}.json", refresh)
    names = set()
    for value in payload.values():
        if not isinstance(value, str):
            continue
        filename = value.rsplit("/", 1)[-1]
        stem = re.sub(r"\.[a-zA-Z0-9]+$", "", filename).strip()
        if stem:
            names.add(stem)
    meta = {
        "url": f"https://github.com/Brind235808/No-Reload-Mod-Manager/tree/main/assets/cloud_data/auto_icon/{game}",
        "count": len(names),
    }
    return sorted(names), meta


def aliases_for(name: str) -> list[str]:
    clean = name.strip()
    clean = re.sub(r"^[「『\"“]+|[」』\"”]+$", "", clean).strip()
    variants = {clean}
    base = re.sub(r"[（(][^）)]*[）)]\s*$", "", clean).strip()
    if base:
        variants.add(base)
    if "：" in clean:
        variants.add(clean.replace("：", "·"))
    if ":" in clean:
        variants.add(clean.replace(":", "·"))
    if "_" in clean:
        variants.add(clean.replace("_", " "))
        variants.add(clean.replace("_", ""))
    if "-" in clean:
        variants.add(clean.replace("-", " "))
    result = []
    for item in variants:
        item = item.strip()
        if not item or item in GENERIC_NAMES:
            continue
        if len(item) == 1 and item not in SINGLE_CHAR_WHITELIST:
            continue
        if len(item) > 40:
            continue
        result.append(item)
    return result


def load_map() -> dict:
    if MAP_PATH.exists():
        try:
            data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        data = {}
    data.setdefault("version", 1)
    data.setdefault("ip_aliases", {})
    data.setdefault("characters", {})
    data.setdefault("author_hints", {})
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--provider", choices=["all", "bangumi", "biligame", "icons"], default="all")
    args = parser.parse_args()

    data = load_map()
    proposals: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    provider_meta = {}

    if args.provider in {"all", "bangumi"}:
        provider_meta["bangumi"] = {}
        for ip, subject_id in BANGUMI_SUBJECTS:
            try:
                names, meta = bangumi_names(subject_id, args.refresh)
                provider_meta["bangumi"][ip] = meta
                for name in names:
                    for alias in aliases_for(name):
                        proposals[alias]["bangumi"].add(ip)
                print(f"Bangumi {ip}: {len(names)}")
            except Exception as exc:
                print(f"Bangumi {ip} 失败: {exc}")
            time.sleep(1.2)

    if args.provider in {"all", "biligame"}:
        provider_meta["biligame"] = {}
        for ip, site, category in BILIGAME_CATEGORIES:
            try:
                names, meta = biligame_names(site, category, args.refresh)
                provider_meta["biligame"][ip] = meta
                for name in names:
                    for alias in aliases_for(name):
                        proposals[alias]["biligame"].add(ip)
                print(f"Bilibili {ip}: {len(names)}")
            except Exception as exc:
                print(f"Bilibili {ip} 失败: {exc}")
            time.sleep(1.2)

    if args.provider in {"all", "icons"}:
        provider_meta["no_reload_icons"] = {}
        for ip, game in ICON_SOURCES:
            try:
                names, meta = icon_names(game, args.refresh)
                provider_meta["no_reload_icons"][ip] = meta
                for name in names:
                    for alias in aliases_for(name):
                        proposals[alias]["no_reload_icons"].add(ip)
                print(f"auto_icon {ip}: {len(names)}")
            except Exception as exc:
                print(f"auto_icon {ip} 失败: {exc}")
            time.sleep(0.5)

    existing = data.get("characters", {})
    manual = data.get("manual_resolutions", {})
    sources = data.setdefault("character_sources", {})
    ambiguous = {}
    conflicts = []
    new_items = {}
    same_items = 0

    for name, by_provider in proposals.items():
        if name in manual:
            continue
        ips = set()
        for values in by_provider.values():
            ips.update(values)
        if len(ips) > 1:
            ambiguous[name] = sorted(ips)
            continue
        ip = next(iter(ips))
        old = existing.get(name)
        if old and old != ip:
            conflicts.append({"name": name, "existing": old, "proposed": ip})
            ambiguous[name] = sorted({old, ip})
            continue
        if old == ip:
            same_items += 1
            sources.setdefault(name, {"ip": ip, "sources": []})
            for provider in by_provider:
                if provider not in sources[name]["sources"]:
                    sources[name]["sources"].append(provider)
            continue
        new_items[name] = ip
        sources[name] = {"ip": ip, "sources": sorted(by_provider)}

    print(f"新增 {len(new_items)}，已存在 {same_items}，多 IP 跳过 {len(ambiguous)}，冲突 {len(conflicts)}，人工优先 {len(manual)}")
    for name in sorted(ambiguous)[:20]:
        print(f"  多IP: {name} -> {', '.join(ambiguous[name])}")
    for item in conflicts[:20]:
        print(f"  冲突: {item['name']} 现有 {item['existing']} / 新 {item['proposed']}")

    if args.apply:
        if MAP_PATH.exists():
            backup = MAP_PATH.with_name("ip_map.backup.json")
            backup.write_text(MAP_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        data["characters"].update(new_items)
        data["ambiguous"] = ambiguous
        data["conflicts"] = conflicts
        data["meta"] = {
            "updated": date.today().isoformat(),
            "providers": provider_meta,
            "note": "Bangumi primary; Bilibili wiki cross-check; No-Reload auto_icon aliases; Moegirl/Wikipedia manual/spot-check.",
        }
        MAP_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"写入: {MAP_PATH}")
    else:
        print("这是预演，确认后加 --apply。")


if __name__ == "__main__":
    main()
