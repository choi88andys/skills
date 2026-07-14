---
name: init
description: Bootstrap a new immutable SDD repo by copying a starter from the plugin into the current directory. Detects empty vs existing repo, helps select mode (spec / app / single) + team language + profile handling, copies the matching starter, and emits next-step git commands. Use when starting a new immutable SDD project or adding immutable configuration to an existing project. Triggers - "/immutable:init", "immutable 시작", "SDD 부트스트랩", "새 spec 레포".
allowed-tools: Read, Write, Bash, Glob, Grep
license: MIT
---

# /immutable:init — Bootstrap an Immutable SDD Repo

Copies one of six bundled starters into the current directory and emits handoff commands. Never overwrites existing files. Never runs git operations.

## Strings catalog & locale (v0.5 / S3)

All user-facing prompts are sourced from `${CLAUDE_PLUGIN_ROOT}/strings/strings.<locale>.yml` — not embedded inline. SKILL.md refers to catalog keys via the pattern ``render `<key>` `` with single-brace `{placeholder}` substitution performed by the skill.

**Locale resolution**:
- Stages 1–2 run BEFORE `team_language` is selected. Default to `ko` unless the free-text invocation argument contains `english` / `en` / `English` (case-insensitive) — in which case default to `en`.
- Stage 3 asks the user to confirm `team_language`. All subsequent stages render from the chosen catalog.

**Resolution fallback** (per string lookup):
1. `strings.<team_language>.yml` (primary)
2. `strings.en.yml` (fallback — emit one-line warning via `common.fallback_warning`, never silent)
3. Hardcoded last-resort English in this SKILL.md (plugin file corruption; emit warning and abort the stage)

See `../SCHEMA.md#strings-catalog-v05-s3` for the schema, responsibility split, and key naming convention.

## Preconditions

- Current working directory is where the user wants the repo bootstrapped (do NOT `cd` elsewhere).
- Plugin starter files are accessible via `${CLAUDE_PLUGIN_ROOT}/examples/starter/<mode>-<lang>/`. Claude Code sets `CLAUDE_PLUGIN_ROOT` when invoking plugin skills. If unset (rare), fall back to walking up from the skill's own location.

## Invocation

```
/immutable:init
```

Optional free-text initial context (mode / language hint):

```
/immutable:init spec-only Korean
/immutable:init single-repo English
```

Free-text is parsed for hints only — the skill still walks Stages 2–4 to confirm.

---

## Overall Process (7 stages)

```
Stage 1: Environment Probe        — detect CWD state, suggest mode
Stage 2: Mode Selection           — spec / app / single, with default from probe
Stage 3: Language Selection       — ko / en (default ko)
Stage 4: Profile Mode             — bundled default / repo-local override / skip
Stage 5: File Copy                — starter → CWD, no-overwrite
Stage 6: Git Init Suggestion      — only if .git absent
Stage 7: Handoff                  — next-step commands
```

**Stop on user refusal at any stage.** No partial copies on cancellation.

---

## Stage 1 — Environment Probe

Use Bash + Glob + Read to inspect the CWD. Report findings before asking anything.

### 1.1 Probe checklist

| Signal | Detection | Implies |
|---|---|---|
| `.git/` present | `[ -d .git ]` | Existing git repo — skip Stage 6 git init suggestion |
| `.immutable-prd/config.yml` present | `[ -f .immutable-prd/config.yml ]` | Already initialized — STOP (1.3) |
| `pitches/` present | `[ -d pitches ]` | Spec-side already started (suggest `two-repo-spec`) |
| `adr/` present | `[ -d adr ]` | App-side already started (suggest `two-repo-app`) |
| `lib/`, `src/`, `app/` present | any of the three | App code (suggest `two-repo-app` or `single-repo`) |
| Both `pitches/` and code dirs present | combination | Suggest `single-repo` |
| Empty (only `README.md` or none) | dir listing | Empty bootstrap (suggest `two-repo-spec`) |

Run the checks in parallel:

```bash
[ -d .git ] && echo "git: yes" || echo "git: no"
[ -f .immutable-prd/config.yml ] && echo "immutable: initialized" || echo "immutable: not initialized"
ls -lA 2>/dev/null | head -30
```

### 1.2 Report findings

Render `init.stage1.probe_summary` with the following substitutions:

- `{git_status}` — `init.probe.status_present` if `.git/` exists, else `init.probe.status_absent`
- `{immutable_status}` — `init.probe.immutable_with_config` if `.immutable-prd/config.yml` exists, else `init.probe.status_absent`
- `{detected_dirs}` — comma-joined list of `"<dir>/ <status>"` pairs for the probed directories (`pitches`, `adr`, `lib`/`src`/`app`), using the same present/absent tokens
- `{recommended_mode}` — one of `two-repo-spec` / `two-repo-app` / `single-repo`
- `{recommendation_reason}` — one-line justification derived from the probe outcome (e.g., "empty dir", "pitches/ + lib/ coexist")

### 1.3 Already-initialized refusal

If `.immutable-prd/config.yml` exists, STOP by rendering `init.stage1.already_initialized` (no substitutions). Do not proceed past Stage 1 in this case.

---

## Stage 2 — Mode Selection

Show all three options with the probe's recommendation marked. Always confirm with the user — never auto-select.

Render `init.stage2.mode_question` with:
- `{recommended_number}` — `1` / `2` / `3` corresponding to the probe's recommended mode
- `{recommendation_reason}` — one-line justification (same phrasing as Stage 1.2)

If the user passed a free-text hint matching one of the modes (e.g., "spec-only", "app", "single"), pre-fill the recommendation but still confirm.

If the user picks an option that conflicts with the probe (e.g., picks `two-repo-spec` when `lib/` exists), render `init.stage2.mode_conflict_warning` with:
- `{chosen_mode}` — the selected mode key
- `{detected_dirs}` — alternatives joined with `common.separator.list_comma`
- `{suggested_alternatives}` — human-readable alternative modes joined with `common.separator.or`

---

## Stage 3 — Language Selection

Render `init.stage3.language_question` (no substitutions). This stage sets `team_language` in config.yml AND determines which starter is copied (`<mode>-<lang>`). The plugin loads the matching default profile (`default-ko.yml` or `default-en.yml`) at /immutable:prd / /immutable:adr invocation time.

**Locale switchover**: once the user confirms their choice, all subsequent catalog lookups (Stages 4–7) use `strings.<team_language>.yml` as the primary source.

---

## Stage 4 — Profile Mode

Render `init.stage4.profile_question` (no substitutions).

### Branch handling

- **(1) bundled default**: leave config.yml's `profile:` line as a comment (it's already commented in the starter). No additional file copy.
- **(2) repo-local copy**: copy `${CLAUDE_PLUGIN_ROOT}/examples/_profiles/default-<lang>.yml` → `<CWD>/.immutable-prd/profile.yml`, then edit the copied config.yml to uncomment the `profile: .immutable-prd/profile.yml` line. After the copy, render `init.stage4.repo_local_hint` (no substitutions).
- **(3) skip**: identical to (1) for v0.5 (the comment stays as documentation). After confirming, render `init.stage4.skip_hint` with `{lang}` = `team_language`.

---

## Stage 5 — File Copy

Source: `${CLAUDE_PLUGIN_ROOT}/examples/starter/<mode>-<lang>/`
Destination: CWD (always — never `cd` elsewhere)

### 5.1 Enumerate source files

```bash
src="${CLAUDE_PLUGIN_ROOT}/examples/starter/<mode>-<lang>"
[ -d "$src" ] || { echo "starter not found at $src"; exit 1; }
find "$src" -type f
```

### 5.2 Copy with no-overwrite

For each source file:

1. Compute destination = `<CWD>/<path-relative-to-src>`
2. If destination exists with non-empty content: SKIP. Append to `skipped[]` list.
3. If destination directory is missing: `mkdir -p` it.
4. Read source via Read tool, Write to destination.
5. Append to `copied[]` list.

**Implementation note**: prefer Read + Write over `cp` so the skill stays within Claude Code's tracked file operations. For empty `.gitkeep` files, run `touch <dest>` via Bash.

### 5.3 Profile-copy branch (Stage 4 = option 2)

After 5.2, additionally:

1. Read `${CLAUDE_PLUGIN_ROOT}/examples/_profiles/default-<lang>.yml`
2. Write to `<CWD>/.immutable-prd/profile.yml` (skip if exists)
3. Edit `<CWD>/.immutable-prd/config.yml`:
   - Find the line `# profile: .immutable-prd/profile.yml`
   - Replace with `profile: .immutable-prd/profile.yml` (uncomment)

### 5.4 Spec repo path interview (two-repo-app only)

**Runs only when `mode == two-repo-app`.** Other modes skip to 5.5.

Goal: replace the `spec_repo_path: ../<your-spec-repo>` placeholder with a real path at init time, so the user does not have to hand-edit config.yml after bootstrap. Works regardless of app repo naming — the interview collects the path directly from the user rather than guessing via suffix convention.

#### 5.4.1 Candidate scan (optional hint)

Scan sibling directories (one level up from CWD, non-recursive) for spec repos:

```bash
_parent="$(dirname "$(pwd)")"
for _dir in "$_parent"/*/; do
  _dir="${_dir%/}"
  [ "$_dir" = "$(pwd)" ] && continue
  _cfg="$_dir/.immutable-prd/config.yml"
  [ -f "$_cfg" ] || continue
  _mode="$(sed -n 's/^repo_mode:[[:space:]]*\([^[:space:]]*\).*/\1/p' "$_cfg" 2>/dev/null | head -1)"
  case "$_mode" in
    two-repo|two-repo-spec) echo "$_dir" ;;
  esac
done
```

Outcomes:

- **0 candidates** — no default. Render `init.stage5.spec_path_question` with `{suggestion_hint}` set to `init.stage5.spec_path_no_candidate`.
- **1 candidate** — soft default. Render `init.stage5.spec_path_question` with `{suggestion_hint}` set to `init.stage5.spec_path_suggestion` (placeholder `{path}` = the sibling's relative path like `../myproject-spec`).
- **2+ candidates** — render `init.stage5.spec_path_multiple` with `{candidate_list}` = newline-joined numbered list.

The scan is a hint only. A candidate's existence does NOT imply the user wants to pair with it — always confirm.

#### 5.4.2 User response handling

Accept any of:

- **Empty / negative response** (`skip`, `나중에`, `no`, `pass`, empty line) — set `spec_path_outcome = skipped`. Placeholder remains.
- **Numeric selection** (only when 2+ candidates listed) — map to the chosen candidate's relative path. Set `spec_path_outcome = configured` with `{spec_path}` = mapped path.
- **Absolute or relative path string** — use as-is. Set `spec_path_outcome = configured` with `{spec_path}` = user input.

Do not validate beyond the soft target-existence check below. The skill accepts any string the user types.

#### 5.4.3 Target existence check (soft warning)

When `spec_path_outcome = configured`:

1. Resolve to absolute path (absolute as-is; relative against CWD).
2. If the target directory does not exist, OR exists but lacks both `.immutable-prd/config.yml` AND `pitches/` — render `init.stage5.spec_path_missing_target` with `{path}` = the input value.
3. Do not abort. The user may be bootstrapping both repos in sequence and intends to run `/immutable:init` in the spec repo next.

#### 5.4.4 Config edit

When `spec_path_outcome = configured`:

1. Edit `<CWD>/.immutable-prd/config.yml`:
   - Find the exact line: `spec_repo_path: ../<your-spec-repo>`
   - Replace with: `spec_repo_path: <spec_path>`
2. Render `init.stage5.spec_path_set` with `{path}` = `<spec_path>`.

When `spec_path_outcome = skipped`, render `init.stage5.spec_path_skipped` (no substitutions). config.yml is left untouched.

Carry `spec_path_outcome` and `{spec_path}` forward to Stage 7 handoff selection.

### 5.5 Report

Render `init.stage5.copy_report` with:
- `{copied_count}` — integer count of files successfully copied
- `{copied_list}` — newline-joined list of relative paths, each prefixed with `  - `
- `{skipped_count}` — integer count of skipped files
- `{skipped_list}` — newline-joined list, or `common.placeholder.none` if none were skipped

If Stage 4 chose option (2) (profile copy), append `init.stage5.profile_copy_note` to the report (no substitutions).

If any file was skipped, suggest the user diff the bundled starter against their existing copy to decide whether to merge changes manually.

---

## Stage 6 — Git Init Suggestion

If `.git/` was absent in Stage 1, render `init.stage6.git_init_suggestion` (no substitutions).

If `.git/` was present, render `init.stage6.git_commit_suggestion` (no substitutions).

---

## Stage 7 — Handoff

Mode-specific next-step output. For each render, pass `{lang}` = `team_language` (`ko` or `en`).

### two-repo-spec

Render `init.stage7.handoff_two_repo_spec`.

### two-repo-app

Render one of two handoff variants based on `spec_path_outcome` from Stage 5.4:

- `spec_path_outcome = configured` — render `init.stage7.handoff_two_repo_app_configured` with `{lang}` and `{spec_path}`. Omits the placeholder-edit instruction since the path was already set interactively.
- `spec_path_outcome = skipped` — render `init.stage7.handoff_two_repo_app_pending` with `{lang}`. Retains the original "edit the placeholder" instruction for users who deferred the decision.

### single-repo

Render `init.stage7.handoff_single_repo`.

---

## Hard Prohibitions

1. **Never overwrite existing files.** If a file exists at the destination, skip + report. The user's existing content is sacred.
2. **Never run git operations.** `git init`, `git add`, `git commit` are user-only. Only suggest commands.
3. **Never commit or push.**
4. **Never write outside CWD.** All copies are to the user's current directory.
5. **Never proceed with already-initialized repos.** If `.immutable-prd/config.yml` exists, refuse and explain (Stage 1.3).
6. **Always confirm mode/language with the user before copying.** No auto-selection without explicit user agreement.
7. **Never modify the bundled starter files.** They live in the plugin (read-only).

---

## Available Starters

Six starters ship with the plugin (S2). Each is a self-contained tree the skill copies into CWD.

| Starter | Mode | Language | Purpose |
|---|---|---|---|
| `spec-ko` | two-repo-spec | ko | Korean spec repo |
| `spec-en` | two-repo-spec | en | English spec repo |
| `app-ko` | two-repo-app | ko | Korean app repo (ADRs only) |
| `app-en` | two-repo-app | en | English app repo (ADRs only) |
| `single-ko` | single-repo | ko | Korean single repo (pitches + ADRs) |
| `single-en` | single-repo | en | English single repo (pitches + ADRs) |

Each starter is copied whole by Stage 5.1's `find "$src" -type f`, which enumerates the dotfiles — `.gitignore`, `.immutable-prd/config.yml`, `.github/workflows/validate-docs.yml` — too; nothing in Stage 5 filters dot-directories.

Additional locales (`ja`, etc.) added without schema changes — drop a new starter directory and a new `default-<locale>.yml` profile.

---

## Credits

- Design pattern: marketplace-bundled starter directories, common in modern CLI tooling (e.g., `npm init`, `cargo new`, `poetry new`).
- No source files copied. Patterns referenced only.
