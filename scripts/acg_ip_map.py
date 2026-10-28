"""Build a separate ACG character -> IP map for AI content organization.

Sources:
- Zzzzzzyt/moegirl-dataset (MIT repo; char2subject.json, 39k+ characters)
- HatsuSumi/anime-character-database (JSON character/IP database, 2.3k chars)

The output is intentionally separate from ip_map.json so that anime/game
character names do not affect mod/Koikatsu asset classification.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

SYSTEM = Path(__file__).resolve().parent
ROOT = SYSTEM.parent
SOURCES = SYSTEM / "ip_sources"
MOE = SOURCES / "moegirl"
ANIME = SOURCES / "anime_character_db"
OUT = SYSTEM / "acg_ip_map.json"

try:
    from wiki_ip_map import aliases_for
except Exception:
    def aliases_for(name: str) -> list[str]:
        return [name.strip()] if name and name.strip() else []

BROAD_MARKERS = (
    "作品", "人物", "角色", "分类", "导航", "模板", "含有", "待补充",
    "御主", "仲魔", "人格面具", "超激稀有", "先锋", "单手剑",
    "阵营", "学院", "魂姬", "系列角色",
)
GENERIC = {
    "主角", "玩家", "闲角", "路人", "NPC", "客串", "人类", "学生",
    "老师", "博士", "指挥官", "管理员", "分析员", "店长", "所长",
}
MANUAL_OVERRIDES = {
    "初音未来": "VOCALOID",
    "初音ミク": "VOCALOID",
    "Hatsune Miku": "VOCALOID",
    "亚丝娜": "刀剑神域",
}


def clean_subjects(values) -> list[str]:
    result = []
    for value in values or []:
        if not isinstance(value, str):
            continue
        value = value.strip()
        if len(value) < 2 or value in GENERIC:
            continue
        if value.startswith(("Category:", "分类:", "Template:", "模板:")):
            continue
        if ":" in value or "：" in value:
            continue
        if any(marker in value for marker in BROAD_MARKERS):
            continue
        if value not in result:
            result.append(value)
    return result


def choose_subject(votes: dict[str, float]) -> tuple[str | None, list[str]]:
    if not votes:
        return None, []
    ranked = sorted(votes.items(), key=lambda item: (-item[1], len(item[0])))
    top_score = ranked[0][1]
    top = [name for name, score in ranked if score == top_score]
    if len(top) == 1:
        return top[0], sorted(votes, key=lambda name: (-votes[name], name))
    return None, sorted(votes, key=lambda name: (-votes[name], name))


def add_vote(votes: dict[str, float], subject: str, weight: float):
    votes[subject] = votes.get(subject, 0.0) + weight


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--lookup", help="查询一个角色名")
    args = parser.parse_args()

    if args.lookup:
        if not OUT.exists():
            raise SystemExit("还没有 acg_ip_map.json，先运行 --apply")
        data = json.loads(OUT.read_text(encoding="utf-8"))
        name = args.lookup
        print(name, "->", data.get("characters", {}).get(name))
        print("ambiguous:", data.get("ambiguous", {}).get(name))
        return

    votes_by_alias: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    subjects_by_alias: dict[str, set[str]] = defaultdict(set)
    exact_aliases: set[str] = set()
    source_counts = {}

    # Moegirl dataset: exact page title is a stronger signal than a
    # parenthetical variant such as Alice (Game A).
    char2subject_path = MOE / "char2subject.json"
    if char2subject_path.exists():
        data = json.loads(char2subject_path.read_text(encoding="utf-8"))
        count = 0
        for name, values in data.items():
            subjects = clean_subjects(values)
            if not subjects:
                continue
            count += 1
            exact = "(" not in name and "（" not in name and ":" not in name
            exact_weight = 2.0 if exact else 1.0
            for alias in aliases_for(name):
                for subject in subjects:
                    add_vote(votes_by_alias[alias], subject, exact_weight)
                    subjects_by_alias[alias].add(subject)
                if exact:
                    exact_aliases.add(alias)
            if ":" in name:
                tail = name.split(":", 1)[1]
                for alias in aliases_for(tail):
                    for subject in subjects:
                        add_vote(votes_by_alias[alias], subject, 0.8)
                        subjects_by_alias[alias].add(subject)
        source_counts["moegirl_dataset"] = count
    else:
        print("缺少 Moegirl 数据:", char2subject_path)

    # HatsuSumi anime character database: clean, smaller, high precision.
    chars_path = ANIME / "characters-data.json"
    ips_path = ANIME / "ip-data.json"
    if chars_path.exists() and ips_path.exists():
        chars = json.loads(chars_path.read_text(encoding="utf-8"))
        ips = json.loads(ips_path.read_text(encoding="utf-8"))
        count = 0
        for character in chars.values():
            ip = ips.get(character.get("ip_id"), {})
            subject = (ip.get("name") or ip.get("name_en") or "").strip()
            if not subject:
                continue
            count += 1
            names = [character.get("name"), character.get("name_en")]
            for name in names:
                if not name:
                    continue
                for alias in aliases_for(str(name)):
                    add_vote(votes_by_alias[alias], subject, 1.8)
                    subjects_by_alias[alias].add(subject)
        source_counts["anime_character_database"] = count
    else:
        print("缺少 anime-character-database 数据")

    characters = {}
    ambiguous = {}
    subjects_all = {}
    for alias, votes in votes_by_alias.items():
        subject, options = choose_subject(votes)
        if alias not in exact_aliases and len(options) > 1:
            subject = None
        if subject:
            characters[alias] = subject
        else:
            ambiguous[alias] = options
        if len(options) > 1:
            subjects_all[alias] = options
    for alias, subject in MANUAL_OVERRIDES.items():
        characters[alias] = subject
        ambiguous.pop(alias, None)

    result = {
        "version": 1,
        "meta": {
            "updated": date.today().isoformat(),
            "sources": {
                "moegirl_dataset": {
                    "url": "https://github.com/Zzzzzzyt/moegirl-dataset",
                    "file": "moegirl/char2subject.json",
                    "count": source_counts.get("moegirl_dataset", 0),
                },
                "anime_character_database": {
                    "url": "https://github.com/HatsuSumi/anime-character-database",
                    "files": ["characters-data.json", "ip-data.json"],
                    "count": source_counts.get("anime_character_database", 0),
                },
            },
            "counts": {
                "characters": len(characters),
                "ambiguous": len(ambiguous),
            },
            "note": "Moegirl data is CC BY-NC-SA at source; this file stores only names and work titles for local lookup.",
        },
        "characters": characters,
        "ambiguous": ambiguous,
        "character_subjects": subjects_all,
    }

    print(f"角色 {len(characters)}，歧义 {len(ambiguous)}，多作品 {len(subjects_all)}")
    for name in ["甘雨", "时崎狂三", "博丽灵梦", "阿贝多", "亚丝娜", "初音未来", "爱丽丝"]:
        print(f"  {name}: {characters.get(name)}  {ambiguous.get(name, '')}")
    if args.apply:
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"写入: {OUT}")
    else:
        print("这是预演，确认后加 --apply。")


if __name__ == "__main__":
    main()
