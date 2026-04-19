# skills

A collection of Claude Code skills and plugins for Spec-Driven Development (SDD).

## Plugins

| Plugin | Skills | Purpose |
|---|---|---|
| [`immutable`](immutable/) | `/immutable:prd`, `/immutable:adr` | Append-only SDD — pitches (WHAT) + Architecture Decision Records (WHY). Single plugin install. |

v0.4 merges the v0.3 two-plugin layout (`immutable-prd` + `immutable`) into the unified `immutable` plugin.

## SDD 워크플로우 (v0.4)

A typical feature lifecycle:

1. **Pitch the feature** — `/immutable:prd` walks through an interview with adversarial review + 90% gate. Output: `pitches/<domain>/YYYY-MM-DD-<slug>.md` in the spec repo.
2. **(Optional) Record an ADR when the feature requires a load-bearing technical decision** — `/immutable:adr` captures Context / Decision / Consequences / Alternatives for one of four justification areas (rollout / observability / migration / external-deps). Output: `adr/YYYY-MM-DD-<slug>.md` in the app repo.

All append-only skills enforce strict invariants:

- Speculation is forbidden — unknown answers block file generation via `[미확정]` tags.
- At most one active file per chain — supersession flips the old file's `deprecated` flag.
- Skills write files; **the author owns the commit**.

Configuration lives in `.immutable-prd/config.yml` at each repo root (spec repo and app repo have their own). See [immutable/SCHEMA.md](immutable/SCHEMA.md) for the full schema, repo layouts (two-repo and single-repo), reference policy, and validation invariants.

### What v0.4 dropped vs. v0.3 / v0.2

- v0.4 drops the two-plugin split. Single plugin `immutable` ships both skills — one marketplace install, consistent `/immutable:*` namespace.
- v0.3 already dropped 4 of v0.2's 5 companion skill types (`design`, `tech-spec`, `status`, `supersede`) and relocated ADRs from the spec repo into the app repo.
- Full migration rationale: [immutable/SCHEMA.md](immutable/SCHEMA.md).

## Installation

### Plugin marketplace

```sh
claude plugin marketplace add choi88andys/skills
claude plugin install immutable    # provides /immutable:prd and /immutable:adr
```

### Local

Clone the repo and reference individual skill directories, or copy them into your Claude Code skills path.

## Structure

```
skills/
├── LICENSE                              # MIT
├── README.md                            # this file
├── .claude-plugin/
│   └── marketplace.json                 # plugin marketplace manifest (v0.4 — 1 plugin, 2 skills)
└── immutable/                           # the immutable plugin
    ├── README.md                        # plugin overview
    ├── SCHEMA.md                        # shared schema (config, frontmatter, reference policy, invariants, migration)
    ├── examples/                        # sample config.yml for spec / app / single-repo modes
    ├── scripts/
    │   ├── find_config.sh               # walk-up config detection helper
    │   └── validate_docs.py             # stand-alone validator (PR check / CI)
    ├── prd/                             # /immutable:prd skill — pitch authoring
    │   └── SKILL.md
    └── adr/                             # /immutable:adr skill — ADR authoring
        ├── SKILL.md
        ├── README.md
        └── TEMPLATE.md                  # ADR body seed + 4 justification-area examples
```

## Pre-commit / CI validation

The `immutable/scripts/validate_docs.py` validator runs without a Claude Code session and exits 1 on any violation. Wire it into a pre-commit hook or CI step to catch frontmatter drift, stale references, and single-active-invariant violations before they reach main.

```sh
python3 immutable/scripts/validate_docs.py                    # auto-detect config via walk-up
python3 immutable/scripts/validate_docs.py --config <path>    # explicit config path
python3 immutable/scripts/validate_docs.py --json             # machine-readable output
```

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

Individual skills cite their design-pattern sources. Common references:

- [mattpocock/skills](https://github.com/mattpocock/skills) (MIT)
- [zscole/adversarial-spec](https://github.com/zscole/adversarial-spec)
- [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) (MIT)
- Michael Nygard, *Documenting Architecture Decisions* (2011) — ADR template
- Basecamp Shape Up — append-only spec framing
