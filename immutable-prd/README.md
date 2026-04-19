# /immutable-prd

Guided authoring skill for immutable, append-only PRD/pitch files in a Spec-Driven Development (SDD) workflow.

## What this skill does

- Walks the author through a structured interview (one question at a time, each with a recommended answer) to produce a pitch-style PRD.
- Runs domain-language checks, three-persona adversarial review, and a 90% completeness gate. Refuses to generate a file if the answer set is incomplete.
- Writes the file only. Never commits or pushes — the author reviews and commits via their preferred path.

## Expected repo structure

This skill assumes the target spec repo follows this convention:

```
<repo-root>/
├── pitches/
│   ├── README.md         # domain allowlist (table)
│   ├── TEMPLATE.md       # pitch body template
│   └── <domain>/
│       └── YYYY-MM-DD-<kebab-slug>.md
└── CONTRIBUTING.md
```

Each pitch file has YAML frontmatter:

```yaml
---
domain: <name>
supersedes: <previous-filename|null>
deprecated: false
---
```

If your repo uses a different structure, fork and adapt `SKILL.md`. Configurable paths are out of scope for v0.x.

## Installation

### As a plugin (from the skills marketplace)

```sh
claude plugin marketplace add choi88andys/skills
claude plugin install immutable-prd
```

### As a local skill

Copy the `immutable-prd/` directory into your Claude Code skills path, or clone this repo and reference it directly.

## Usage

From the root of your spec repo:

```sh
cd <your-spec-repo>
claude
```

Then invoke:

```
/immutable-prd
```

Or with initial context:

```
/immutable-prd add auto-modal to notice domain
```

## Stages

1. **Intent Routing** — classify new / update / deprecate; confirm target domain.
2. **Context Intake** (optional) — accept curated external materials (Figma URL, Notion page, local draft, chat excerpt). Summarize and confirm before using.
3. **Interview** — grill-me pattern, one question at a time, recommended answers included.
4. **Domain Language Check** — code identifier detection, terminology drift.
5. **Adversarial Review** — three personas (New Engineer, Customer Support, Product Lead) each surface at least one gap.
6. **90% Completeness Gate** — 7-criterion checklist. Refuse if any unresolved gap or any `[미확정]` tag remains.
7. **File Generation & Handoff** — write file, print commit instructions. User commits manually.

## Core principles

- **Speculation is forbidden.** Unknown answers become `[미확정]` tags that block file generation.
- **Quality gate is strict.** Append-only systems carry permanent history — low-quality pitches are expensive to unwind.
- **The author owns the commit.** The skill generates; the human decides.

## Language

User-facing prompts default to Korean. To change the language, edit the user-facing strings in `SKILL.md` consistently.

## License

MIT — see [LICENSE](../LICENSE) at repo root.

## Credits

Design patterns adapted from:

- [mattpocock/skills](https://github.com/mattpocock/skills) (MIT) — `grill-me`, `domain-model`
- [zscole/adversarial-spec](https://github.com/zscole/adversarial-spec) — PRD critique criteria
- [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) (MIT) — `adversarial-reviewer`

No source files copied. Patterns referenced only.
