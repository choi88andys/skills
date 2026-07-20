# immutable — Append-only SDD toolkit

Single plugin hosting the Spec-Driven Development toolkit with append-only guarantees: bootstrap a starter, run the 7-step flow from problem framing through PR creation, and (legacy) migrate v0.4 repos to the v0.5 profile system.

**Status**: stable. The 7-step SDD cycle runs entirely from this plugin — no external harness required. `scripts/sdd_mode_detect.sh` consolidates SDD-mode detection into a sourceable helper. The init starter writes `.claude/immutable/` to `.gitignore` for transient-artifact handoff notes. See [CHANGELOG](CHANGELOG.md) for release-by-release detail.

## Skills

| Skill | Command | Purpose | Mutability |
|---|---|---|---|
| [`init/`](init/) | `/immutable:init` | Bootstrap a starter (six modes: spec / app / single × ko / en) | Writes only into the user's CWD; never overwrites |
| [`office-hours/`](office-hours/) | `/immutable:office-hours` | Premise challenge + ≥3 alternatives + transient design-doc note | Writes one transient note under `.claude/immutable/office-hours/` (gitignored) |
| [`prd/`](prd/) | `/immutable:prd` | WHAT — product pitches (6-stage interview, 4 personas, 8-criterion gate) | Append-only + supersede |
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

One install enables every skill listed above.

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

## Pipeline manifest for orchestrators

`pipeline.yaml` at the plugin root declares the canonical phase chain, hard dependencies, and verdict-routing contracts for `flows.pitch_to_ship`. Orchestrators (e.g., a dispatcher or future cross-plugin scheduler) parse it to learn the phase order WITHOUT hard-coding immutable-specific knowledge — they read `dependencies` to respect ordering at dispatch time, so workers do not hit in-skill gates.

The skills themselves enforce their own preconditions at invocation time (refusal or explicit AskUserQuestion warn). The manifest is the orchestration-time signal layered ON TOP — read by tools BEFORE dispatching a worker, complementing the worker-time gates inside each skill.

Schema is `schema_version: 1`. Other plugins adopting the same shape get orchestration compatibility for free.

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

## Deprecated-doc read gate (the plugin's first hook)

`hooks/hooks.json` registers a PostToolUse hook on the `Read` tool
(`scripts/deprecated_read_guard.sh`). When a session reads a document whose
frontmatter carries `deprecated: true` inside any immutable SDD repo
(identified by a `.immutable-prd/` ancestor directory), the document's **body
is withheld** and replaced by a banner naming the superseding file(s). The
frontmatter itself stays visible.

Why a read gate: the validator and starter CI enforce deprecation on the
*write* path only. A deprecated pitch's body is textually indistinguishable
from a live one — the only marker is one frontmatter line — so a session that
reads a dead spec implements from it in good faith, and every artifact it then
produces is individually valid. The defect is *which document was read*, which
leaves nothing for CI to catch. Withholding removes the input instead of
hoping a warning is heeded.

Deliberate boundaries:

- **Read tool only.** Raw-body access for audits or supersede review stays
  available through Bash (`cat`, `git show`, `git log -p`) — deliberately.
  The banner says exactly this.
- **Frontmatter passes through**, so the one sanctioned in-place edit
  (flipping `deprecated: false` → `true`, or back) always has its exact
  target text visible.
- **Off switch**: set `IMMUTABLE_DEPRECATED_GUARD_DISABLE=1` (e.g. in a
  settings `env` block). The plugin system has no per-hook toggle, so the
  guard ships its own. Instrumentation: set
  `IMMUTABLE_DEPRECATED_GUARD_LOG=<path>` to append one `withheld`/`pass`
  line per gated Read.
- **Requirements**: bash, `jq`, and python3 with PyYAML. PyYAML is already
  required by the bundled validator; `jq` is new and used only by the hook's
  fast path. Missing PyYAML fails **open** with a deterministic warning —
  the gate never blocks reads it cannot judge. Windows adopters need these
  via a POSIX-ish environment (e.g. Git Bash), which the plugin's skills
  already assume.

Hooks load at session start — restart the session after enabling or updating
the plugin.

## Design heritage

`immutable` is built from two layered fusions.

### Layer 1 — `immutable-prd` (the artifact contract)

The `immutable-prd` lineage already reconciled two opposing document traditions:

- **Immutable pitch** (Basecamp Shape Up) — append-only artifact, history-as-audit-trail. Strong on accountability; silent on "what we know now."
- **Mutable PRD** (traditional product spec) — living document, revised as understanding evolves. Strong on accuracy; weak on audit trail because revisions silently overwrite prior decisions.

`immutable-prd` keeps both: pitches and ADRs are append-only, AND supersede chains carry forward — the active artifact reflects current understanding (the PRD value), while the chain preserves the full revision history (the pitch value). Accuracy AND accountability without picking a side. The directory marker `.immutable-prd/` preserves the lineage name as the system-level path identifier.

### Layer 2 — gstack's transient → artifact pipeline

The gstack harness contributed a **flow philosophy**: separate working state from permanent record.

- **Transient** (working state): office-hours exploration, design handoff, plan-review verdicts. Gitignored under `.claude/immutable/`. Disposable; regenerable from the next round of work.
- **Artifact** (permanent record): pitches, ADRs, PRs. Append-only, committed, audit-trail material.

The flow is a pipeline that turns transient notes into artifact decisions: office-hours feeds pitch authoring, design plus plan-review notes feed the PR body, review-surfaced triggers feed ADRs. Uncertainty is absorbed in the transient layer; only resolved decisions are promoted to the artifact layer.

### v0.6.0 — the unification

Before v0.6.0, the plugin shipped only the artifact-authoring skills (`prd`, `adr`); the gstack pipeline lived in a separate harness layer that had to be installed and maintained alongside the plugin. v0.6.0 absorbs the gstack flow skills into the plugin so a single install ships both halves: the append-only-but-accurate artifact contract (immutable-prd lineage) AND the transient → artifact flow process (gstack lineage). The full 7-step SDD cycle now runs without any external harness dependency.

## Design principles

1. **Speculation is forbidden.** Unknown answers become `[미확정]` / `[TBD]` tags (locale-specific via profile) that block file generation.
2. **Append-only is cultural, not arbitrary.** History is the audit trail; mutation is the exception (single allowed in-place change: flipping `deprecated: false → true`).
3. **The author owns the commit.** Skills generate files; humans review and commit. No skill runs `git add` / `git commit` / `git push`.
4. **Quality gates are strict.** Authoring skills enforce a 90% completeness gate before writing. The 90% gate refuses generation outright — no "almost good enough" path.
5. **Configuration is data, not code.** Section headings, personas, gate criteria, and workflow prose live in profile YAML and the strings catalog. Teams override without forking the plugin.

## Ship positioning

`/immutable:ship` is intentionally **minimum-viable**. It guarantees chain integrity at PR time — verifies the eng review APPROVED, auto-includes the pitch and linked ADR paths in the PR body, and guards against common ship-time mistakes (dirty tree, failing tests, protected branch). It does NOT carry cross-session learnings capture, worktree-policy enforcement, or team-specific telemetry. Teams that want those layers should add them as hooks or wrapper skills around the `/immutable:ship` invocation rather than maintaining a parallel ship path.

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

See [Design heritage](#design-heritage) above for the two-lineage origin story. Pattern sources documented inside each skill's `SKILL.md` under Credits. Common sources:

- gstack (internal harness) — flow shape, adversarial review patterns, 90% gate
- [mattpocock/skills](https://github.com/mattpocock/skills) (MIT) — `grill-me`, `domain-model`
- [zscole/adversarial-spec](https://github.com/zscole/adversarial-spec) — PRD critique criteria
- [alirezarezvani/claude-skills](https://github.com/alirezarezvani/claude-skills) (MIT) — `adversarial-reviewer`
- Michael Nygard, *Documenting Architecture Decisions* (2011) — ADR template
- Basecamp Shape Up — append-only pitch framing
