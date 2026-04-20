---
name: migrate
description: Migrate .immutable-prd/config.yml from config schema v2 to v3 — bumps version, copies the bundled default profile into .immutable-prd/profile.yml, and uncomments the `profile:` pointer. Idempotent and zero-data-loss. Use when graduating a v0.4 repo to the v0.5 profile system. Triggers - "/immutable:migrate", "v3 업그레이드", "profile 전환", "config migrate".
allowed-tools: Read, Write, Edit, Bash, Glob
license: MIT
---

# /immutable:migrate — v2 → v3 Config Migration

Upgrades an existing `.immutable-prd/config.yml` from schema v2 to v3, seeds a repo-local profile by copying the bundled default, and activates the `profile:` pointer. The operation is idempotent and zero-data-loss: already-migrated repos abort cleanly, and an existing `profile.yml` is preserved.

Never runs git. Never writes outside the repo. Never modifies pitches, ADRs, READMEs, or templates.

## Strings catalog & locale (v0.5 / S3+)

All user-facing prompts are sourced from `${CLAUDE_PLUGIN_ROOT}/strings/strings.<locale>.yml` — not embedded inline. SKILL.md refers to catalog keys via the pattern ``render `<key>` `` with single-brace `{placeholder}` substitution performed by the skill.

**Locale resolution**:
- Stage 1 reads `team_language` from the existing config.yml. That becomes the primary locale for all subsequent stages.
- If config.yml is missing or unreadable, fall back to `en` (the Stage 1 refusal still renders correctly).

**Resolution fallback** (per string lookup):
1. `strings.<team_language>.yml` (primary)
2. `strings.en.yml` (fallback — emit one-line warning via `common.fallback_warning`, never silent)
3. Hardcoded last-resort English in this SKILL.md (plugin file corruption; emit warning and abort the stage)

See `../SCHEMA.md#strings-catalog-v05-s3` for the schema, responsibility split, and key naming convention.

## Preconditions

- Current working directory is inside (or is the root of) an immutable SDD repo.
- `.immutable-prd/config.yml` exists, reachable via walk-up from CWD.
- `${CLAUDE_PLUGIN_ROOT}` is set by Claude Code when invoking plugin skills. If unset (rare), fall back to walking up from the skill's own location.

## Invocation

```
/immutable:migrate
```

No arguments. The skill auto-detects repo state.

---

## Overall Process (4 stages)

```
Stage 1: Probe              — walk-up config.yml, read version + team_language
Stage 2: Plan preview        — render plan, confirm with user
Stage 3: Execute             — copy profile + edit config.yml
Stage 4: Verify + handoff    — show result, suggest commit
```

**Stop on user refusal at any stage.** Partial execution is forbidden — either the whole migration lands or nothing does.

---

## Stage 1 — Probe

### 1.1 Locate config.yml

Walk up from CWD until `.immutable-prd/config.yml` is found or the `.git` boundary is reached:

```bash
current="$(pwd)"
while :; do
  candidate="$current/.immutable-prd/config.yml"
  [ -f "$candidate" ] && { echo "$candidate"; break; }
  [ -d "$current/.git" ] && { echo "NOT_FOUND"; break; }
  parent="$(dirname "$current")"
  [ "$parent" = "$current" ] && { echo "NOT_FOUND"; break; }
  current="$parent"
done
```

If the walk-up returns `NOT_FOUND`, STOP by rendering `migrate.stage1.not_initialized` (no substitutions). Do not proceed.

### 1.2 Parse version + team_language

Read the discovered config.yml via Read. Extract two values:

- `version:` — integer, expected `2` or `3`.
- `team_language:` — short locale key (`ko`, `en`, `ja`, …). Used to pick the bundled profile.

If the file fails to parse (malformed YAML) or `version:` / `team_language:` is missing, abort with a hardcoded English error message (plugin state should never allow this; this is a last-resort guard):

```
error: could not read `version:` or `team_language:` from {config_path}. Fix the YAML manually and rerun `/immutable:migrate`.
```

### 1.3 Already-migrated refusal

If `version: 3` (or any value other than `2`), STOP by rendering `migrate.stage1.already_v3` with:

- `{config_path}` — the absolute path discovered in 1.1
- `{current_version}` — the parsed version value

Do not proceed past Stage 1 in this case.

### 1.4 Switch locale

Once `team_language` is known, all subsequent catalog lookups (Stages 2–4) use `strings.<team_language>.yml` as the primary source.

---

## Stage 2 — Plan preview

Compute the four path/value placeholders and present the plan. Always confirm before executing.

### 2.1 Compute substitutions

- `{current_version}` — parsed in Stage 1.2 (always `2` when we reach Stage 2).
- `{target_version}` — literal `3`.
- `{profile_source_path}` — `${CLAUDE_PLUGIN_ROOT}/examples/_profiles/default-<team_language>.yml`. Render with the expanded absolute path when available; otherwise render the `${CLAUDE_PLUGIN_ROOT}/…` form verbatim.
- `{profile_dest_path}` — `<repo_root>/.immutable-prd/profile.yml` where `<repo_root>` is the parent of the `.immutable-prd/` directory holding config.yml.

### 2.2 Render preview

Render `migrate.stage2.plan_preview` with the substitutions above. Ask the user to reply `yes` / `no` (or equivalents — free-text acceptance is OK: `진행`, `proceed`, `go`).

### 2.3 Handle decline

If the user declines, STOP by rendering `migrate.stage2.user_declined` (no substitutions). Do not touch any files.

---

## Stage 3 — Execute

Perform the three changes in order. Each step is idempotent — if the target state is already reached, skip + warn.

### 3.1 Copy bundled profile → repo

1. Source: `${CLAUDE_PLUGIN_ROOT}/examples/_profiles/default-<team_language>.yml`
2. Destination: `<repo_root>/.immutable-prd/profile.yml`

If destination exists with non-empty content:
- SKIP the copy.
- Render `migrate.stage3.profile_exists_warning` with `{profile_dest_path}`.
- Proceed to 3.2 (version bump must still happen for idempotency).

Otherwise:
- Read source via Read tool, Write to destination.

### 3.2 Edit config.yml — version bump

Use Edit to replace exactly:

```
version: 2
```

with:

```
version: 3
```

Match must be unique — config.yml has exactly one `version:` line. If Edit reports the old_string is not unique (e.g., a comment line matches), abort with a hardcoded English error:

```
error: `version: 2` line ambiguous in {config_path}. Inspect the file manually and rerun.
```

### 3.3 Edit config.yml — uncomment profile pointer

Use Edit to replace exactly:

```
# profile: .immutable-prd/profile.yml
```

with:

```
profile: .immutable-prd/profile.yml
```

If the commented line is missing (custom-edited config — user already uncommented it, or they wrote a different path), SKIP this edit and note it in the Stage 4 handoff. Do not abort — this still leaves the repo in a working state (version is bumped, profile.yml exists, user's manual config wins).

---

## Stage 4 — Verify + handoff

### 4.1 Verify

Read the updated config.yml and confirm:

- `version: 3` is present.
- `profile: .immutable-prd/profile.yml` (uncommented) is present.
- `<repo_root>/.immutable-prd/profile.yml` exists and is non-empty.

If any assertion fails, surface the failure to the user with a hardcoded English message and suggest `git restore .immutable-prd/config.yml && rm .immutable-prd/profile.yml` as rollback.

### 4.2 Handoff

Render `migrate.stage4.handoff` with:

- `{config_path}` — absolute path of the edited config.yml.
- `{profile_path}` — absolute path of the copied (or pre-existing) profile.yml.

---

## Hard Prohibitions

1. **Never run git operations.** `git add`, `git commit`, `git restore` are user-only. Only suggest commands.
2. **Never overwrite an existing profile.yml.** If it exists, warn + skip copy (Stage 3.1).
3. **Never edit files outside `.immutable-prd/`.** Pitches, ADRs, READMEs, templates are untouched.
4. **Never proceed past Stage 1 when `version: 3`.** The skill handles only the v2 → v3 transition.
5. **Never proceed past Stage 2 without explicit user confirmation.** No auto-execute.
6. **Never leave the repo in a partially-migrated state.** Either all three changes land (with documented skips for 3.1 / 3.3) or the skill aborts before touching anything.
7. **Never modify the bundled starter / profile files.** They live in the plugin (read-only).

---

## Idempotency contract

Re-running `/immutable:migrate` on a repo that already completed migration:

| Prior state | Behavior |
|---|---|
| `version: 3` + profile.yml exists | Stage 1 refusal (`migrate.stage1.already_v3`) |
| `version: 3` + profile.yml missing | Stage 1 refusal — user runs the one-liner from the refusal message to copy profile.yml if they want one |
| `version: 2` + profile.yml exists (edge case) | Stage 3.1 skip + warn, Stage 3.2 bumps version, Stage 3.3 uncomments pointer. Final state matches a normal migration. |

This contract means `/immutable:migrate` is safe to re-run in CI / automation without guard conditions.

---

## Rollback

If the user decides to undo a completed migration:

```bash
git restore .immutable-prd/config.yml
rm .immutable-prd/profile.yml
```

This restores config.yml to its v2 form and removes the seeded profile. Safe because migrate never touches files outside `.immutable-prd/`.

---

## Credits

- Walk-up detection mirrors `scripts/find_config.sh` + `validate_docs.py`.
- Plan-then-confirm pattern mirrors `/immutable:init` Stage 2.
