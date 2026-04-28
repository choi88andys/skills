# immutable — Append-only SDD toolkit

Single plugin hosting nine skills for Spec-Driven Development with append-only guarantees: bootstrap a starter, run a 7-step flow from problem framing through PR creation, and migrate v0.4 repos to the v0.5 profile system.

**Status**: v0.6.0. Adds five new flow skills (`office-hours`, `design`, `plan-review-ceo`, `plan-review-eng`, `ship`) so the entire SDD cycle runs from this plugin alone — no external harness required. The `scripts/sdd_mode_detect.sh` helper consolidates SDD-mode detection into a single sourceable script. The init starter now adds `.claude/immutable/` to `.gitignore` for the new transient-artifact namespace. v0.5.x repos pick up the new skills immediately on install — `/immutable:prd`, `/immutable:adr`, and `/immutable:migrate` behavior is unchanged.

## Skills

| Skill | Command | Purpose | Mutability |
|---|---|---|---|
| [`init/`](init/) | `/immutable:init` | Bootstrap a starter (six modes: spec / app / single × ko / en) | Writes only into the user's CWD; never overwrites |
| [`office-hours/`](office-hours/) | `/immutable:office-hours` | Premise challenge + ≥3 alternatives + transient design-doc note | Writes one transient note under `.claude/immutable/office-hours/` (gitignored) |
| [`prd/`](prd/) | `/immutable:prd` | WHAT — product pitches (6-stage interview, 3 personas, 7-criterion gate) | Append-only + supersede |
| [`design/`](design/) | `/immutable:design` | App-side context handoff (lightweight; pitch is the design artifact) | Writes one transient handoff note (gitignored) |
| [`plan-review-ceo/`](plan-review-ceo/) | `/immutable:plan-review-ceo` | Scope challenge + 11-section adversarial review of pitch + linked ADRs | Writes one transient review note (gitignored) |
| [`plan-review-eng/`](plan-review-eng/) | `/immutable:plan-review-eng` | 4-section engineering review (architecture / code / test / perf) + worktree analysis | Writes one transient review note (gitignored) |
| [`adr/`](adr/) | `/immutable:adr` | WHY — Architecture Decision Records (Nygard template, 3 personas, 6-criterion gate) | Append-only + supersede |
| [`ship/`](ship/) | `/immutable:ship` | Pre-ship verification + PR creation with pitch + ADR paths included (minimum-viable; see "Ship positioning" below) | Creates a GitHub PR after explicit user confirmation |
| [`migrate/`](migrate/) | `/immutable:migrate` | v0.4 → v0.5 config migration (idempotent, zero-data-loss) | Edits `.immutable-prd/` only; never touches pitches / ADRs |

### 7-step flow

Single-repo:

```
/immutable:office-hours
  → /immutable:prd
  → /immutable:design
  → /immutable:plan-review-ceo
  → /immutable:plan-review-eng
  → /immutable:adr            (when an architecture decision is surfaced)
  → /immutable:ship
```

Two-repo split — spec repo runs the first two, implementation repo runs the rest:

```
[spec]  /immutable:office-hours → /immutable:prd
[app]   /immutable:design → /immutable:plan-review-ceo → /immutable:plan-review-eng
        → /immutable:adr (when surfaced) → /immutable:ship
```

`/immutable:init` is a one-shot bootstrap. `/immutable:migrate` is a one-shot upgrade for existing v0.4 repos; new repos created via `/immutable:init` are already v3.

## Installation

```sh
claude plugin marketplace add choi88andys/skills
claude plugin install immutable
```

One install enables all four skills.

## Repository layouts

Both authoring skills consume `.immutable-prd/config.yml` at the target repo root, resolved via walk-up from CWD. Three layouts are supported:

| `repo_mode` | Pitches | ADRs | Starter |
|---|---|---|---|
| `two-repo-spec` | this repo | sibling app repo | `spec-{ko,en}` |
| `two-repo-app` | sibling spec repo (`spec_repo_path`) | this repo | `app-{ko,en}` |
| `single-repo` | this repo (`spec/pitches/`) | this repo (`adr/`) | `single-{ko,en}` |

Standalone reference configs in [`examples/`](examples/):

- [`config.yml`](examples/config.yml) — two-repo-spec
- [`config-two-repo-app.yml`](examples/config-two-repo-app.yml) — two-repo-app
- [`config-single-repo.yml`](examples/config-single-repo.yml) — single-repo

The directory name `.immutable-prd/` is retained for back-compat with the SDD_MODE_DETECT bash snippet — it's the system-level path marker, distinct from the plugin name.

## Schema, profile, strings catalog, validator

Full reference lives in [`SCHEMA.md`](SCHEMA.md):

- Document types, frontmatter fields, naming conventions
- Reference policy (pitch → ADR direction; `_global` reserved scope)
- Mutability rules + supersede chain semantics
- `config.yml` schema (v2 + v3, repo-mode-specific fields)
- Profile system — full schema, resolution order, fork vs. override
- Strings catalog — schema, key naming, responsibility split with profiles
- Validation invariants 1–8 (validator coverage)
- Migration guide v0.2 → v0.3/v0.4 → v0.5

## Design principles (shared by all four skills)

1. **Speculation is forbidden.** Unknown answers become `[미확정]` / `[TBD]` tags (locale-specific via profile) that block file generation.
2. **Append-only is cultural, not arbitrary.** History is the audit trail; mutation is the exception (single allowed in-place change: flipping `deprecated: false → true`).
3. **The author owns the commit.** Skills generate files; humans review and commit. No skill runs `git add` / `git commit` / `git push`.
4. **Quality gates are strict.** Authoring skills enforce a 90% completeness gate before writing. The 90% gate refuses generation outright — no "almost good enough" path.
5. **Configuration is data, not code.** Section headings, personas, gate criteria, and workflow prose live in profile YAML and the strings catalog. Teams override without forking the plugin.

## Ship positioning (v0.6.0+)

`/immutable:ship` is intentionally **minimum-viable**. It guarantees chain integrity at PR time — verifies the eng review APPROVED, auto-includes pitch + linked ADR paths in the PR body, and guards against the common ship-time mistakes (dirty tree, failing tests, protected branch). It does NOT carry cross-session learnings capture, worktree-policy enforcement, or any team-specific telemetry.

If your environment also runs an external harness with a richer ship skill (for example, gstack `/sprint:ship`), prefer that one. The two skills coexist without conflict because:

- **Slash invocation**: `/immutable:ship` and `/sprint:ship` are different namespaces — neither shadows the other.
- **Natural-language routing**: each environment's personal `UserPromptSubmit` hook decides which skill picks up phrases like "PR 만들어" / "ship it". Hooks that already point natural-language ship intent at `/sprint:ship` keep doing so; `/immutable:ship` then becomes the explicit-call fallback.
- **Plugin-only environments** (no external harness): `/immutable:ship` is the only ship path and natural-language routing reaches it via the description's trigger phrases.

This way the plugin promises a complete 7-step flow on any machine, while harness-using teams can keep their richer shipping experience without shadow conflicts.

## What v0.6.0 changed (vs. v0.5.8)

- Five new flow skills: `office-hours`, `design`, `plan-review-ceo`, `plan-review-eng`, `ship`. Together with the existing `prd` and `adr`, they cover the entire 7-step SDD flow.
- `scripts/sdd_mode_detect.sh` extracted as a sourceable helper — the cross-pair detection logic used by every flow skill lives in one place.
- `.claude/immutable/` transient namespace introduced for cross-skill handoff notes (gitignored via init starter).
- Existing skills (`prd`, `adr`, `init`, `migrate`) and the validator are unchanged.

## What v0.5 changed (vs. v0.4)

- Two new skills: `/immutable:init` (bootstrap) and `/immutable:migrate` (config upgrade).
- Profile system + strings catalog externalize what v0.4 hardcoded in SKILL.md.
- `validate_docs.py` is profile-aware and gains an opt-in `--strict-body` flag.
- v0.4 repos keep working unchanged via the zero-action path.

Full release notes in [`CHANGELOG.md`](CHANGELOG.md).

## License

MIT — see [LICENSE](../LICENSE) at repo root.

## Credits

Pattern sources documented inside each skill's `SKILL.md` under Credits. Common sources:

- [mattpocock/skills](https://github.com/mattpocock/skills) (MIT) — `grill-me`, `domain-model`
- [zscole/adversarial-spec](https://github.com/zscole/adversarial-spec) — PRD critique criteria
- [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) (MIT) — `adversarial-reviewer`
- Michael Nygard, *Documenting Architecture Decisions* (2011) — ADR template
- Basecamp Shape Up — append-only spec framing
