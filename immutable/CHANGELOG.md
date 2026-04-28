# Changelog — immutable plugin

All notable changes to the `immutable` plugin are documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the plugin follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Version is canonically declared in `.claude-plugin/plugin.json`.

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
