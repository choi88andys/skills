# Changelog — immutable plugin

All notable changes to the `immutable` plugin are documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the plugin follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Version is canonically declared in `.claude-plugin/plugin.json`.

## [0.9.0] — 2026-07-15

Adds a date cutoff to `--strict-body`, so a repo with legacy documents can start enforcing structure on new ones without breaking its own append-only rule.

`--strict-body` scans **every** pitch and ADR. That is correct for a fresh repo and a trap for an established one: the v0.5.3 pitch user-stories structure requirement, and any team's profile that adds a required ADR section, are retroactive under `--strict-body` — every document authored before the rule fails it at once. Measured across the in-house repos: turning `--strict-body` on lights up 4 pitches in one spec repo, 2 in another, and 3 ADRs in an app repo. Not one of those is missing content. The ADRs carry all five required sections under English headings (`## Context`) where the Korean profile expects the bilingual form (`## 맥락 (Context)`); the pitches carry their user stories in the pre-v0.5.3 flat layout rather than the `###` per-story grouping. They are legacy *format*, not legacy *substance* — and they are append-only, so the honest way to make them pass is to supersede each one, which is absurd overhead for a heading-label mismatch.

The cutoff turns retroactive enforcement into forward enforcement. `--strict-since 2026-07-01` (or `strict_body_since:` in `.immutable-prd/config.yml`) checks only files whose filename date is on or after it; everything older is grandfathered *by exemption*, untouched, no append-only violation. This is the mechanism that was missing when the earlier design conversation reached "either break append-only to normalize the legacy, or grandfather it" — grandfathering is now a first-class, per-repo setting rather than a manual carve-out.

The design deliberately avoids a git-diff / base-SHA scope (the other obvious way to mean "only new docs"). Diff-scoping is fragile exactly where it must not be: the base is ambiguous on a first commit, a force-push, or a direct-to-main push, and it resolves differently under `actions/checkout` than it does locally — a validator that passed on your machine and failed in CI for reasons neither of you can see. The filename date is already mandated by the naming invariant, is present on every valid file, and compares identically everywhere. A cutoff has no external-state dependency at all, which is why its behaviour could be pinned down by an exhaustive test rather than argued about.

### Added

- **`--strict-since YYYY-MM-DD` flag and the `strict_body_since` config field** for `scripts/validate_docs.py`. With `--strict-body`, body-level checks (missing required sections; the v0.5.3+ user-stories structure check) apply only to files dated on or after the cutoff. The CLI flag overrides the config field; unset, behaviour is exactly as before — every file is checked. Backward-compatible: no schema bump, no migration, and a repo that sets neither sees no change.
- **`immutable/scripts/validate_docs_strict_since.test.sh`** — an 8-case regression test, run with `bash immutable/scripts/validate_docs_strict_since.test.sh` (needs only python3 + PyYAML, no git). It builds a throwaway repo whose ADRs deliberately fail `--strict-body` under the real bundled `default-ko` profile, then asserts each contract that makes the cutoff trustworthy: no cutoff checks everything (backward compatible); a cutoff between two files exempts the older and still catches the newer; the boundary is inclusive (a file dated exactly on the cutoff is checked); a cutoff past every file exits clean and says how many it exempted; the config field scopes identically to the flag; and — the cases that matter most for a gate — an impossible date (`2026-13-01`) and a non-date both **die loudly and check nothing**, rather than silently falling back to checking everything or nothing.

### Changed

- **`scripts/validate_docs.py`** — new `resolve_strict_since()` (CLI-over-config precedence, fatal on a malformed cutoff) and `strict_body_in_scope()` (filename-date vs cutoff, inclusive, fail-closed on an unparseable name). The exemption count is written to stderr whenever a cutoff is active, so the scoping is observable in CI logs and never silent. Passing `--strict-since` without `--strict-body` warns that it has no effect rather than doing nothing quietly.
- **`immutable/SCHEMA.md`** — the strict-body section documents the cutoff, its inclusive boundary, the fail-closed and fail-loud behaviours, and why the scope is by filename date rather than git diff.

### Backward compatibility

- **No schema, config, or interface change to anything that already ran.** The new config key is optional and defaults to absent; the new flag defaults to absent; with neither set, `validate_docs.py` behaves byte-for-byte as it did in 0.8.0. The existing `validate_docs.test.sh` (spec_repo_path resolution) stays green.
- **The starter workflows still pin `immutable--v0.8.0`.** They are unchanged by this release; a repo wanting the cutoff bumps `IMMUTABLE_REF` deliberately, or picks it up when a future release re-pins the starters. Nothing auto-changes underneath a repo that did not ask.

## [0.8.0] — 2026-07-14

The plugin has bundled a 31.7 KB validator since v0.3 and never once run it. No skill invokes `scripts/validate_docs.py`; no hook ships; no starter carried CI. It executed only when a human remembered to type it, and for months nobody did — while `SCHEMA.md` told readers the invariants were "checked at generation time by the `/immutable:adr` skill, **and by CI via `scripts/validate_docs.py`**". That sentence was false, and verifiable as false in thirty seconds by anyone who looked. Run for the first time against the five in-house repos that adopted this plugin, the validator found four clean and one — an app repo — carrying two genuine broken pitch references that had been sitting in a merged ADR for thirty-five days.

This release makes the plugin ship the gate it was already claiming to have. Every starter now carries `.github/workflows/validate-docs.yml`, so a repo bootstrapped by `/immutable:init` is validated on every push and pull request without anyone opting in.

CI is the layer, deliberately, and neither of the two cheaper alternatives is a gate. A skill-side call is not one: `/immutable:prd`'s `allowed-tools` include `Write` and `Edit`, so the skill can author a pitch and simply never invoke the validator, and nothing would notice — structurally the same defect as the `$1`-substitution bug that scored a commit-review gate at zero for three and a half months, a gate that looked installed and silently never fired. A pre-commit hook is not one either: `.githooks/*` is tracked, but `core.hooksPath` lives in `.git/config` and does not survive a clone, so a fresh clone has no hooks and says nothing about it — and `--no-verify` skips what remains. CI is the only layer a contributor cannot silently skip.

The validator is **fetched at a pinned tag, never vendored**, and the workflow checks out the whole plugin rather than the one script. That second detail is load-bearing and was nearly missed. `validate_docs.py` resolves its bundled default profile *relative to its own location* — `<plugin>/examples/_profiles/default-<lang>.yml`, a sibling of `scripts/` — and when that lookup misses it falls through to hardcoded defaults **silently**, with no warning on any stream. A copy of the script sitting alone in `/tmp` therefore still runs, still exits 0 or 1, and quietly checks less: measured against the app repo above, the in-tree run reports **17** violations under `--strict-body` and the lone-file run reports **2**. A repo whose only defects were missing ADR sections would have gone green. Fetching the script by raw URL — the obvious three-line implementation — would have installed, inside the new CI gate, a quieter copy of the exact failure this release exists to end. Vendoring is the same trap with a longer fuse: one in-house spec repo copied the validator and its copy has since drifted to 33,076 bytes against the plugin's 31,709, with nobody able to say which is newer.

### Added

- **`.github/workflows/validate-docs.yml` in all six starters.** Runs on `push` and `pull_request`, checks out `choi88andys/skills` at a pinned tag (`IMMUTABLE_REF`, default `immutable--v0.8.0`), installs PyYAML, and runs `validate_docs.py` over the repo. Upgrading the gate is a deliberate act — bump the tag — so the check cannot change underneath a team that did not ask for it. `spec-*` and `single-*` need no configuration at all: the validator auto-detects `.immutable-prd/config.yml` by walking up. Verified end-to-end against the real in-house spec repo (clean → exit 0), and against injected defects (a malformed filename and a supersede edge pointing at a still-active predecessor → exit 1 each), then back to clean.
- **A two-checkout layout for `app-*`, so an app repo's ADR→pitch references are actually checked.** This is the hard case: an app repo's ADRs reference pitches held in a *sibling spec repo*, and `actions/checkout` cannot write above `$GITHUB_WORKSPACE`, so `../<spec>` has nowhere to resolve to in a naive single-checkout job. The workflow instead lays both repos out as siblings *inside* the workspace — `app/` and `<spec>/` — which is exactly the shape `resolve_pitches_for_reference` already resolves. Verified against the real app + spec repo pair: the job reproduces the two known reference violations, resolving them through `$GITHUB_WORKSPACE/<spec>/pitches`. Because `config.yml` records only a filesystem path (`../my-spec`) and not GitHub coordinates, the workflow needs `SPEC_REPO` (owner/name) set at the top of the file, plus a `SPEC_REPO_TOKEN` secret when the spec repo is private — the default `GITHUB_TOKEN` is scoped to the current repo alone. **Unconfigured, the job fails loudly and never passes having checked less**: an unset `SPEC_REPO`, an unset or placeholder `spec_repo_path`, an absolute path, and a path more than one level up each produce a distinct `::error::` and a red run. This is faithful to the validator, which already refuses rather than skips when it cannot see the spec repo.

### Fixed

- **`SCHEMA.md` claimed CI checked the invariants when nothing ran it.** Two claims: "Suitable for pre-commit hooks and CI" (aspirational — no hook and no CI shipped) and, the outright false one, "Checked at generation time by the `/immutable:adr` skill, and by CI via `scripts/validate_docs.py`". Both now describe what actually ships, including the caveat that a red run **reports** rather than **blocks** unless the consuming repo adds a branch-protection rule making the check required — a guarantee the plugin cannot ship on a user's behalf and must not imply.
- **`SCHEMA.md` invariant 2 claimed "No cycles".** `validate_docs.py`'s own docstring lists cycle detection on supersede chains under "Not covered (deferred)". The invariant is per-edge; the doc now says so instead of advertising a graph check that does not exist.
- **`init/SKILL.md`'s starter file-count table had been wrong since v0.6.0.** It read 5 / 3 / 7. The v0.7.6 consistency sweep found and fixed the *same* table in the root `README.md` (5/3/7 → 6/4/8, undercounting the `.gitignore` added in v0.6.0) and did not notice this second copy of it. Both tables now read 7 / 5 / 9 and are correct.

### Changed

- **`immutable/strings/strings.en.yml` and `strings.ko.yml`** — the four `init.stage7.handoff_*` templates now name the CI workflow. The two `two-repo-app` variants carry it as a numbered *next step*, because an app repo's gate does not work until `SPEC_REPO` is set and a user who does not know that will meet an unexplained red build and delete the workflow. `spec-*` and `single-*` carry it as a reference line — they need no setup. No new keys: the existing templates were extended, so `en`/`ko` parity (200/200) holds by construction. `strings.ja.yml` is untouched, as designed — it is a deliberate scaffold that falls back to English wholesale.
- **Root `README.md`** — starter table corrected to 7 / 5 / 9, plus a paragraph describing what the shipped workflow does and what `app-*` requires.

### Backward compatibility

- **No schema, config, or interface change, and `validate_docs.py` itself is untouched.** No new config key, no migration, no profile-schema bump. The validator this release wires up is byte-for-byte the one that shipped in v0.7.8.
- **Existing repos are not retrofitted, and this is the release's real limitation.** `/immutable:init` refuses to run on a repo that already has `.immutable-prd/config.yml` (Stage 1.3, "never proceed with already-initialized repos"), so the five in-house repos already on this plugin — including the one carrying the two live violations — do **not** get the gate from upgrading. Adopting it there means copying `.github/workflows/validate-docs.yml` out of the matching starter by hand; the file is self-contained and needs no other change. New repos bootstrapped by `/immutable:init` get it automatically.
- **`/immutable:init` never overwrites.** A repo that already has a `.github/workflows/validate-docs.yml` keeps its own; the starter's copy is reported as skipped.
- **The pinned tag must exist for the workflow to run.** A starter copied out of `develop` before `immutable--v0.8.0` is tagged fails at the fetch step with an unresolvable ref — loudly, at the first step, not silently at the last.

## [0.7.8] — 2026-07-14

Fixes a path-resolution defect that made `scripts/validate_docs.py` refuse every commit issued from a linked git worktree whose directory is not a sibling of the main checkout — including the nested layout (`<parent>/<repo>-worktrees/cycle-N/pod-M`) that parallel-dispatch harnesses create. The commit failed with one `references.pitches file not found` violation per ADR, raised against ADRs the diff never touched, so the repo looked corrupt when nothing was actually wrong with it. Every one of those violations was pure path arithmetic.

`.immutable-prd/config.yml` is a tracked file, so it exists in every linked worktree too. Walk-up therefore finds it at the *worktree* root, `repo_root` becomes the worktree, and a relative `spec_repo_path: ../<spec-repo>` is resolved from there. That is correct only when the worktree happens to sit beside the main checkout, because only then does `../` land in the same parent directory. A relative `spec_repo_path` means "the spec repo sits next to my REPO" — and in a linked worktree, "my repo" is the MAIN checkout, not the one checkout of it you are standing in. Resolved from a nested worktree, `../` is the cycle directory and the spec repo is two levels away, so every pitch reference misses.

The workaround this cost people was a hand-made symlink, or `--no-verify` — which also skips lint, codegen and the secret scan, a far larger hole than the one it works around.

### Fixed

- **`scripts/validate_docs.py` refused every commit made from a nested linked worktree.** A relative `spec_repo_path` is now tried against the current checkout FIRST — so every layout that already worked keeps working unchanged, including a spec repo genuinely parked beside the worktree — and only then against the main checkout, discovered via `git worktree list --porcelain`. An absolute `spec_repo_path` is untouched by any of this.
- **An unresolvable spec repo now reports itself once, accurately.** Previously the validator globbed a directory that was not there and emitted one bogus `references.pitches file not found` per ADR — N violations, every one of them pointing away from the actual problem. It now emits a single violation naming the config keys involved and every path it tried.
- **`scripts/sdd_mode_detect.sh` silently failed to pair the spec repo from a nested worktree.** The same relative-path arithmetic, with a quieter symptom: `IMMUTABLE_PRD_SPEC_CONFIG` came back empty, so a skill sourcing it fell through to its no-spec-repo branch instead of reporting anything. Both of the script's `spec_repo_path` resolution sites — the app-role branch and the reverse-config scan — now share one helper carrying the same worktree-first, then-main-checkout order.

### Added

- **`immutable/scripts/validate_docs.test.sh`** — the plugin's first test. It builds a throwaway two-repo SDD workspace under `mktemp -d`, `git worktree add`s a nested and a sibling worktree, and asserts the four distinct outcomes of `spec_repo_path` resolution: the validator exits clean from the main checkout, from a sibling worktree and from a nested one, and reports an unresolvable spec repo as **exactly one** violation rather than one per ADR. Verified to fail against the pre-0.7.8 validator on precisely the two cases it is meant to catch, and to pass against this one. Run it with `bash immutable/scripts/validate_docs.test.sh`; it needs only bash, git and PyYAML — the set `validate_docs.py` already assumes — and is deliberately not wired into CI. This defect was rediscovered three times and fixed zero times because nothing in the repo could catch it; the sibling and main-checkout cases are what keep the fix additive under future edits.

### Changed

- **`immutable/scripts/validate_docs.py`** — new `main_worktree_root()` helper. `resolve_pitches_for_reference()` now returns `(pitches_root, error)` so that an unresolvable spec repo is reported once by the caller, rather than N times by the per-ADR existence check. The helper prefers `git worktree list --porcelain` over `git rev-parse --git-common-dir`: it lists the main worktree first and always as an absolute path, whereas `--git-common-dir` prints a *relative* `.git` when run from the main checkout, and its parent is not the checkout root at all under `git init --separate-git-dir` or inside a submodule.
- **`immutable/scripts/sdd_mode_detect.sh`** — new `_sdd_main_worktree_root` and `_sdd_resolve_spec_root` helpers, used by both the app-role branch and the reverse-config scan. A candidate spec root now counts only when it actually holds `.immutable-prd/config.yml`, which is the question both call sites were already asking downstream.

### Backward compatibility

- **No schema, config or interface change.** No new config key and no migration: every repo already in the wild with a relative `spec_repo_path` keeps working with no edit required of it.
- **Resolution is purely additive.** The pre-existing checkout-relative candidate is tried first and kept whenever it resolves, so no layout that works today can change behaviour — not the sibling-worktree layout, and not a spec repo deliberately placed beside a worktree.
- **Degenerate cases keep today's behaviour exactly.** Not a git repo, git not installed, or a plain non-worktree checkout: the main-checkout candidate is simply never added, and resolution is what it is today.
- **One intentional behaviour change.** A repo whose `spec_repo_path` resolves nowhere now fails with one accurate violation; it previously failed with N bogus ones, or — with zero ADRs to check — passed silently. Only an already-broken configuration can reach this path; a working one cannot.

## [0.7.7] — 2026-07-14

Fixes a silent config-parsing defect shared by four skill bodies. All four read `.immutable-prd/config.yml` with the same idiom — `grep '^<key>:' "$CFG" | head -1 | awk '{print <field>}'` — but a `SKILL.md` cannot hold an awk field reference. Claude Code substitutes a dollar sign followed by a digit with the invocation's positional arguments *before bash ever runs*, fenced code blocks included, and it does so even when no arguments are passed. On the bare call the field reference degrades to the empty string, leaving `awk '{print }'` — which is not a parse error but valid awk: `print` with no argument prints the whole record. Every one of these seven reads therefore returned `<key>: <value>`, the entire line with the key still glued on, instead of `<value>`. A `${VAR:-default}` fallback one line below each read masked the defect in exactly the repos that left the key unset, which is why it survived this long.

### Fixed

- **`/immutable:design` and `/immutable:plan-review-ceo` found no pitches, ever.** `PITCHES_REL` resolved to the literal `pitches_path: spec/pitches/`, so `PITCHES_DIR` addressed a directory that cannot exist and both skills fell through to their `no_pitches_found` branch on every bare invocation in any repo whose config declares `pitches_path` — which includes the bundled `single-repo` starter. A repo leaving the key unset hit the fallback and was unaffected.
- **`/immutable:init` never discovered a sibling spec repo.** `_mode` came back as `repo_mode: two-repo-spec`, which matches neither arm of the `case` immediately below it, so the adjacent-repo scan silently found nothing.
- **`/immutable:ship` wrote malformed pitch and ADR links into the PR body.** Both the pitch path (read from the design note's `Pitch:` line) and `adr_path` came back as whole lines.

### Changed

- **`immutable/design/SKILL.md`, `immutable/init/SKILL.md`, `immutable/plan-review-ceo/SKILL.md`, `immutable/ship/SKILL.md`** — all seven affected reads replaced with a `sed` capture, `sed -n 's/^<key>:[[:space:]]*\([^[:space:]]*\).*/\1/p'`. A sed backreference is not a shell positional parameter, so the harness leaves it intact. Output was verified identical to the awk the code meant to run across six config shapes: plain, extra whitespace, trailing comment, and `ship`'s refactor-mode sentinel `Pitch: (none — internal refactor)`, where the capture still yields `(none` — precisely what the downstream refactor-mode check keys on.

### Backward compatibility

- **No schema, config, or interface change.** Same keys, same defaults, same fallbacks — only the parse of an already-supported config is corrected. Config schema v3 and profile schema 2 are untouched; no migration required.
- **Behavior can only move from broken toward correct.** Repos that left `pitches_path` / `adr_path` unset were already resolving to the default via the fallback and see no change at all.

## [0.7.6] — 2026-07-08

Cross-file consistency sweep across the plugin's own source (not end-user pitch/ADR artifacts) — an audited pass over frontmatter descriptions, `pipeline.yaml`, `README.md` (root + plugin), `SCHEMA.md`, the strings catalog, and cross-skill shared contracts, catching several more instances of the same drift class fixed once already in v0.7.5: docs and manifests describing a skill's behavior in a way that has since fallen out of sync with what the skill body actually does. Nine confirmed fixes across 8 files; every fix below was independently re-verified against the current on-disk state of both sides of the claimed inconsistency before being applied.

### Fixed

- **`pipeline.yaml` under-declared `plan-review-eng`'s ceo-grounded dependencies.** The `ceo-grounded` mode's manifest entry listed only `plan-review-ceo` (`enforcement: refuse`), but the skill's own frontmatter description states the design handoff note is an expected input "in BOTH modes" (warn-on-absence) — plan-review-eng independently re-checks it in its own Phase 0.2 even when CEO already prompted the same warn upstream. Introduced a "nested map form" (mode + per-dependency-keyed) in the manifest's dependency-list schema, for the case where a single mode's dependencies span different enforcement levels, and used it to add the missing `design: warn-3way` entry alongside `plan-review-ceo: refuse`.
- **`SCHEMA.md`'s canonical profile-schema template was stuck at `profile_schema: 1`** while both bundled default profiles (`default-en.yml`, `default-ko.yml`) have declared `profile_schema: 2` since v0.5.6, and the template was missing every field that bump added: `sections[].max_items` / `structure` (user-stories anti-monolith cap), a top-level `vague_words:` block (Stage 3 vague-word detection, consumed by `prd/SKILL.md`), a top-level `anti_monolith:` block, and an `adr.anti_monolith:` block. All four are genuinely read by skill bodies today; the schema doc's example had simply never caught up. Added all four plus the version bump.
- **`adr/SKILL.md` hardcoded the ADR reference-policy exception to `domain: _global`** in six places (profile-fields table, Stage 1.4, Stage 3 Branch F, Stage 5 gate criterion 6, frontmatter template comment, Hard Prohibition 5), while `SCHEMA.md` invariant 5 and `scripts/validate_docs.py` already generalize the exception to "domain is declared `adr_only` in `profile.domain_allowlist.reserved_domains`" (bundled defaults mark only `_global` this way, but teams may add others). Generalized all six mentions to match, and added the missing `adr.anti_monolith.tiers` row to the profile-fields-consumed table.
- **`strings.ko.yml` was missing both `prc.phase4.auto_advanced` and `pre.phase4.auto_advanced`** — the verdict-auto-advance banners added in v0.7.4, present in `strings.en.yml` and referenced by `plan-review-ceo/SKILL.md` and `plan-review-eng/SKILL.md` respectively. Korean-language teams (the `team_language` default) hitting the `live`-autonomy auto-advance path would have silently fallen back to the English banner via the strings-catalog fallback chain. Added both keys with Korean translations matching the English original's meaning.
- **`design/SKILL.md` and `plan-review-ceo/SKILL.md` descriptions didn't mention the pitch-less "refactor mode" path** that both skills already implement in their bodies (`plan-review-ceo/SKILL.md` lines 73/211/503/512) — an agent reasoning only from frontmatter would have concluded a pitch is unconditionally required. Extended both descriptions to name the exception.
- **Root `README.md` had four stale factual claims**: the "Existing v0.5.x repos... unchanged" sentence was written for the v0.6.0 upgrade and never updated for later releases that did change `/immutable:prd`'s interview and `/immutable:adr`'s description; `/immutable:prd`'s gate was still described as "7 criteria" (bumped to 8 in v0.5.6); `/immutable:plan-review-eng` was described in single-mode prose though it has run in two modes since v0.7.2; and the bundled-starter file-count table (5/3/7) undercounted by one each (6/4/8) since the `.gitignore` added to every starter in v0.6.0.
- **`immutable/README.md`'s skill table still said "3 personas, 7-criterion gate"** for `/immutable:prd` — the same stale gate-criteria count as above.

### Changed

- **`immutable/pipeline.yaml`** — new "nested map form" documented in the dependency-list-semantics comment block; `plan-review-eng.ceo-grounded` restructured to use it.
- **`immutable/SCHEMA.md`** — canonical profile-schema template bumped to `profile_schema: 2` with the four new fields/blocks described above.
- **`immutable/adr/SKILL.md`** — six reference-policy mentions generalized from hardcoded `_global` to the profile-driven `adr_only` mechanism; profile-fields table gained an `adr.anti_monolith` row.
- **`immutable/strings/strings.ko.yml`** — two new keys (`prc.phase4.auto_advanced`, `pre.phase4.auto_advanced`).
- **`immutable/design/SKILL.md`, `immutable/plan-review-ceo/SKILL.md`** — frontmatter descriptions each gain a refactor-mode clause.
- **`README.md`, `immutable/README.md`** — four and one stale claims corrected respectively.

### Backward compatibility

- **No skill-body logic changed.** Every fix in this release corrects a description, comment, doc, manifest entry, or missing catalog string to match behavior the skill bodies already had — no `/immutable:*` skill behaves differently after this release.
- **`pipeline.yaml`'s new nested-map dependency form is additive and used in exactly one entry** (`plan-review-eng.ceo-grounded`); every other entry keeps its existing flat or mode-keyed shape unchanged.
- **No migration required.** v0.7.6 is a docs + manifest + strings-catalog release. The bundled profiles already declared `profile_schema: 2`; this release only brings `SCHEMA.md`'s documentation example in line with what was already shipped.

## [0.7.5] — 2026-06-20

Fixes the `adr-placement` misinference at two layers prior releases left open. (1) `/immutable:adr`'s frontmatter description carried no flow-position anchor, so a session sketching the whole pipeline UPFRONT (before running `/immutable:prd`) inferred `prd → adr` from the description alone — a case the v0.7.3 prd-handoff anchor does not reach, since that anchor only fires once a session reaches `/immutable:prd` Stage 6. (2) `pipeline.yaml` declared `dependencies.adr.enforcement: refuse`, but per the manifest's own schema `refuse` means the skill body aborts — and `/immutable:adr` has no such precondition (it is standalone-callable by design). The mislabel means any orchestrator honoring `dependencies` at `refuse`-level would hard-block standalone ADR authoring — re-creating at the orchestration layer the standalone-breaking refusal that v0.7.3 deliberately kept OUT of the skill body.

### Fixed

- **`/immutable:adr` description had no flow-position anchor.** Added one clause: in the orchestrated flow ADRs are authored reactively (only after `/immutable:plan-review-eng` Phase 3 surfaces an ADR-authoring trigger, never upfront after the pitch), while remaining standalone-callable for out-of-flow decisions. The description is what an agent reads FIRST when modeling the flow; every other skill touching ADR-ordering was already anchored (plan-review descriptions in #9 / v0.6.5, prd Stage 6 handoff in v0.7.3) — adr's own description was the remaining gap, and the only one covering the upfront whole-flow-planning case (the prd Stage 6 anchor fires too late for a session that pre-plans the entire chain).
- **`pipeline.yaml dependencies.adr.enforcement: refuse` misdescribed a standalone-callable skill.** This manifest's own schema documents `enforcement: refuse` as "the skill body aborts on absence of the dependency", but `/immutable:adr` carries no plan-review precondition — it is standalone-callable by design (the init-handoff peer entry point and the plan-review-eng standalone quick-ADR path both reach it without a prior review). So the entry was internally false: any orchestrator that honors the `dependencies` map at `refuse`-level would abort a standalone `/immutable:adr` dispatch whenever the `{slug}-eng.md` review note was absent — contradicting the intentional standalone path documented in v0.7.3 "Out of scope (intentional)". Moved `adr` from `dependencies` to `soft_dependencies` (`[plan-review-eng]`): a phase absent from `dependencies` resolves to `enforcement: none`, so no orchestrator hard-blocks it, while the canonical in-flow ordering remains carried by `exit_verdicts.plan-review-eng` `Next:`-directive routing (no signal lost).

### Changed

- **`immutable/adr/SKILL.md`** — frontmatter description gains one reactive/standalone clause.
- **`immutable/pipeline.yaml`** — `adr` moved from `dependencies` (was `enforcement: refuse`) to `soft_dependencies`, with a block comment recording the advisory-only / must-not-hard-block semantics and why it moved.
- **`immutable/pipeline.yaml` header + `immutable/README.md`** — removed orchestrator-implementation-specific references (a named local orchestrator skill, introduced in v0.7.2) from the manifest PURPOSE/CONSUMERS comments, the README "Pipeline manifest" section, and the v0.7.2 changelog entry; the manifest is orchestrator-agnostic, so the consumer is now described generically (a dispatcher / brief author). Also corrected a stale `hard_dependencies` reference in the README to `dependencies` (the actual field name).

### Backward compatibility

- **No skill-body change.** `/immutable:adr` never carried a plan-review precondition and still doesn't; v0.7.5 only corrects how the manifest *describes* it. Direct `/immutable:adr` invocation was always unaffected — only an orchestrator that consumed the manifest's `refuse`-level `dependencies` entry would have wrongly blocked a standalone ADR dispatch, and that path is now fixed.
- **In-flow dispatch unchanged.** In the full `pitch_to_ship` flow, adr is still reached after plan-review-eng via the eng review's `Next:` directive; removing the refuse-level prereq does not change that ordering, only removes the false hard-block on the standalone path.
- **No migration required.** v0.7.5 is a manifest + description release on the same v0.7.0 schema. Profile schema unchanged.

## [0.7.4] — 2026-06-19

Adds an optional verdict auto-advance hook to `/immutable:plan-review-eng` and `/immutable:plan-review-ceo`. Both skills can now skip the Phase 4 verdict `AskUserQuestion` and auto-select `APPROVE` on a clean review — but ONLY when an external verdict-autonomy engine is installed AND its policy promotes the per-skill gate to `live`. The hook is thin, additive, and a strict no-op for every existing user: with no engine on `PATH` (and no `$TM_VERDICT_GATE`), the gate resolves to `ask` and the question renders exactly as before. The two-layer split is deliberate — the generic autonomy engine lives outside this plugin (in the operator's harness/dotfiles); this repo carries only the thin in-skill hook that calls it when present.

### Added

- **Autonomy gate block** in `plan-review-{eng,ceo}/SKILL.md` Phase 4.1, before the verdict `AskUserQuestion`. A self-contained bash block resolves the gate via `$TM_VERDICT_GATE` or `command -v tm-verdict-gate.sh`; absent → `GATE_DECISION=ask` → renders the question unchanged. On `proceed` (reached only under `live` policy + a clean APPROVE) the skill skips the question, sets `APPROVE`, and emits the auto-advanced banner. Gate predicate: `APPROVE ∧ issues==0` for ceo; `APPROVE ∧ issues==0 ∧ adr_triggers==0` for eng (ceo has no ADR-form gate, so `--adr-triggers` is omitted).
- **Autonomy receipt block** in the same skills' Phase 4.2, before `### 4.3 Handoff`. When the question WAS rendered (no auto-advance), the block records the human's actual verdict via `--human-pick` so an autonomy engine's measurement loop can learn — the keypress is the label. No-op without the gate; skipped when auto-advanced (the gate writes that receipt itself).
- **`pre.phase4.auto_advanced` and `prc.phase4.auto_advanced`** banner strings in `strings/strings.en.yml`, rendered only when a verdict auto-advances under `live` policy.

### Backward compatibility

- **Zero change for existing users.** No engine on `PATH` → both gate blocks resolve to `ask` and the verdict `AskUserQuestion` renders exactly as in v0.7.3. Each bash block is self-contained (re-resolves the gate inline) because Claude Code runs every skill `bash` block in a fresh shell — env vars do not persist between blocks.
- **Safe even WITH an engine installed.** The reference engine ships a `shadow` default policy, so nothing auto-advances until a gate is earned-promoted to `live` out-of-band. The hook is safe on-by-default.
- **`ship/SKILL.md` untouched.** Its independent `^Verdict: APPROVE` gate stays a separate human-gated step; auto-advance only advances the REVIEW verdict, never ship.
- **No migration required.** v0.7.4 is a catalog + skill-body release on the same v0.7.0 schema. Profile schema unchanged.

### Known follow-up

- **Korean banner strings deferred.** `pre.phase4.auto_advanced` / `prc.phase4.auto_advanced` are en-only this release; the strings system falls back to en for a missing ko key and the banner only renders under opt-in `live` policy, so no user sees a missing string. ko translations plus the `english-guard` exemption for `**/strings/*.yml` are tracked as a follow-up.

## [0.7.3] — 2026-05-16

Closes the emitting end of the `prd → adr (upfront, wrong)` anti-pattern that v0.6.5 partially fixed on the receiving end. `/immutable:prd` Stage 6 handoff now anchors the next step explicitly to `/immutable:design`, with a one-paragraph clarifier framing ADR authoring as reactive (an OUTPUT of `/immutable:plan-review-eng` Phase 3, not an input authored upfront after the pitch). ADR's standalone-callable status (init handoffs as a peer entry point, plan-review-eng standalone-mode quick-ADR path) is preserved — the fix is scoped to the orchestrated `pitch_to_ship` flow, where prd-into-design is the canonical transition.

### Fixed

- **`/immutable:prd` Stage 6 handoff missing next-step anchor.** Prior versions of `prd.stage6.handoff` (`strings.{en,ko}.yml`) rendered only the new file path + GitHub web / CLI registration steps. The string had no line pointing to `/immutable:design` as the canonical next skill in the `pitch_to_ship` flow. Sessions completing `/immutable:prd` were left without an in-skill anchor and inferred the next step from nearby signals — init handoffs that surface ADR as a peer entry point (intended for fresh-repo bootstrap), the plan-review-eng standalone mode's small-task/quick-ADR documentation, and the general visibility of ADR in plugin descriptions — all of which biased toward `prd → adr` as the next move. v0.6.5 already documented this exact anti-pattern in its CHANGELOG entry ("Observed in the wild: workers authored `/immutable:adr` upfront before `/immutable:design`") and corrected `/immutable:plan-review-ceo`'s description to stop framing ADRs as a co-equal prerequisite. v0.7.3 closes the emitting end: `prd.stage6.handoff` now ends with `Next step: /immutable:design <slug>` plus a clarifier paragraph stating ADR authoring is reactive (surfaced by plan-review-eng Phase 3 as an OUTPUT, never authored upfront after the pitch). The clarifier is the load-bearing part — it directly contradicts the inference that was causing the misordering.

### Changed

- **`strings/strings.en.yml` and `strings/strings.ko.yml`** — `prd.stage6.handoff` extended with a `Next step:` line plus a clarifier paragraph. The registration steps (`{github_web_steps}` / `{cli_steps}`) are preserved unchanged above the new block.
- **`immutable/prd/SKILL.md`** Stage 6 Handoff output section — documents the next-step anchor contract and its rationale so future SKILL.md readers (and translators adding new locales) understand why the next-step block exists and must not be dropped during catalog maintenance.

### Out of scope (intentional)

- **`/immutable:adr` preconditions remain unchanged.** ADR is intentionally callable standalone — supported by `init.stage7.handoff_*` (surfacing ADR as a peer entry point alongside pitch in fresh-repo bootstrap) and by `/immutable:plan-review-eng` standalone mode (quick-ADR path for small tasks where the full CEO review is overkill, documented in v0.6.0 CHANGELOG). Pipeline.yaml's `dependencies.adr.deps=[plan-review-eng]` applies only to the orchestrated `pitch_to_ship` flow; adding a hard refusal in the skill body would break the intentional standalone path. The misordering this release addresses is upstream — the prd handoff needs to point reliably to design, not the adr skill needing to refuse.

### Backward compatibility

- **All existing flows are unaffected.** The change is additive — registration steps still render unchanged, and the new next-step block appears below them. Users who were already invoking `/immutable:design` next see no functional change; users who were inferring `/immutable:adr` next now see the explicit anchor and clarifier.
- **Strings catalog forks**: teams that customized `prd.stage6.handoff` keep their override (catalog resolution prefers team profile). To inherit the next-step anchor, copy the new block from `strings.{en,ko}.yml`. Teams without a fork get it automatically.
- **No migration required.** v0.7.3 is a catalog + documentation release on the same v0.7.0 schema. Profile schema unchanged.

## [0.7.2] — 2026-05-07

Design-handoff-note guidance hardened across plan-review skills + declarative pipeline manifest. Eliminates the recurring orchestration-time defect where lead sessions skipped `/immutable:design` between `/immutable:prd` APPROVE and `/immutable:plan-review-ceo`, producing degraded reviews without app-side context grounding. Fix is layered: descriptions tightened (orchestration-time signal lead reads at dispatch decision), declarative pipeline manifest added (orchestrator-facing source-of-truth for phase chain + hard dependencies), and body-level explicit 3-way warn replaces silent-skip (worker-time signal when the skill is already invoked).

### Fixed

- **`plan-review-ceo` Phase 0.1 silent-skip surface.** Prior versions checked for the design handoff note and rendered `prc.warn.no_design_note` only as informational text — execution flowed forward whether the user "saw" the warn or not, and worker contexts that skipped past the warn produced reviews missing app-side grounding (module placement, activation status, dependent features). Phase 0.1 now surfaces the warn via AskUserQuestion as the **first** Phase 0 user interaction, with three explicit branches (A pause + run `/immutable:design`, B proceed degraded with `degraded: no_design_note` recorded in the Phase 4.2 review note, C abort). Silent-skip is no longer a path. Same gate added to `plan-review-eng` Phase 0.2 — applies in both ceo-grounded and standalone modes (ceo-grounded because the user may have taken option B upstream and can revisit it before eng locks in; standalone because no upstream gate exists).
- **`plan-review-ceo` description framing.** v0.6.5 already corrected the ADR portion ("grounded in" → required pitch + recommended design + optional pre-existing ADRs). v0.7.2 sharpens the design portion without escalating it to required: the design handoff note is now framed as an **expected input** (warn-on-absence, NOT hard-refused) with the canonical path inline (`.claude/immutable/design/{slug}.md`), and the description names the AskUserQuestion 3-way explicitly so lead sessions reading only the description (auto-loaded into the system prompt at dispatch time) see the dependency without misreading it as enforced. Same fix applied to `plan-review-eng` description for both ceo-grounded and standalone modes. The contract level remains warn — option B (proceed degraded) is always available; the skill never hard-refuses on a missing design note.
- **Slug-derivation drift between writer and reader.** `/immutable:design` Phase 4.1 derives `FEATURE_SLUG` from `git branch --show-current | tr '/' '-'` with optional env override. Plan-review-ceo Phase 0.1 previously did not compute the slug at all, leaving the design-note path discovery implicit. v0.7.2 adds explicit slug computation in plan-review-ceo Phase 0.1 mirroring the writer's derivation — both sides reference the same `FEATURE_SLUG` semantics, so the contract holds.

### Added

- **`pipeline.yaml`** at plugin root — declarative manifest for `flows.pitch_to_ship` with phases, `dependencies` (per-entry `enforcement: refuse | warn-3way`, mode-keyed for `plan-review-eng`), `soft_dependencies`, `exit_verdicts` (verdict line regex + routing directive line regex + routing targets per verdict), and `skill_output_markers` (e.g., `DESIGN_NOTE_WRITTEN:`). The `enforcement` field per entry tells orchestrators which dependencies hard-block (refuse) vs which surface a warn-3way (silent-skip forbidden but proceed-degraded available). Orchestrators (a dispatcher, cross-plugin schedulers) parse this BEFORE dispatching a worker, layering an orchestration-time signal on top of the worker-time gates inside each skill. Schema is `schema_version: 1`; other plugins adopting the same shape get orchestration compatibility automatically — no immutable-specific terms beyond the `plugin:` field.
- **`pre.warn.no_design_note` strings catalog key** in `strings.{en,ko}.yml` for the new plan-review-eng Phase 0.2 warn (parallel to the existing `prc.warn.no_design_note` for plan-review-ceo). Includes a `{mode_context_hint}` placeholder so the message can adapt for ceo-grounded vs standalone callers.
- **README "Pipeline manifest for orchestrators" section** (above "Schema, profile, strings catalog, validator") explaining the manifest's role as an orchestration-time signal layered on top of in-skill gates.

### Changed

- **`prc.warn.no_design_note` wording** rewritten in `strings.{en,ko}.yml` to: (a) name the degraded-mode consequence concretely (Sections 1, 9, 10 weakened), (b) require recording `degraded: no_design_note` in the review note's scope-context section when option B is chosen, (c) add option C (abort), (d) state explicitly "silent-skip is not allowed". Same shape applied to the new `pre.warn.no_design_note` (sections 1 + 4 + worktree analysis named as the weakened areas).
- **`immutable/plan-review-ceo/SKILL.md`** — frontmatter description, Preconditions #4, and Phase 0.1 design-note-check block all rewritten to match the explicit-3-way-warn contract.
- **`immutable/plan-review-eng/SKILL.md`** — frontmatter description, Phase 0.1 ceo-grounded mode commentary, Phase 0.2 design-note-check block, and strings catalog table all rewritten.

### Backward compatibility

- **All flows that already include `/immutable:design`** are unaffected — the gate is silent-pass when the file exists.
- **Flows that skipped design intentionally** (rare; small refactors, very-early-cycle exploration) now hit the warn explicitly and can choose option B (proceed degraded) — same effective behavior as the prior silent-skip, but the choice is now recorded in the review note's scope-context section so downstream consumers (`/immutable:plan-review-eng`, `/immutable:ship`) see the constraint. No existing flow is hard-blocked.
- **Strings catalog forks**: teams that customized `prc.warn.no_design_note` keep their override (catalog resolution prefers team profile). To inherit the sharper wording + new option C, copy the new value from `strings.{en,ko}.yml`. The new `pre.warn.no_design_note` key lands in the bundled defaults; teams without a fork get it automatically.
- **`pipeline.yaml` is purely additive** — no consumer is required to read it. Existing orchestrators that hard-code phase chains continue to work unchanged. Adoption is opt-in.
- **No migration required.** v0.7.2 is a guidance + manifest release on the same v0.7.0 schema. Profile schema unchanged.

## [0.7.1] — 2026-05-06

`/immutable:prd` Branch A and gate criterion 1 sharpened so §"배경과 문제" content is unambiguously product/service-level — the user/business problem the requirement solves, not the document's own creation rationale.

### Fixed

- **§"배경과 문제" interview drift.** Branch A's prior question set ("Why is this pitch needed?", "What is the current state?", "What specific gap does this pitch close?") was ambiguous between product-level intent and document-level meta. Observed in the wild on real pitch repos: §"배경과 문제" accumulated retro-spec rationale ("PRD didn't exist", "code-spec alignment", sub-pitch positioning) instead of user/business problem statements, leaving future readers without a product-level decision basis. Branch A questions are now anchored to the user/business problem — "what user or business problem does this requirement solve", "for whom and what scenario", "why is this the right product-level approach" — and three explicit reject signals loop the interview back when the answer is document-existence rationale, sub-pitch positioning only, or a generic title restatement.
- **Gate criterion 1 (`background_clear`) wording.** Both `default-ko.yml` and `default-en.yml` previously asked the gate to verify a third party can summarize "intent" / "왜 필요한지" — the same ambiguity. Reworded to require summary of the **user/business problem this requirement solves**, with an explicit rule that document-existence rationale (PRD missing / code-spec alignment / changelog) does not count as a product-level problem statement and fails this criterion.

### Changed

- **`immutable/prd/SKILL.md` Stage 2 Branch A** — question framing rewritten to product-level only; reject-signal block added with three anti-patterns; completion criterion tightened to require user/business problem summary.
- **`immutable/prd/SKILL.md` Stage 5 gate table** — row 1 (`background_clear`) updated to match the profile's revised pass condition.
- **`immutable/examples/_profiles/default-ko.yml`** — `sections[id=background].description` and `gate.criteria[id=background_clear].pass_condition` rewritten with product-level framing + anti-example list.
- **`immutable/examples/_profiles/default-en.yml`** — parity for English-locale teams.

### Backward compatibility

- **Existing pitches unaffected.** The append-only contract is preserved — previously written pitches with document-level §"배경과 문제" content remain valid. The gate change applies only to new in-flight pitches authored via `/immutable:prd` after upgrade.
- **Profile schema unchanged** — no field additions, no schema bump. Teams with custom forks of `default-{ko,en}.yml` keep their overrides intact; only the bundled defaults change. To inherit the sharper wording, copy the new `description` / `pass_condition` strings into the team profile.
- **No migration required.** v0.7.1 is a copy/prompt sharpening release on the same v0.7.0 schema.

## [0.7.0] — 2026-05-05

Cross-session learnings integration. Every interactive skill now appends a structured outcome entry to a shared project memory store on completion or abort, so future skill invocations and `/common:learn` queries can surface prior decisions, blockers, and cancellation reasons across sessions.

### Added

- **`immutable/scripts/learnings.sh`** — vendored jq+bash helper that appends to `~/.gstack/projects/<slug>/learnings.jsonl` (canonical gstack store path). Subcommands: `search [--type T] [--limit N] [--key K] [--include-stale]`, `log '<json>'`, `prune [--dry-run]`, `path`, `slug`. Schema: `{skill, type, key, insight, confidence, source, ts, branch, commit, files}`. Type set: `pattern | pitfall | preference | architecture | tool`. Source set: `observed | user-stated | inferred | cross-model`. The plugin remains standalone — no `~/.claude-dotfiles/` dependency — but the on-disk store is shared with the harness's `/common:learn` skill, which now points at the same path.

- **Canonical project slug.** The store path's `<slug>` derives from the SDD spec repo's directory basename via `IMMUTABLE_PRD_SPEC_CONFIG` (sourced from `sdd_mode_detect.sh` when not pre-set in the env), falling back to git toplevel basename. Two-repo-app mode resolves spec and app sides to the same slug, so the learnings store is one shared per-project space rather than one per repo. Calls into `learnings.sh slug` from SKILL.md log blocks ensure helper and writers agree on a single identity.

- **POSIX-atomic appends + concurrent-writer safety.** `cmd_log` uses `O_APPEND` for the append step; entries (~300-500 bytes) are well under PIPE_BUF, so concurrent `learnings.sh log` invocations from parallel-pod cycles never lose entries.

- **Prune + stale dedup.** `cmd_log` defaults `files: []` so every entry has a uniform schema. `cmd_prune` flags entries whose referenced files no longer exist with `stale: true`. `cmd_search` drops stale rows BEFORE `group_by` (so a stale row that is the newest in its key+type bucket cannot mask earlier active rows), and exposes `--include-stale` for forensic queries.

- **`## Log learning to project memory (mandatory final step)` section** appended to every interactive SKILL.md (`prd`, `design`, `plan-review-ceo`, `plan-review-eng`, `adr`, `ship`). Each skill emits exactly one entry per invocation, on success **or** abort/blocked outcomes. Per-skill mapping:
  - `prd` → `pattern` (success, source `user-stated`) / `pitfall` (abort, source `observed`).
  - `design` → `pattern` (success, source `observed`) / `pitfall` (abort).
  - `plan-review-ceo` → `pattern` on APPROVE (key `scope-<slug>-<pitch>`) / `pitfall` on REVISE/REJECT/abort (key `scope-blocked-...` or `plan-review-ceo-aborted-...`), source `observed`.
  - `plan-review-eng` → mirrors CEO with `eng-` key prefix; insight enumerates architecture / worktree / risks.
  - `adr` → `architecture` (success, source `user-stated`); insight format **inlines the revisit trigger** as `"Decision: X. Revisit when: Y."` so future "what triggers re-visiting X?" queries surface the trigger via substring match on `insight`.
  - `ship` → `tool` (success, key `ship-<branch>-<slug>`, insight enumerates pitch + ADRs + build/test outcome). Branch name is stable across the cycle and known before `gh pr create` runs, so it keys without depending on PR number capture.

- **Cancel-as-information policy.** Aborts (interview cancel, 90% gate fail, hard prohibition hit, refusal verdicts) are logged as `pitfall` entries — the cycle's "what was attempted and why it stopped" carries forward as much value as success captures.

### Changed

- **Six SKILL.md files** gained the `Log learning` final-step section, positioned just before the existing `Hard Prohibitions` / `Critical rules` / `Strings catalog` reference blocks so the linear-flow reader sees it as the last step of the main flow. Best-effort by design — if `${CLAUDE_PLUGIN_ROOT}/scripts/learnings.sh` is unavailable, the call is silently skipped (`2>/dev/null || true`); logging never blocks the flow.

### Backward compatibility

- **Forward-compatible.** Sessions on v0.6.x continue to operate without learnings emission — the absence of `${CLAUDE_PLUGIN_ROOT}/scripts/learnings.sh` is gracefully handled. Sessions that pick up v0.7.0 begin accumulating entries from the next skill invocation; no migration of historical sessions needed.
- **Store path is shared with the harness.** Both the plugin's vendored helper and the harness's `bin/learnings.sh` now point at `~/.gstack/projects/<slug>/learnings.jsonl`; `/common:learn` and `/immutable:*` skills read the same store. Two on-disk copies of the helper exist (plugin-vendored + harness-local). Drift is currently zero (byte-identical) and consolidation is deferred — see `Deferred features` for the path.
- **Deferred features** (slated for follow-up cycles): prompt-injection filter on `insight`, time-based confidence decay on `observed`/`inferred` sources, cross-project search with trust gate, contradiction detection during prune. These mirror the gstack canonical (`garrytan/gstack` 4d2c8d9) Bun-based feature set; the plugin's jq+bash vendor adopts the schema and slug convention now and can graduate to the canonical implementation when Bun becomes a project-wide dependency.

## [0.6.5] — 2026-05-05

Plan-review skill contract clarification + machine-readable routing directive. Fixes a description-driven drift surface where peer Claude sessions misread `plan-review-ceo`'s frontmatter as requiring ADRs to exist before review.

### Fixed

- **`plan-review-ceo` description framed ADRs as a mandatory input.** The previous frontmatter "grounded in the pitch + linked ADRs + design handoff note" placed three artifacts in syntactically equal grounding position, causing some Claude sessions reading only the description (which the harness loads automatically into the system prompt) to interpret ADRs as a co-equal prerequisite alongside pitch and design note. Observed in the wild: workers authored `/immutable:adr` upfront before `/immutable:design`, contradicting the plugin's intended reactive ADR flow (where Phase 3.2 surfaces ADR triggers as an OUTPUT, not an input). Fix rewords the description to make pitch (required) and design note (recommended) the actual inputs, and explicitly states that ADRs are referenced only if pre-existing — never required. Same fix applied to `plan-review-eng`'s standalone-mode body description.
- **Body wording — "three review targets" implied uniformity.** `plan-review-ceo` body listed pitch / linked ADRs / design handoff note as three review targets without marking optionality. Updated to a required / recommended / optional ladder with an explicit "ADRs do NOT need to exist before this review runs" callout.

### Added

- **`Next:` line spec in Phase 4.2** of both `plan-review-ceo` and `plan-review-eng` review notes. Column-0, grep-safe (`grep -E '^Next:[[:space:]]+'`), placed as the LAST non-blank line of the note. Encodes the machine-readable routing directive consumed by downstream sessions:
  - `plan-review-ceo` `Next:` routes to `/immutable:plan-review-eng` on APPROVE, `/immutable:prd <slug>` on REVISE (pitch supersede), or `/immutable:office-hours <slug>` on REJECT.
  - `plan-review-eng` `Next:` is the SOURCE OF TRUTH for whether the ADR step runs. APPROVE with 0 Phase 3 triggers writes `Next: implement → /immutable:ship` (skip ADR entirely); APPROVE with N triggers writes `Next: /immutable:adr <slug-1> → /immutable:adr <slug-2> → … → implement → /immutable:ship`. REVISE / REJECT route back to the appropriate upstream skill.

  Eliminates the ambiguity that v0.6.4's "(if any)" wording left to downstream re-interpretation. The directive is now authoritative; downstream sessions follow it verbatim without re-deciding.

### Changed

- **Phase 4.3 handoff sections** of both `plan-review-{ceo,eng}/SKILL.md` updated to surface the new `Next:` directive as the authoritative routing instruction. Trigger reminders are framed as candidates for the eng review to merge with its own findings — the actual ADR routing decision lives in the eng review's `Next:` directive, which sees the union of CEO + eng-specific triggers.

### Backward compatibility

- **Forward-compatible by design.** Sessions on v0.6.4 that don't grep the new `Next:` line continue to work — the existing `Verdict:` line is unchanged in format, and downstream consumers of v0.6.4 (`plan-review-eng` mode routing, `/immutable:ship` precondition check) keep using `^Verdict:[[:space:]]+APPROVE` as before. The `Next:` line is purely additive.
- Sessions that opt to read `Next:` gain unambiguous routing — particularly valuable for parallel-pod cycles where multiple workers run plan-review concurrently and downstream auditors need to verify which next step each pod is taking.
- Users on v0.6.4 should `claude plugin update immutable` to pick up the description fix and the new directive. No migration required for in-flight cycles.

## [0.6.4] — 2026-05-03

Documentation polish + downstream-verification marker on `/immutable:design`. No interactive behavior change.

### Added

- **`DESIGN_NOTE_WRITTEN: <path>` marker emit** in `immutable/design/SKILL.md` Step 4.3. After the localized confirmation, the skill now emits a single machine-parseable marker line (English literal regardless of `team_language`) carrying the path of the just-written design note. Downstream consumers — auditors, follow-up skills, CI checks — can `grep ^DESIGN_NOTE_WRITTEN: ` to verify the design note was produced by this skill rather than composed manually outside it. Absence of the marker is a tell that the note bypassed the skill's pitch-confirmation / context-capture / template-rendering pipeline.

### Changed

- **HARD GATE wording in `immutable/design/SKILL.md`** dropped the `.claude/sprint/design-*.md (legacy convention)` reference. The migration to `.claude/immutable/design/{slug}.md` is complete on consumer projects and any codebase still using the legacy path is on a pre-v0.5 plugin version anyway. The legacy mention now misdirects more than it protects, so the gate is restated as "Writing any `design-*.md` outside `.claude/immutable/design/` would create drift" — same intent, no stale path leaked into reader context.

### Backward compatibility

- No interactive behavior change in any skill. The marker emit is additive — sessions that previously parsed only the localized confirmation continue to work; sessions that opt to grep the new marker gain a verification signal. Plugin manifests still register the same 9 skills under the same slash names. Users on v0.6.3 should run `claude plugin update immutable` to pick up the doc cleanup and start emitting the marker.

## [0.6.3] — 2026-04-29

Documentation polish release. No skill behavior change; metadata and prose only.

### Added

- **`Design heritage` section** in `immutable/README.md` documenting the two layered fusions that produced the plugin: (1) the `immutable-prd` lineage that reconciles append-only pitch (Shape Up) with mutable-PRD accuracy via supersede chains, so the active artifact reflects current understanding while the chain preserves full revision history; (2) the gstack lineage that contributed a transient → artifact flow pipeline where working notes (office-hours, design, plan-review) feed permanent artifact decisions (pitches, ADRs, PRs). v0.6.0 unified both heritages into a standalone toolkit. Top-level README `Acknowledgements` now points to this section.

### Changed

- **Plugin description** in `marketplace.json` and `plugin.json` rewritten count-free and version-pin-free. Skill names retained as stable identifiers; "v0.6.0 ships nine skills" enumeration removed. Both manifest descriptions kept byte-equal.
- **Top-level README** lost two high-drift surfaces: the `## Structure` directory tree (GitHub repo browsing covers the same need) and the `## Versioning` table (CHANGELOG is canonical; the table was a duplicate that already missed v0.6.0/v0.6.1/v0.6.2 rows). Versioning section is now a one-line CHANGELOG pointer.
- **`/immutable:ship` Ship positioning narrative** in `immutable/README.md` shrunk to the minimum-viable policy statement, dropping the now-obsolete `/sprint:ship` coexistence comparison. The upstream `/sprint:ship` skill was retired in `claude-dotfiles` commit `4bd69d8` (2026-04-28); `/immutable:ship` is now the canonical SDD ship path. `ship/SKILL.md` description and body updated to match — cross-references replaced with hook/wrapper guidance for teams that want cross-session learnings or harness-policy layers.
- **Hardcoded skill counts and version pins** trimmed across READMEs ("nine skills", "(v0.6.0)" parentheticals, "Walks 6 stages") to reduce drift surface. Heritage-section v0.6.0 references and CHANGELOG-style historical anchors retained intentionally — they document when a feature was introduced rather than asserting current status.

### Fixed

- **`migrate/SKILL.md` Overall Process heading** said "(5 stages, v0.5.7+)" while the body enumerated Stage 1 through Stage 6. v0.5.7 inserted Stage 5 (Profile field migration) and renumbered the body but the heading count was missed. Corrected to "(6 stages, v0.5.7+)".

### Backward compatibility

- No skill behavior change. Plugin manifests still register the same 9 skills under the same slash names. Users on v0.6.2 see only documentation improvements after `claude plugin update immutable`.

## [0.6.2] — 2026-04-29

Patch release fixing a marketplace-side registration bug.

### Fixed

- **5 skills missing from `marketplace.json`**. v0.6.0 added `/immutable:{ship,office-hours,design,plan-review-ceo,plan-review-eng}` as new SKILL.md folders, but `.claude-plugin/marketplace.json` `plugins[0].skills` array was not updated to register them. As a result, Claude Code's plugin loader (which uses the marketplace skills array, not directory scan) registered only the original 4 skills (`init`, `prd`, `adr`, `migrate`) for everyone who installed v0.6.0 or v0.6.1. Symptom: the Skill tool returned `Unknown skill: immutable:ship` even on a fully up-to-date install — confirmed reproducible across multiple sessions. Fix: extended the array to all 9 skills, and updated the marketplace `description` and `keywords` to match `immutable/.claude-plugin/plugin.json` (which was already accurate).

### Backward compatibility

- No code changes in any skill. Plugin behavior is unchanged. Users on v0.6.0 / v0.6.1 should run `claude plugin update immutable` after this release; the 5 newly-registered skills will then appear in their available-skills list at next session start.

## [0.6.1] — 2026-04-28

Hotfix release patching three integration issues surfaced by static analysis after v0.6.0 shipped. All three are pre-dogfood findings — the v0.6.0 flow had not yet been exercised end-to-end on a real repo when these were caught — so v0.6.1 prevents the failures rather than reacting to them.

### Fixed

- **`/immutable:ship` Step 3 — `FEATURE_SLUG` undefined**. v0.6.0's `ship/SKILL.md` referenced `${FEATURE_SLUG}` to compose the design / CEO / ENG note paths but never set the variable in any preceding bash block. Each Bash tool invocation is a fresh shell, so the unset variable expanded to empty, producing paths like `.claude/immutable/design/.md` that could never match real notes. Result: `/immutable:ship` would always have refused with `ship.refuse.eng_not_approved`, blocking every PR. The fix adds the canonical slug-derivation line at the start of Step 3 and Step 5.1 (matching the convention used by every upstream skill in the 7-step flow).
- **Verdict-line format mismatch between writer and reader**. The eng review's Phase 0.1 mode routing greps `^Verdict: APPROVE` (literal, line-start) on the CEO note; `/immutable:ship` Step 3 greps the same pattern on the eng note. v0.6.0's `plan-review-{ceo,eng}/SKILL.md` Phase 4.2 instructed the writer only loosely ("Verdict + one-line rationale"), allowing markdown formatting (`**Verdict**: APPROVE`, `### Verdict\nAPPROVE`, `Verdict: **APPROVE**`, indented or list-marker-prefixed lines) that breaks the grep. The fix tightens the writer side with an explicit "Verdict line — REQUIRED format" callout in both ceo and eng Phase 4.2 (lists acceptable / not-acceptable forms with a worked example), and slightly loosens the reader greps to use `[[:space:]]+` instead of a literal space — so a benign extra space is tolerated, but markdown formatting still fails fast.
- **Template-file pre-reads not strongly enforced**. v0.6.0 referenced three output templates (`plan-review-ceo/templates/data-flow-diagram.md`, `plan-review-ceo/templates/error-rescue-map.md`, `plan-review-eng/templates/test-coverage-diagram.md`) with passive prose ("the template lives at..."). The Read-tool fetch was implied but not commanded, so Claude could plausibly skip the pre-read and produce freestyle output. The fix replaces the passive references with explicit "**use the Read tool to fetch `${CLAUDE_PLUGIN_ROOT}/.../template.md` now**" instructions tied to the relevant section's pre-read step, matching the strength already used for `sections.md` and `nuclear-scope-rubric.md`.

### Changed

- **Reader-side verdict greps** in `plan-review-eng/SKILL.md` Phase 0.1 (3 lines) and `ship/SKILL.md` Step 3 (1 line) updated from `'^Verdict: APPROVE'` (and equivalents) to `'^Verdict:[[:space:]]+APPROVE'` (regex). Comments next to each grep now explicitly document the writer-side format requirement, so a future reader knows where the contract is enforced.

### Backward compatibility

- Strictly forward-compatible. All v0.6.0 catalog keys, supporting files, scripts, and starters are unchanged. Repos that pulled v0.6.0 see only behavior fixes; no action required on the user side.
- The verdict-line tightening is a writer-side rule. v0.6.0 review notes that happened to use the canonical `Verdict: APPROVE` form keep working under v0.6.1's reader. Notes with markdown formatting that v0.6.1 would have refused never reached production (the bug they would have triggered was caught here statically before any cycle ran).

## [0.6.0] — 2026-04-28

Adds five new flow skills so the entire spec-driven development cycle runs from this plugin alone — no external harness required. Previously the SDD flow needed a local `~/.claude-dotfiles/claude/commands/sprint/` toolset (`office-hours`, `design`, `plan-review`, `plan-review-ceo`, `plan-review-eng`, `ship`); v0.6.0 absorbs the immutable-prd-mode behavior of those skills into the plugin so `claude plugin install immutable` is the single setup step on any machine.

### Added

- **`/immutable:office-hours`** — heaviest context-gather skill in the flow. Forces premise challenge plus three implementation alternatives (Minimal / Ideal / Creative) before any approach is chosen. Output is a transient design-doc note at `.claude/immutable/office-hours/{slug}.md` that `/immutable:prd` consumes during Stage 1.5 Context Intake. Refuses to write code; writes only the one transient note.
- **`/immutable:design`** — lightweight bridge between pitch authoring and review. Confirms which pitch the implementation work targets, captures the app-side context the pitch couldn't include (activation status, dependent features, module placement), and writes a transient handoff note at `.claude/immutable/design/{slug}.md`. Does NOT generate a design artifact — the pitch is the design artifact in immutable-prd mode.
- **`/immutable:plan-review-ceo`** — scope challenge + 11-section adversarial review of pitch + linked ADRs + design handoff. Phase 0 nuclear scope challenge (premise / existing-code leverage / dream-state / **mandatory alternatives** / mode selection). Phase 2 walks 11 sections (Architecture / Error & Rescue Map / Security / Data Flow / Code Quality / Test / Performance / Observability / Deployment / Long-Term / UX). Phase 3 surfaces pitch-supersede candidates and ADR-authoring candidates. Outputs `.claude/immutable/plan-review/{slug}-ceo.md` with verdict.
- **`/immutable:plan-review-eng`** — engineering-perspective review with two-mode routing. **`ceo-grounded`** when `/immutable:plan-review-ceo` ran first and APPROVED — consumes the CEO scope envelope and Phase 3 trigger list, skips the lightweight scope check. **`standalone`** when no CEO note exists — runs a built-in lightweight scope check (Phase 0.3) and surfaces every architecture decision as an ADR candidate (no CEO Phase 3 to cross-reference). Standalone mode supports the small-task / quick-ADR path where the full CEO review is overkill. Refuses with structured options when CEO note exists in REVISE / REJECT state. Walks 4 sections (Architecture-eng / Code Quality / Test Coverage Diagram / Performance) and runs a worktree parallelization analysis. Outputs `.claude/immutable/plan-review/{slug}-eng.md` recording the mode + verdict.
- **`/immutable:ship`** — final step, intentionally **minimum-viable**. Runs pre-ship checklist (branch sanity, commit hygiene), verifies review artifacts (ENG note must be APPROVE), runs build + test for the auto-detected project type (Flutter / iOS / Node / Python / Rust / Go), composes a PR body that auto-includes pitch path + linked ADRs + Test Coverage Diagram + deferred items from CEO Phase 3, and runs `gh pr create` after explicit user confirmation. Does NOT integrate cross-session learnings capture or harness policy enforcement — teams running an external harness with a richer ship skill (e.g., gstack `/sprint:ship`) may prefer that. Both skills coexist without conflict (different slash namespaces); see `immutable/README.md` "Ship positioning" for the routing rules.
- **`scripts/sdd_mode_detect.sh`** — sourceable bash script consolidating the SDD-mode detection logic (walk-up → explicit pointer → sibling-suffix → cross-pair resolution via `spec_repo_path:` and reverse-config scan). Replaces ~200 lines of duplicated detection in each flow skill. Exports `SDD_MODE`, `IMMUTABLE_PRD_CONFIG`, `IMMUTABLE_PRD_SPEC_CONFIG`, `IMMUTABLE_PRD_APP_CONFIG`, `IMMUTABLE_PRD_REPO_MODE`, `SDD_AMBIGUITY_FLAG` into the caller's shell.
- **`.claude/immutable/` transient artifact namespace**. Five flow skills write notes here for cross-skill handoff. Gitignored by the init starter (all 6 starter directories now ship a `.gitignore` containing the line). Manually-bootstrapped repos see `common.transient_namespace_hint` on first write.
- **79 new strings catalog keys** across `strings.ko.yml` and `strings.en.yml` (parity-strict): 5 shared `common.*`, 17 `oh.*`, 10 `design.*`, 21 `prc.*`, 18 `pre.*` (covers the dual-mode routing — ceo-grounded / ceo-missing / ceo-blocked / standalone), 13 `ship.*`. `strings.ja.yml` continues to fall back to `en` per existing convention.
- **3 new SCHEMA.md sections**: "7-step SDD flow", "Transient artifact namespace", "scripts/sdd_mode_detect.sh helper".
- **Progressive disclosure pattern** for new flow skills: SKILL.md kept under ~500 lines; detailed reference (review sections, rubrics, output templates) lives in supporting files (`sections.md`, `nuclear-scope-rubric.md`, `templates/*.md`) that the skill instructs Claude to read at the right moment. Existing skills (`prd`, `adr`, `init`, `migrate`) are unchanged in this release; their refactor to the same pattern is deferred to a future minor.

### Changed

- **`README.md` (immutable/) skill table** lists nine skills (was four). The "What v0.6.0 changed" section is added; the existing "What v0.5 changed" section is preserved for archival reference.
- **All 6 init starter directories** (`spec-{ko,en}`, `app-{ko,en}`, `single-{ko,en}`) gain a `.gitignore` containing `.claude/immutable/`. Previously these starters had no `.gitignore`, so v0.6.0 transient notes would have been visible to git.

### Removed

- Nothing. v0.6.0 is fully backward-compatible with v0.5.x — existing skills, configs, profiles, and starters work without any change.

### Backward compatibility

- **Existing v0.5.x repos** can use the new flow skills immediately on install. No config bump or migration is required.
- **`/immutable:prd`, `/immutable:adr`, `/immutable:init`, `/immutable:migrate`** — behavior is unchanged. The validator (`scripts/validate_docs.py`) is unchanged.
- **Repos manually bootstrapped before v0.6.0** must add `.claude/immutable/` to their `.gitignore` themselves. The flow skills surface a one-line hint on first write.
- **Legacy mode** — the new flow skills require `.immutable-prd/config.yml` and refuse with a structured message otherwise (suggesting `/immutable:init`). v0.5.x didn't have flow skills, so this is not a regression.
- **No `~/.claude-dotfiles/` dependency.** The new skills do not call `policy-resolve.sh`, `learnings.sh`, or any other gstack helper. Users keeping a local gstack harness alongside v0.6.0 see no conflict — the layers are now disjoint.

## [0.5.8] — 2026-04-24

Restructures `/immutable:migrate` Stage 5 from per-version recipes to a universal structural diff algorithm. Motivated by a v0.5.7 dogfood gap report (peer e4185825): the v1→v2 recipe omitted `sections[user_stories].structure: per_story_grouped` because the SKILL.md author manually enumerated additions and missed one. Recipes are case-by-case patches by nature — every new field added in a future plugin version requires another SKILL.md update, with the same risk of omission. v0.5.8 eliminates that class of bug structurally.

### Changed

- **`/immutable:migrate` Stage 5.2 — universal structural diff** replaces per-version recipes. The skill now parses both team profile and bundled default as YAML, walks the bundled structure top-down, and identifies every additive difference: missing top-level keys, missing id-keyed sequence entries (matched by `id` or `key`), missing nested fields under existing entries. Output is a flat list of additions that Stage 5.4 executes via Edit operations. Future field additions in any plugin version are picked up automatically — no SKILL.md update required.
- **Override preservation guarantees codified as algorithmic invariants** (rather than per-recipe rules):
  - Scalars in team profile are never modified.
  - Existing id-keyed entries are recursively walked but never replaced.
  - Anonymous string lists (`feature_flag.states`, `personas[*].checks`, etc.) are preserved entirely — no element-level merging because there is no safe identity for diffing.
  - Comments in the team profile are never touched.
  - Description / heading text edits in bundled defaults do not propagate to teams that explicitly customized them.
- **Sequence type detection** — a sequence is "id-keyed" when every element is a mapping containing either `id` or `key`. Otherwise treated as "anonymous" (preserved entirely from team). Documented examples in SKILL.md §5.2.2.
- **SCHEMA.md "Profile field migration" subsection** rewritten to cover the v0.5.7→v0.5.8 transition, the recipe-vs-diff comparison table, override preservation guarantees as algorithmic invariants, and the locale parity guarantee that makes the universal diff sound across ko/en/future locales.

### Fixed

- **Recipe v1→v2 omission in v0.5.7** — `sections[user_stories].structure: per_story_grouped` was missing from the v0.5.7 hardcoded recipe. Under universal diff (v0.5.8), this field is detected automatically and included in the migration plan. Teams who already migrated under v0.5.7 will see `structure` flagged on next `/immutable:migrate` invocation (Stage 5 is idempotent — no harm in re-running).

### Added

- **Locale parity guarantee** documented in SCHEMA.md — bundled default-ko.yml and default-en.yml maintain identical structure (only locale-specific values differ, e.g., `vague_words` entries). This is now an explicit invariant; structural divergence between locale defaults is a breaking change. Verified via parity audit during v0.5.8 development (268 ko keypaths vs 262 en keypaths — only the `vague_words` items differ, by design).

### Backward compatibility

- **Behavior is strictly more inclusive than v0.5.7.** Any addition the v0.5.7 recipe would have caught is also caught by the v0.5.8 universal diff. Plus the universal diff catches additions the recipe missed (e.g., `structure`).
- **No catalog key changes.** All `migrate.stage5.*` and `migrate.stage6.*` keys from v0.5.7 are reused unchanged.
- **Teams who already ran `/immutable:migrate` v0.5.7** can re-run on v0.5.8 to pick up `sections[user_stories].structure` (and any future bundled additions). Idempotent — re-runs add only what is still missing.
- **profile_schema bump remains explicit** (still a single in-place edit at the end of Stage 5). The diff algorithm is structural; the schema version marker is intentional metadata.

## [0.5.7] — 2026-04-24

Hotfix for a defect surfaced during v0.5.6 dogfood: teams who ran `/immutable:migrate` on an earlier plugin version had a frozen v1 team profile that did not pick up v0.5.6's new `anti_monolith` block, `max_items` field, `concern_scope` gate criterion, or `quality_auditor` persona. The §1.2.1 anti-monolith pre-check fallback chain ("derive from `max_items`") also broke because v1 profiles lack `max_items` entirely. Net result: v0.5.6 headline features were silently disabled for migrated teams.

### Added

- **`/immutable:migrate` Stage 5 — profile field migration**. Reads team `profile_schema:` (default `1` if absent), compares to bundled default, and inserts only missing fields. Existing values are preserved verbatim. Bumps `profile_schema:` on success. Per-version recipes describe what was added between consecutive versions (currently `v1 → v2` covers the v0.5.6 surface). Idempotent — re-running adds nothing.
- **`/immutable:migrate` Stage 1 routing matrix** — five distinct outcomes now mapped (config v2 + profile v1, config v3 + profile stale, fully current, profile missing, profile ahead of plugin). Replaces the v0.5.6 binary "already at v3 → refuse" decision.
- **`/immutable:prd` and `/immutable:adr` Stage 1.bis schema mismatch detection**. When the team profile schema is older than the bundled default, the skill renders a one-line warning + recommends `/immutable:migrate`. For the in-flight run, missing fields fall back to bundled default values **with source annotation** ("from bundled default-ko v2 — your team profile is v1"). No disk write. Surfaces silent-skip behavior immediately rather than letting it pass unnoticed.
- **`/immutable:prd` §1.2.1 anti-monolith fallback chain extended**. New step 3: when team profile lacks `anti_monolith` AND `max_items`, fall back to the bundled default's values (with source annotation). Step 4 (skip with note) only fires when even the bundled default lacks the block — should be impossible in correctly-installed plugins.
- **Catalog keys (ko + en)** for: `migrate.stage1.fully_current`, `migrate.stage1.profile_missing`, `migrate.stage1.profile_ahead_of_plugin`, `migrate.stage2.plan_preview_full` / `_profile_only` / `_config_only`, `migrate.stage5.*` (already_current, field_added, field_skipped_present, execute_progress, edit_failure, verify_failure), `migrate.stage6.handoff` + `note_concern_scope_threshold`, `prd.stage1.profile_schema_mismatch` + `profile_fallback_annotation` + `anti_monolith_skipped_no_threshold`, `adr.stage1.profile_schema_mismatch` + `anti_monolith_skipped_no_threshold`.

### Changed

- **`/immutable:migrate` skill description and process overview** — now declares two responsibilities (config + profile field migration) instead of one. Stage count expanded from 4 to 6.
- **`migrate.stage1.already_v3` catalog key** — preserved for backward-compat but downgraded to a soft alias. New callers should use the routing-matrix outcomes (`fully_current` / `profile_missing` / `profile_ahead_of_plugin`).
- **SCHEMA.md `Migration` section** — added "Profile field migration (v0.5.7+)" subsection documenting the two-responsibility model, override preservation guarantee, and authoring-time detection behavior.
- **`/immutable:migrate` Hard Prohibition #8** added: "Never change existing profile.yml values in Stage 5." Default value changes (e.g., `min_items: 2 → 1` in v0.5.6 defaults) are NOT propagated — teams who set explicit values likely want them.

### Backward compatibility

- **Teams on plugin v0.5.5 or older** are unaffected — `/immutable:migrate` still works for the v2 → v3 transition, and Stage 5 is a no-op when team profile schema already matches bundled.
- **Teams on plugin v0.5.6 with current profile** are unaffected — Stage 1 routing detects fully-current state and aborts cleanly.
- **Teams on plugin v0.5.6 with stale profile** (the dogfood case) get Stage 1 detection + Stage 5 migration on next `/immutable:migrate` invocation. Until then, Stage 1.bis warning surfaces in `/immutable:prd` and `/immutable:adr` runs.
- **`gate.total` and `gate.pass_threshold` are NOT auto-bumped** even though `concern_scope` is added. Teams must opt in to the new criterion counting toward the gate by editing those values manually. Stage 6 handoff includes a NOTE pointing this out.
- **`migrate.stage1.already_v3` callers** continue to render correctly (alias message is informative even if less precise).

## [0.5.6] — 2026-04-24

The single largest design change since v0.3. Drops the global "single active per (domain, type)" cap and reframes a PRD as **1 feature/policy** instead of **1 domain charter**. Multiple active PRDs may coexist in the same domain, each on its own supersede chain. A new 3-tier `anti_monolith` guard (hint / strong-recommend / block) replaces the implicit cap with a measurable one tied to feature-scoped sub-section and normative counts.

Motivated by dogfood evidence: the lounge-x-spec repo had a 197-line `order-history` PRD covering 8 sub-sections, a `settings` chain superseded 4× in a single day, and 8 cross-cutting ADRs that could not all live in `_global` because of the (domain, type) cap — driving a workaround that proposed adding 7 fake `_arch_*` reserved domains. v0.5.6 removes the underlying constraint that produced these patterns and adds explicit guards so the new flexibility doesn't degrade into multi-feature dumping.

### Added

- **`anti_monolith` profile block** (top-level for pitches, `adr.anti_monolith` for ADRs). 3 tiers — `L1: hint`, `L2: strong_recommend`, `L3: block` — each carrying threshold pairs (`sub_sections` + `normative_lines` for pitches; `alternatives_count` + `consequences_count` for ADRs). When the block is omitted, thresholds derive from `sections[user_stories].max_items` (L1 = max+1, L2 = max+2, L3 = max×3; normative_lines = sub_sections × 5).
- **`sections[user_stories].max_items`** field. Default: 3. Caps `### ` sub-section count under the user_stories H2 — exceeding triggers anti_monolith escalation. Bump to 4 in your team profile if 4-step linear flows (checkout, onboarding, etc.) are common.
- **New gate criterion `concern_scope`** (8th in default profile, raises `gate.total: 7→8` and `gate.pass_threshold: 6→7`). Fails when the in-flight draft exceeds L3 thresholds. L1/L2 violations pass with hint/warning rather than fail.
- **5-way intent classification** in `/immutable:prd` Stage 1.3 — adds `refactor-split` (Stage 1 only — decomposes oversized PRD into N small PRDs without semantic change) and `split-from` (refactor + new semantic change applied to one of the resulting small PRDs, in two reviewable phases).
- **Anti-monolith pre-check** in Stage 1.2 — every active PRD in the target domain is tier-classified and surfaced in the Stage 1.4 confirmation block. Tier of the user's intended target drives Stage 1.3 menu adjustment (L2 promotes split, L3 removes `update`).
- **Stage 2 derivation policy** — the recommended-answer source priority now demotes oversized active PRDs to "fact-source only, never structural template", preventing the new authoring session from inheriting the anti-pattern.
- **Quality auditor persona** gains 2 new checks — intake-decomposition awareness (intake 1:1 mapping assumption dropped) and per-sub-section normative imbalance detection.
- **SCHEMA.md** new sections: "Anti-monolith escalation" (mechanism + tier semantics + fallback formula), "Anti-patterns" (domain-charter, fake reserved domains, dumping intake — with symptom/why/fix triples).

### Changed

- **Validator `check_single_active_invariant` → `check_supersede_chain_integrity`** (`scripts/validate_docs.py`). The global per-(domain, type) cap is removed. New invariant: for each file F with non-null `F.supersedes`, the target T must exist in the same doc-type set AND have `deprecated: true`. Multiple active leaves in the same domain are valid, each on its own chain. Fan-out (1 predecessor superseded by N successors — the canonical refactor-split shape) is permitted.
- **SCHEMA.md "Mutability policy" rewritten** to reflect per-edge integrity and add a new "Granularity (1 PRD = 1 feature/policy, not 1 PRD = 1 domain)" subsection. Validation invariant #3 reworded.
- **Profile depth knobs recalibrated** for the per-feature model:
  - `sections[user_stories].min_items: 2 → 1` (single-feature PRDs with one happy path + one error path are normal)
  - `sections[edge_cases].min_items: 2 → 1` (a small toggle-style PRD legitimately has one edge row)
  - `gate.criteria[gwt_minimum]` — semantics shift from "≥2 GWT blocks" to "happy ≥1 AND alternate/error ≥1" (kind check rather than count)
  - `gate.criteria[edge_cases_minimum]` — pass threshold lowered from "≥2 rows" to "≥1 row"
  - `gate.criteria[normative_minimum]` — kept at ≥3 (the depth signal of a feature spec; preserved even for small PRDs)
- **`profile_schema: 1 → 2`** bump on default-ko.yml and default-en.yml. v1 profiles continue to load (the new fields fall back to derived defaults).
- **`product_lead` persona check** strengthened — "Epic-level content" now references the anti_monolith tier triggers rather than a soft heuristic.

### Removed

- **`(domain, type)` single-active cap** as a global invariant. Behavior preserved for repos that genuinely host one PRD per domain (the per-edge integrity check is satisfied trivially when there's only one chain).

### Backward compatibility

- **Existing pitches and ADRs are valid as-is.** No body changes required. The validator's new check is strictly weaker for repos that previously satisfied the global cap — anything that passed v0.5.5 passes v0.5.6.
- **v1 profiles** (`profile_schema: 1`, no `anti_monolith` block, no `max_items` field) load with derived fallbacks. Default-ko / default-en explicitly bump to v2 to ship the new defaults.
- **Repos with oversized PRDs** (e.g., dogfood lounge-x-spec) will see L3 classification on their large active PRDs starting from the next `/immutable:prd` invocation in those domains. Existing files are untouched; the next authoring session receives a recommendation to use `refactor-split` rather than continuing the monolith. Choosing `new` (a separate small PRD in the same domain) is fully supported and recommended.

## [0.5.5] — 2026-04-24

Removes the last hand-edit step from the `two-repo-app` bootstrap flow. Previously, `/immutable:init` copied an app starter with a `spec_repo_path: ../<your-spec-repo>` placeholder that the user had to open in an editor afterward — a silent friction point for users whose spec repo did not follow the `-spec` suffix convention (backend / api / server repo pairs) and a correctness hazard when users forgot to replace it before running `/immutable:adr`. The skill now conducts the path interview interactively and writes the real path directly into config.yml.

### Added

- **`/immutable:init` Stage 5.4 — Spec repo path interview (two-repo-app only)**. After the starter is copied, the skill scans sibling directories for spec repo candidates (non-recursive, one level up, matching `repo_mode: two-repo-spec`), renders a prompt with an optional soft-default suggestion when exactly one candidate is found or a numbered pick-list when multiple are found, accepts any absolute or relative path the user types, warns (non-fatally) when the target directory does not yet exist, and edits the placeholder line in `.immutable-prd/config.yml` in place. Naming-agnostic: the interview works identically for `myproject-backend` ↔ `myproject-spec`, `api-server` ↔ `api-docs`, or any other pairing the user has.
- **Catalog keys (`strings.ko.yml` + `strings.en.yml`)**: `init.stage5.spec_path_question`, `spec_path_suggestion`, `spec_path_no_candidate`, `spec_path_multiple`, `spec_path_set`, `spec_path_skipped`, `spec_path_missing_target`. Plus two Stage 7 variants: `init.stage7.handoff_two_repo_app_configured` (rendered when the path was set interactively — omits the placeholder-edit step) and `init.stage7.handoff_two_repo_app_pending` (rendered when the user deferred — retains the original "edit the placeholder" instruction).

### Changed

- **`init.stage7.handoff_two_repo_app` → renamed to `init.stage7.handoff_two_repo_app_pending`** and a companion `_configured` variant added. Stage 7 selects between them based on the Stage 5.4 outcome. The `_pending` text reinforces that any naming is acceptable (removes the "sibling" framing that suggested directory adjacency was required).

### Backward compatibility

- User may still decline the Stage 5.4 interview (empty response / `skip` / `나중에`). In that case behavior is identical to v0.5.4: the placeholder remains in config.yml and the Stage 7 handoff instructs the user to edit it manually.
- Existing `spec_repo_path:` values in already-initialized repos are untouched. The new interview only runs during fresh `/immutable:init` invocations and only touches the placeholder line in a just-copied starter.
- Single-repo and two-repo-spec modes are unchanged — Stage 5.4 is skipped entirely for those modes.

## [0.5.4] — 2026-04-23

Hygiene release for multi-plugin marketplace readiness. No user-facing feature changes — this release restructures manifests and documentation so the `skills` marketplace repo can host additional plugins alongside `immutable` without ambiguity around versioning or changelogs. Existing `/immutable:*` skills, profiles, starters, and validator behavior are unchanged from v0.5.3.

### Added

- **`immutable/.claude-plugin/plugin.json`** — canonical per-plugin manifest declaring `name`, `version`, `description`, `author`, `license`, `homepage`, `repository`, `keywords`. Claude Code's version resolution uses this file first ("plugin.json takes priority" per `plugins-reference` docs), giving each plugin a single source of truth for version independent from the marketplace manifest.

### Changed

- **`.claude-plugin/marketplace.json`** — removed `metadata.version` root field. It was effectively `immutable`'s version under a non-standard location (Anthropic's own multi-plugin marketplace does not use it). Version now lives in `immutable/.claude-plugin/plugin.json` exclusively.
- **`CHANGELOG.md` relocated** — top-level `CHANGELOG.md` moved to `immutable/CHANGELOG.md` so each future plugin can own its own changelog. The marketplace repo may keep a slim top-level CHANGELOG for marketplace-level events (plugin added / removed / renamed) going forward.
- **`README.md`** — Versioning table row updated to v0.5.4 with multi-plugin hygiene note.

### Removed

- **`marketplace.json: metadata.version`** — see Changed.

### Migration

- **End users of `immutable`**: no action required. `claude plugin list` will display `Version: 0.5.4` (previously showed the install-time commit SHA fallback, e.g., `34dae9d34574`) after the next marketplace sync. Users with auto-update disabled run `/plugin marketplace update skills` (or the Marketplaces tab's "Update marketplace" button) and then `Update now` on the Installed tab.
- **Marketplace maintainers adding a 2nd plugin later**: each new plugin owns its version via its own `<plugin>/.claude-plugin/plugin.json`. Git tags follow the official `{name}--v{version}` convention produced by `claude plugin tag`.

## [0.5.3] — 2026-04-23

Patch release: tightens pitch authoring along two independent axes — **shape** (the per-story structure of the user-stories section) and **depth** (detail level proportional to complexity). Motivated by observed drift patterns across real pitches: bottom-consolidated normative bundles divorced from their stories, inline prose-style `[MUST]` that breaks grep/CI extraction (especially in Korean output from some models), vague hedge words that push interpretation onto implementers, and shallow normative counts in complex domains.

### Added

- **`profile.sections[id=user_stories].structure` field** (`per_story_grouped` | `consolidated`; default `per_story_grouped`). Declared in `immutable/examples/_profiles/default-ko.yml` and `default-en.yml` with inline documentation of both values and the enforcement sites (Stage 2, Stage 6 guard, validator).
- **Stage 6 pre-write structure guard** in `/immutable:prd`. Runs after the required-sections guard, only when `structure == per_story_grouped`. Enforces:
  - ≥2 `### ` sub-sections under the user-stories H2 (matches `min_items = 2`);
  - each `### ` sub-section carries ≥1 **bullet-list** bracketed normative line (`- **[MUST]** …`); inline paragraph normative is flagged separately as a drift signal;
  - no bracketed normative leakage between the H2 and the first `### `.
  Aborts file generation on violation and loops back to Stage 2 Branch B. Cross-cutting normative-only sub-sections are accepted (e.g., "shared result-code handling") — the guard does not require GWT inside every sub-section.
- **Stage 3 vague-word detection** — `profile.vague_words[]` carries locale-specific hedge-word regex lists (ko: `적절히`, `자연스럽게`, `충분히`, `가능한`, `합리적`, `일반적`, `최대한`, `필요에 따라`, `상황에 맞게`, `안전하게`, `부드럽게`; en: `appropriate(ly)`, `reasonabl(e|y)`, `natural(ly)`, `sufficient(ly)`, `as needed`, `etc.`/`and so on`, `smooth(ly)`, `safe(ly)`, `general(ly)`). On hit, Stage 3 renders `prd.stage3.vague_word_warning` and loops back to the relevant Branch. Skill-side only — not enforced by `validate_docs.py` (semantic noise would break CI predictability).
- **Stage 3 inline-paragraph normative scan** — catches `[MUST]` embedded in prose (the Korean-drift pattern) during authoring, renders `prd.stage3.inline_normative_warning`, and requires re-writing in bullet form before Stage 4.
- **4th adversarial-review persona `quality_auditor`** — appended to `profile.personas[]` in both bundled profiles. Question: "Can this pitch be implemented and verified against measurable criteria, with no clauses requiring subjective judgment?" Checks cover concrete-value density, context-vague hedge phrases (semantic complement to the Stage 3 regex), Then pass/fail decidability, hidden passive-voice actors, and depth-to-complexity balance. Stage 4 header updated from "(3 Personas)" to "(4 Personas)".
- **Stage 2 Branch B authoring guidance** — elicits per-sub-section normative lines alongside the GWT triple so Stage 6 assembly has the material the guard expects.
- **Stage 4 minimum-only explicit** — existing "each persona MUST surface ≥1 gap" clarified as a minimum (not a cap); LLM continues surfacing every non-trivial gap for complex pitches.
- **`validate_docs.py --strict-body` structure check (pitch only)** — mirrors the skill-side Stage 6 guard so teams wiring the validator into pre-commit hooks or CI pipelines catch the same violations post-hoc. Still gated on `--strict-body` (opt-in); activates only when the profile sets `structure == per_story_grouped`.
- **New strings** in `strings.en.yml` and `strings.ko.yml`: `prd.stage6.missing_story_structure` (expanded to cover bullet-only + min-2 rules), `prd.stage3.vague_word_warning`, `prd.stage3.inline_normative_warning`.

### Changed

- **Starter TEMPLATE.md files** — `spec-{ko,en}/pitches/TEMPLATE.md` and `single-{ko,en}/spec/pitches/TEMPLATE.md` rewrite the user-stories section to demonstrate `per_story_grouped` layout (two `### ` sub-sections, each carrying a GWT triple + bracketed MUST list on bullet lines). Inline HTML comment documents the `consolidated` alternative.
- **`prd/SKILL.md` profile-field table** — adds rows for `sections[id=user_stories].structure` and `vague_words[].regex / hint`.
- **`SCHEMA.md` invariant 8** — widened body-constraint description to cover the v0.5.3 per-story structure check alongside the existing required-sections check.

### Migration

- **Zero-action path (recommended)** — install v0.5.3 and keep your existing config. The bundled default profiles ship `structure: per_story_grouped` and the new `vague_words[]` + `quality_auditor` persona automatically. New pitches generated through `/immutable:prd` adopt the per-story, bullet-only layout by default. Existing pitches are append-only and untouched.
- **Teams with repo-local forked profiles from v0.5.2** — the new fields (`sections[id=user_stories].structure`, `vague_words[]`, `personas[id=quality_auditor]`) are missing from your fork. Missing fields fall back to bundled defaults — no config change required. To opt out of the structure guard explicitly, add `structure: consolidated` to the `user_stories` section in your profile.
- **Teams running `--strict-body` in CI** — the new pitch structure check activates under the same `--strict-body` flag. Existing pitches authored in v0.5.2 shape (consolidated, bold-label, or inline-normative) will fail the check. Options: flip the profile to `structure: consolidated`, supersede the affected pitches with per-story-grouped versions, or stop passing `--strict-body` in CI until migration completes.

### Deprecated

None.

### Removed

None.

### Fixed

None.

## [0.5.2] — 2026-04-22

Patch release: extends `validate_docs.py --strict-body` from ADR-only to pitch + ADR. Achieves CI/hook parity with the v0.5.1 skill-side guard for teams that wire the validator into pre-commit hooks or pipelines. Still opt-in (off by default). No config changes; no migration needed.

### Changed

- **`validate_docs.py --strict-body`** now validates pitch bodies in addition to ADR bodies. Every `profile.sections[i].required == true` entry (pitch) and `profile.adr.sections[i].required == true` entry (ADR) must appear as an `##` heading. Violation message labels the doctype (`missing required pitch section` / `missing required ADR section`). Off by default — behavior unchanged for teams that don't use the flag.
- **`SCHEMA.md` invariant 8 (CI validator clause)** — scope widened from ADR to pitch + ADR; backward-compat note widened from "v0.4 ADRs" to "v0.4 repos".
- **`validate_docs.py` internal refactor** — `validate_adr_body` renamed to `validate_body_headings` (doctype-agnostic). Shared `_extract_required_headings` helper backs both `profile_required_adr_headings` and the new `profile_required_pitch_headings`.

### Deprecated

None.

### Removed

None.

### Fixed

None.

## [0.5.1] — 2026-04-22

Patch release: adds a Stage 6 skill-side guard that verifies required section headings are present in the assembled body before `/immutable:prd` and `/immutable:adr` write the file. Complements the v0.5.0 opt-in `--strict-body` CI check by catching missing sections at generation time. No config changes; no migration needed.

### Added

- **Stage 6 required-sections guard (pitch + ADR)** — always-on, skill-side. Iterates `profile.(adr.)sections[]` and fails generation if any `required: true` entry is missing as an `## <heading>` in the body. Aborts without writing the file or flipping `deprecated`, and loops back to the interview (Stage 2 for pitch, Stage 3 for ADR). Covers custom profile forks that add required sections beyond the default branches. Skill-side complement to v0.5.0's ADR-only `--strict-body` CI check.
- **New strings** — `prd.stage6.missing_required_section` and `adr.stage6.missing_required_section` in `strings.en.yml` and `strings.ko.yml`, with `{missing_headings}` placeholder rendering the ordered list of absent `##` lines.

### Changed

- **`SCHEMA.md` invariant 8** — split into two clauses: skill-side guard (always on, both doctypes) and CI-side `--strict-body` (opt-in, ADR only).
- **`prd/SKILL.md` and `adr/SKILL.md` profile-field tables** — the `sections[].id / required / min_items / description` row now reflects that `required` is consumed at Stage 6 by the guard (in addition to the Stage 2/3 interview branches).

### Deprecated

None.

### Removed

None.

### Fixed

None.

## [0.5.0] — 2026-04-20

The "foundation" release: extends the v0.4 two-skill toolkit into a four-skill bootstrap-able plugin with externalized configuration. v0.4 repos keep working without any change — every new surface is opt-in.

### Added

- **`/immutable:init`** — 7-stage bootstrap skill (probe → mode → language → profile → copy → git → handoff). Copies one of six bundled starters into the current directory. Never overwrites existing files. Never runs git operations.
- **`/immutable:migrate`** — 4-stage idempotent v0.4 → v0.5 config migration (probe → plan preview → execute → verify+handoff). Bumps `config.yml: version: 2 → 3`, copies the bundled default profile into `.immutable-prd/profile.yml`, and uncomments the `profile:` pointer. Re-running on an already-migrated repo aborts cleanly. Existing `profile.yml` is preserved.
- **Profile system** — `immutable/examples/_profiles/default-{ko,en}.yml` externalize section headings, adversarial personas, 90% gate criteria, RFC 2119 keywords, identifier regex, filename conventions, and feature-flag vocabulary. Teams override selected fields by copying a default profile into their repo and pointing `config.yml: profile:` at the copy. Missing fields fall back to the matching bundled default.
- **Strings catalog** — `immutable/strings/strings.{ko,en,ja}.yml` externalize user-facing workflow prose (Stage questions, refusal messages, confirmation templates, handoff blocks). Resolution order per string: `<team_language>` → `en` → hardcoded English in SKILL.md (with one-line warning at each fallback step — never silent). `strings.ja.yml` ships as an empty scaffold; every key falls back to `en` until translated.
- **Six bundled starters** — `immutable/examples/starter/{spec,app,single}-{ko,en}/` consumed by `/immutable:init`. File counts: spec = 5, app = 3, single = 7.
- **Config schema v3** — adds an optional `profile: <path>` field. v2 configs (without `profile:`) continue to work unchanged; the plugin auto-loads the bundled default matching `team_language`.
- **`validate_docs.py --strict-body`** — opt-in CI check that every `profile.adr.sections[].required == true` entry appears as an `##` heading in each ADR body. Off by default for backward compatibility with v0.4 ADRs authored before the profile system existed.

### Changed

- **`validate_docs.py` is now profile-aware**. The hardcoded filename regex is replaced with `profile.naming.filename_pattern`. The hardcoded `_global` special-case is replaced with `profile.domain_allowlist.reserved_domains[].adr_only`. v2 configs auto-load the bundled `default-<team_language>.yml` profile — no config bump required.
- **`/immutable:prd` and `/immutable:adr` SKILL.md** are now profile-aware AND catalog-aware. Section headings, persona names/questions/checks, gate criteria, identifier regex, and filename rules are looked up from the active profile rather than hardcoded into the skill text. Stage questions, refusal messages, confirmation templates, and handoff blocks are looked up from the strings catalog. Inline Korean prose has been removed.
- **`marketplace.json`** registers `./init` and `./migrate` skill paths in addition to `./prd` and `./adr`. Plugin description and keywords expanded to surface the new bootstrap and migration capabilities.
- **`SCHEMA.md`** documents the v3 config field, the profile system (Profile resolution order, reference profiles, when to fork vs. override), the strings catalog (resolution order, responsibility split with profiles, key naming convention), the v0.4 → v0.5 migration paths, and the rewritten validation invariants 5–8.

### Migration (v0.4 → v0.5)

- **Zero-action path (recommended for most teams)** — install v0.5 and keep `version: 2` in your existing `.immutable-prd/config.yml`. The plugin auto-loads the bundled default profile that matches your `team_language` (`ko` → `default-ko.yml`, `en` → `default-en.yml`). Behavior is identical to v0.4.
- **Graduate to v3** — run `/immutable:migrate` to bump `version: 2 → 3`, seed `.immutable-prd/profile.yml` from the bundled default, and uncomment the `profile:` pointer. Idempotent and zero-data-loss. After migration, edit only the fields you want to diverge from the default — unedited fields continue to fall back to the bundled default.
- **Compatibility window** — v0.5–v0.7 accept `version: 2` without complaint. v0.8 will warn, and a later release will require `/immutable:migrate`. No deprecations in v0.5.

### Deprecated

None. The hardcoded `_global` special-case in the v0.4 validator is replaced by the profile-driven `domain_allowlist.reserved_domains[].adr_only` flag, but the `_global` ADR scope itself is preserved (it is now declared in the bundled default profiles).

### Removed

None.

### Fixed

None.

## [0.4.0]

Single-plugin merge: the v0.3 two-plugin layout (`immutable-prd` + `immutable`) was unified into one `immutable` plugin. One install, one enable step, consistent `/immutable:*` namespace. Behavior, schema, and config format unchanged from v0.3.

## [0.3.0]

Append-only foundation: dropped four of the v0.2 companion doc types (`design`, `tech-spec`, `status`, `supersede`) — duplicated against pitch / Figma / code or derivable from PR state and feature flags. ADRs relocated from the spec repo into the app repo. `/immutable:prd` absorbed pitch supersession; cross-doc cascades are rare with two doc types.

## [0.2.0] and earlier

Pre-public iterations — see `git log` for history.

[0.5.4]: https://github.com/choi88andys/skills/releases/tag/immutable--v0.5.4
[0.5.3]: https://github.com/choi88andys/skills/releases/tag/v0.5.3
[0.5.2]: https://github.com/choi88andys/skills/releases/tag/v0.5.2
[0.5.1]: https://github.com/choi88andys/skills/releases/tag/v0.5.1
[0.5.0]: https://github.com/choi88andys/skills/releases/tag/v0.5.0
[0.4.0]: https://github.com/choi88andys/skills/releases/tag/v0.4.0
[0.3.0]: https://github.com/choi88andys/skills/releases/tag/v0.3.0
