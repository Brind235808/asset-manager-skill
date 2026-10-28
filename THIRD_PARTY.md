# Third-party notices

This repository contains original code and documentation plus compiled mapping
snapshots under `data/`. It does **not** bundle game assets, card images, mod
packages, or wiki prose. Mapping data is covered separately by
[DATA_LICENSE.md](DATA_LICENSE.md).

## Format / parser references

- **GenesisAN/illusionsCard** and **GenesisAN/KKCardModCheck** — public
  documentation and Go implementations of the KK/KKS card container format.
  `scripts/koi.py` is an independent Python implementation written for this
  project; no third-party source code is copied.
  - https://github.com/GenesisAN/illusionsCard
  - https://github.com/GenesisAN/KKCardModCheck
- **vam-backstage** — public documentation of VaM `.var` path/type rules used
  as a reference for category mapping.
  - https://github.com/cyberpunk2073/vam-backstage

## Optional mapping sources (not bundled)

- **Zzzzzzyt/moegirl-dataset** — MIT repository; underlying Moegirlpedia text
  is CC BY-NC-SA. Only names and work titles are used locally for lookup.
  - https://github.com/Zzzzzzyt/moegirl-dataset
- **HatsuSumi/anime-character-database** — JSON character/IP database. The
  repository does not declare a single license; verify before redistributing.
  - https://github.com/HatsuSumi/anime-character-database
- **Bangumi** — API and subject/character data. Follow Bangumi's terms.
  - https://github.com/bangumi/api
- **Bilibili game wikis** — MediaWiki APIs; content terms apply.
- **Fandom** — per-wiki MediaWiki APIs; content terms apply.
- **Wikipedia / Wikimedia** — CC BY-SA and local terms apply.
- **No-Reload-Mod-Manager auto_icon** — public repository data used as an
  optional alias source.
  - https://github.com/Brind235808/No-Reload-Mod-Manager
- **VAM community documentation** — used only for file-type/organization
  knowledge; no VAM assets are included.

## Python dependencies

- Pillow — HPND license
- msgpack-python — Apache-2.0
- openpyxl — MIT

Users are responsible for complying with the terms of any data source they
choose to build or import.
