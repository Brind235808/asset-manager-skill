# Mapping snapshots

Bundled with the skill so a fresh install works without fetching anything.

| File | Characters | Ambiguous | Built |
|---|---:|---:|---|
| `ip_map.json` | 2,573 | 18 | 2026-10-28 |
| `acg_ip_map.json` | 44,821 | 11,999 | 2026-10-28 |

## ip_map.json

Game/MOD-side mapping: IP aliases, character → game/IP, author hints.
Sources used for this snapshot:

- Bangumi v0 subject characters (12 games)
- Bilibili game wikis (Genshin, HSR, ZZZ, Arknights, NIKKE)
- No-Reload-Mod-Manager `auto_icon` character aliases
- Manual/learned additions

Rebuild with `scripts/wiki_ip_map.py --apply` (network + cache).

## acg_ip_map.json

AI-content/ACG-side mapping: character → work/IP, plus multi-work candidates.

Sources:

- Zzzzzzyt/moegirl-dataset `char2subject.json` (MIT repository; Moegirl content is CC BY-NC-SA)
- HatsuSumi/anime-character-database (no single license declared upstream)
- A few manual overrides (e.g. Hatsune Miku → VOCALOID)

Rebuild with `scripts/acg_ip_map.py --apply` after placing the source JSON in
`_SYSTEM/ip_sources/`.

## Update behavior

`install.ps1` / `install.sh` copy a bundled map **only if the target does not
already exist**. Existing local maps are never overwritten.

## Licensing

The maps are a separate data layer from the MIT-licensed code. See
[../DATA_LICENSE.md](../DATA_LICENSE.md). Do not use the data commercially
without checking the upstream terms.
