# immutable — Append-only SDD toolkit

Single plugin hosting the Spec-Driven Development toolkit with append-only guarantees: bootstrap a starter, run the 7-step flow from problem framing through PR creation, and (legacy) migrate v0.4 repos to the v0.5 profile system.

**Status**: stable. The 7-step SDD cycle runs entirely from this plugin — no external harness required. `scripts/sdd_mode_detect.sh` consolidates SDD-mode detection into a sourceable helper. The init starter writes `.claude/immutable/` to `.gitignore` for transient-artifact handoff notes. See [CHANGELOG](CHANGELOG.md) for release-by-release detail.

## Skills

| Skill | Command | Purpose | Mutability |
|---|---|---|---|
| [`init/`](init/) | `/immutable:init` | Bootstrap a starter (six modes: spec / app / single × ko / en) | Writes only into the user's CWD; never overwrites |
| [`office-hours/`](office-hours/) | `/immutable:office-hours` | Premise challenge + ≥3 alternatives + transient design-doc note | Writes one transient note under `.claude/immutable/office-hours/` (gitignored) |
| [`prd/`](prd/) | `/immutable:prd` | WHAT — product pitches (6-stage interview, 4 personas, 8-criterion gate; one pitch per user-facing feature area, every user-entered value declared per field, new versions copied and diff-checked; opt-in requirement contract against a tracker ticket) | Append-only + supersede |
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

Use Bash, Git, jq and Python 3 with PyYAML. Run the clients from the consumer
repository. Both use its existing `.immutable-prd/config.yml`, profile and
`.claude/immutable/` notes, including handoffs started in the other client.

| Client | Install from a revision containing its marketplace | Invoke in a new session | Update a Git marketplace and its installed copy |
| --- | --- | --- | --- |
| Claude Code | `claude plugin marketplace add choi88andys/skills` then `claude plugin install immutable@skills` | `/immutable:init`, `/immutable:prd`, or another command above | `claude plugin marketplace update skills` then `claude plugin update immutable@skills`. Restart the session. |
| Codex CLI | `codex plugin marketplace add choi88andys/skills --ref main` then `codex plugin add immutable@skills` | `$immutable:init`, `$immutable:prd`, or select the namespaced skill in `/skills` | `codex plugin marketplace upgrade skills` then `codex plugin add immutable@skills`. Open a new session. |

For a local Codex marketplace, pass the absolute path to **the checkout** to
`codex plugin marketplace add`. After editing, run `codex plugin add immutable@skills`
again to refresh the cached package. To test in a disposable home, use the verification
command below. For Claude development, use `claude --plugin-dir "/path/to/checkout/immutable"`.

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

## Deprecated-document reads

For Markdown in a directory tree marked by `.immutable-prd/`, the protected read
paths parse YAML frontmatter. If `deprecated` is boolean true, they deliver the
frontmatter, a withholding banner and any same-directory successors. Active documents
remain readable. Both paths share the reader and the validator's frontmatter parser.

| Client | Ordinary reads | Intentional historical review |
| --- | --- | --- |
| Claude Code | The plugin's `PostToolUse` hook replaces deprecated native `Read` results, including offset reads. | Use the banner's audit command. Claude's Bash `cat` and `git show` paths also remain available. |
| Codex CLI | The enabled, trusted plugin's `PreToolUse` hook denies supported raw reads before the shell starts. Its reason gives a shell-quoted retry using the installed package. This applies in ordinary coding sessions, including before a skill is selected. | Run the banner's `read_doc.py --audit -- FILE` command for a supersede or history review. It prints the raw snapshot between historical-audit markers. Use the successor for implementation. |

### Codex shell coverage

Paths are literal absolute or relative names, including shell-quoted spaces. A file
is in scope when its Markdown path or resolved target ends in `.md` and has a
`.immutable-prd/` ancestor. The hook checks the call's working directory and
operands. A file mentioned in a message, search expression or another program's
arguments does not by itself trigger a denial.

| Shell form | What the retry delivers |
| --- | --- |
| `cat [--] FILE...` | Concatenated snapshots in operand order, with a notice for each deprecated file. |
| `sed -n [-e] 'Np' [--] FILE`, also `'N,Mp'` and `'N,$p'` | The selected lines of one active file, or the complete withholding notice even for a body-only range. Line numbers start at 1. |
| `rg [OPTIONS] PATTERN [FILE_OR_DIR...]`, also `-e PATTERN` | One expression over explicit files, recursive directories, or the current directory when omitted. Active matches carry paths. Deprecated candidates produce their notices even if there are no active matches. Mixed searches include source matches. |
| Flat commands separated by `&&`, `||`, `;`, a newline or a pipe, including a literal leading `cd [--] DIR &&` | The entire call is denied when a supported read is found. The retry runs the first such read on its own. Run any remaining steps separately. A piped `rg PATTERN` with no targets consumes stdin. |

Search options include `-n`, `-i`, `-S`, `-F`, `-w` (including combinations and
their long forms), `--hidden`, repeated `-g GLOB` / `--glob GLOB` / `--glob=GLOB`,
and `--`. Quote glob patterns. Directory discovery uses `rg --files -0` with the
same glob and hidden options and normal ignore rules. The hook only enumerates
names. The retry classifies the same Markdown snapshot that it filters or searches.
Filename enumeration, e.g. `rg --files | rg pitch`, and source-only reads pass.

Examples from a consumer repository:

```sh
cat -- 'pitches/order/old pitch.md'
sed -n '20,60p' 'pitches/order/old pitch.md'
cd 'pitches/order' && rg -ni -g '*.md' 'checkout' .
```

If denied, execute the exact command in the reason. The ordinary retry applies
the range or search to active inputs. Only an explicit historical review uses
`python3 -B "$IMMUTABLE_ROOT/scripts/read_doc.py" --audit -- "$path"`.

This check covers the listed forms with the standard utilities on PATH. Shell
expansion (variables, wildcards in file operands, substitutions), redirects,
nested shells, loops, aliases, wrappers, other utility options, custom ripgrep
configuration, and commands that change the file tree or working directory
conditionally can fall outside it. Interactive shell input, `git show`, other
programs such as `head` or Python, and other tools can still read raw files.
Trust and enable the installed hook in Codex (`/hooks`). Disabled, untrusted,
failed or timed-out hooks can leave reads unprotected. [Codex hook reference](https://developers.openai.com/codex/hooks#tool-coverage)

Both clients need Python with PyYAML. The Codex search path also needs ripgrep.
The Claude hook additionally uses jq and Bash. Missing PyYAML leaves Claude Read
open with a diagnostic. The protected reader exits before releasing an in-scope
body when PyYAML is missing. `IMMUTABLE_DEPRECATED_GUARD_DISABLE=1` disables the
Claude hook. `IMMUTABLE_DEPRECATED_GUARD_LOG=<path>` records reader decisions.

## Maintenance

Edit each procedure once, in `immutable/<name>/SKILL.md`. Runtime tool mappings,
interview fallback and asset resolution live in [RUNTIME.md](RUNTIME.md).
The physical skill path locates the bundled scripts, templates and catalogs,
including when the developer's entry point is a symlink.

The canonical version, skill list and plugin description live in
`immutable/.claude-plugin/plugin.json`. Run the following from the checkout after
editing its metadata or adding a skill:

```sh
python3 immutable/scripts/sync_manifests.py
bash immutable/scripts/plugin_manifest.test.sh
```

Commit the generated Claude marketplace, Codex compatibility manifest and Codex
marketplace together. The compatibility manifest accepts explicit skill roots, so
each client loads the existing directories. The manifest test detects stale output
and checks English/Korean string-key parity. A new bundled profile field still
requires a schema bump in both default profiles. [Official packaging guide](https://developers.openai.com/codex/plugins/build)

## Verification

From the checkout, these checks load the package in both clients and exercise
consumer-shaped repositories. The Codex script creates a temporary `CODEX_HOME`.
Its default discovery and asset checks run without a model. Its optional model
test uses `CODEX_API_KEY` from the environment and accepts `--model <name>`.

```sh
claude --plugin-dir "$PWD/immutable" plugin details immutable
python3 immutable/scripts/codex_plugin.test.py
bash immutable/scripts/validate_docs.test.sh
bash immutable/scripts/deprecated_read_guard.test.sh --e2e
python3 immutable/scripts/codex_plugin.test.py --e2e
```

The two end-to-end guard tests inspect **client-delivered tool results** for the
banner, the active document's token and the explicit raw audit's token. Unit
tests separately check Claude's JSON shape, folded and split successors, YAML
booleans, CRLF and the reader's behavior without PyYAML.

On 2026-11-18, Claude Code 2.1.327 (`--plugin-dir`) and Codex CLI 0.169.1
(isolated marketplace install) each exposed nine skills. An isolated Claude marketplace
install also loaded all nine and retained the shared assets in its cache. In separate copies
of the English single-repo starter, a synthetic repository-wide timestamp ADR
was refused when the decision and trade-offs were missing. Each client generated one ADR
after the fixture owner resolved the three perspectives' questions and approved the write.
Both outputs passed `validate_docs.py --type adr --strict-body` from the consumer
directory. The existing gate named “90%” uses the bundled thresholds of seven
of eight pitch criteria and five of six ADR criteria. The shell regression suites cover requirement contracts and supersede
rules on additional fixtures. Desktop, IDE and hosted clients were not exercised.

## Requirement contract (opt-in, v0.11.0)

A pitch can be authored against a tracker ticket whose designated sections
**bind** it — in the pilot, a GitHub Epic's acceptance and QA-checklist
sections. Declare it once in `.immutable-prd/config.yml`:

```yaml
requirement_contract:
  enforcement: optional        # optional | required
  tracker: github
  repo: my-org/task-tracker
  since: 2026-09-08            # under required, pitches dated before this are exempt
  response_window: "2영업일"    # rendered into correction requests; the plugin keeps no clock
  # fetch_command: "python3 tools/ticket.py {id}"   # any command printing the ticket-input JSON
```

What then happens, and what deliberately does not:

- **`/immutable:prd`** fetches the ticket through `scripts/requirement_contract.py`,
  lints the binding sentences' wording (`lint`, v0.13+ — deterministic, the
  ticket text alone), judges every binding item (followed, or one of the
  admissible deviations: not implementable / self-contradiction / conflict
  with a settled requirement, and since v0.13 not concrete / delegated
  authority — 「필요 시」, "as the pitch decides", a design as the oracle,
  pinned or not since v0.16), cross-checks the designs the ticket pins by
  version-id against what the binding items state (v0.16+,
  `scripts/figma_pin_texts.py`), hands the author a correction request to post, and writes the
  pitch against the corrected text. The pitch records the ticket's identity and **version
  coordinate** in `references.tickets[]` — never its text; the tracker keeps
  the body at that version.
- **A disagreement is a section, not a blocker.** Each deviation becomes an
  entry with original, correction, reason and a *provisional* outcome. The
  validator (`--strict-body`) refuses a provisional outcome, so the pitch's
  pull request stays open until the author rewrites it as *agreed* or
  *deadline passed* on the PR branch. The section stays afterwards: it tells a
  later reader the difference from the ticket was deliberate.
- **Accounting is a ledger over the set.** Each pitch declares in its ticket
  record which binding groups or items it reflects (`covers`) or reflects in
  substance while the literal lives elsewhere (`delegates`, e.g. copy → Figma);
  `requirement_contract.py coverage` reconciles every pitch citing the ticket
  against the live items, so no pitch enumerates its siblings.
- **Wording lint** — `requirement_contract.py lint --profile <profile> --id <id> …`
  exits 1 when a binding item's wording hits a `block` rule from the profile's
  `wording_rules`; the same rules judge a pitch's correction bullets in the
  validator. Recall only — precision is the skill's context check and the
  human's verdict. A rule may carry `since` (v0.16+): it then judges only
  tickets created on or after that day, and every rule it withheld is
  reported. `lint --from-body <file>` lints a local draft or the ticket
  template.
- **Merge gate** — `requirement_contract.py gate --mode off|warn|on …` (v0.15+):
  every `block` hit on a ticket an active pitch cites must be contested by
  a disagreement entry or acknowledged, hit by hit, in the repo's
  `.immutable-prd/contract-acknowledgements.yml`; an acknowledgement whose
  hit is gone is stale and fails the gate. The on/off switch is the repo's.
- **Drift** — `requirement_contract.py drift --id <id> --profile <profile>
  --ledger <ledger> … <pitches>` (v0.19+) re-reads the ticket and judges every
  active pitch citing it against the version that pitch recorded. A pitch
  fails only for an edit to an item it owns: any edit to an item it `covers`,
  an edit of substance to one it `delegates` (a quoted literal swapped is
  reported, not failed); an item it does not claim is `coverage`'s business.
  When an owned item was reworded but kept its meaning, a `meaning_unchanged`
  entry in the ledger says so instead of a new version, and goes stale when
  the item moves again. The single-version form (`--version <recorded>`, no
  pitch files) is unchanged. Where it runs — a spec repo's PR check, a
  tracker-side bot on ticket edits — is the consuming repo's decision; the
  plugin ships the parser and the exit codes.
- **Not in the plugin**: any clock (business-day deadlines live with the
  tracker), any write to the tracker, and any coverage check against sources
  the ticket does not name — a topic the ticket never raised is not a defect.

Vocabulary (which headings bind, the category labels, the outcome tokens)
lives in the profile; the built-in adapter needs the `gh` CLI, a custom one
needs whatever it needs. Full contract: [`SCHEMA.md`](SCHEMA.md), "Requirement
contract".

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

## What v0.19.0 changed (vs. v0.18.0)

- Ticket drift fails only the pitch that owns what moved. `requirement_contract.py
  drift` takes the pitch files and judges each active citing pitch against its
  own recorded version, through the same claim resolver as `coverage`: a copy
  edit to an item a pitch delegated to the design passes, the same item
  reworded fails its delegating pitch, and a pitch that owns nothing that moved
  passes. A `meaning_unchanged` ledger entry acknowledges an owned edit that
  kept its meaning, so a reworded sentence no longer costs a new version of
  every citing pitch. `/immutable:prd` §1.5.2 settles those edits while the
  author has the ticket open. `drift --version` is unchanged; consumers switch
  their CI call to the pitch-file form. Details: [`CHANGELOG.md`](CHANGELOG.md).

## What v0.18.0 changed (vs. v0.17.0)

- Input contract: a pitch declares every value the user enters in a
  `## 입력 항목` / `## Inputs` table — how it is entered, accepted values, what
  happens on an invalid value. `/immutable:prd` asks the four cells per value
  (Branch C2) and refuses a pitch that leaves one undefined (gate 8/7);
  `validate_docs.py --strict-body` polices a present table and, from the
  section's `since` on, fails a pitch whose normative lines speak of an input
  with no table — earlier pitches only warn (profile_schema 9). `changes`
  section names holding " / " now resolve. **Run `/immutable:migrate`.**
  Details: [`CHANGELOG.md`](CHANGELOG.md).

## What v0.17.0 changed (vs. v0.16.0)

- Pitch granularity: a pitch is one user-facing feature area, each rule lives
  in one active pitch, length is no reason to split. `/immutable:prd` routes a
  change to the pitch that owns the rule (no `new` lean); the count caps
  (`max_items`, `anti_monolith`, `concern_scope`) are retired (profile_schema 8)
  for one byte ceiling, `max_bytes`. New versions are a copy plus the declared
  `changes`, checked by `validate_docs.py --supersede-diff`; `supersedes` takes
  a list (a fold); a prose override of another pitch fails `--strict-body`.
  **Run `/immutable:migrate`.** Details: [`CHANGELOG.md`](CHANGELOG.md).

## What v0.16.0 changed (vs. v0.15.2)

- `design_oracle`: a binding item that makes a design the acceptance oracle
  blocks even when pinned — on tickets created from its `since` date on. Rules
  gain an optional `since` (profile_schema 7), tickets a `created_at`, rule
  keys turn strict, `lint` gains `--from-body`, and `/immutable:prd` cross-checks
  pinned designs. **Bump CI pins before adopting a dated rule.** Details:
  [`CHANGELOG.md`](CHANGELOG.md).

## What v0.15.0 changed (vs. v0.14.0)

- `requirement_contract.py gate` and the acknowledgement ledger — the
  spec repo's merge gate, ready to switch on. Details: [`CHANGELOG.md`](CHANGELOG.md).

## What v0.13.0 changed (vs. v0.12.1)

- `requirement_contract.py lint` and two wording categories (`non_concrete`,
  `delegated_authority`); one `wording_rules` list (profile_schema 5) read by
  `lint`, `/immutable:prd` Stage 1.6 and the validator's correction check.
  Details and the migration note: [`CHANGELOG.md`](CHANGELOG.md).

## What v0.11.0 changed (vs. v0.10.1)

- The opt-in **requirement contract** above: `scripts/requirement_contract.py`
  (parse / fetch / drift, pluggable adapters), `/immutable:prd` Stages 1.5.1
  and 1.6, validator invariant 9 (the disagreement merge gate), profile
  schema 3, and the `requirement_contract:` config block.
- A repo that does not declare the block sees no change anywhere.

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
