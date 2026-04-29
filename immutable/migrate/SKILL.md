---
name: migrate
description: Migrate .immutable-prd/config.yml from config schema v2 to v3 AND migrate team profile.yml field schema (v1 to v2 in v0.5.7+). Bumps versions, copies the bundled default profile when missing, uncomments the profile pointer, and merges new schema fields into existing team profiles preserving overrides. Idempotent and zero-data-loss. Use when graduating a v0.4 repo to the v0.5 profile system or when picking up a plugin update that bumped profile_schema. Triggers - "/immutable:migrate", "v3 업그레이드", "profile 전환", "config migrate", "profile schema migration".
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
license: MIT
---

# /immutable:migrate — Config + Profile Schema Migration

Two responsibilities (added in v0.5.7):

1. **Config migration** (`.immutable-prd/config.yml` v2 → v3) — bumps `version`, seeds `.immutable-prd/profile.yml` from bundled default, uncomments `profile:` pointer.
2. **Profile field migration** (`profile.yml` `profile_schema: 1` → `2` and beyond) — adds new schema fields introduced by plugin updates while **preserving all team overrides**. Never modifies values that already exist in the team profile.

The operation is idempotent and zero-data-loss across both responsibilities. Re-running on a fully-migrated repo aborts cleanly. Existing `profile.yml` content is never overwritten — only missing fields are inserted.

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

## Overall Process (6 stages, v0.5.7+)

```
Stage 1: Probe              — walk-up config.yml, read version + team_language; probe profile schema if profile.yml exists
Stage 2: Plan preview        — render config + profile migration plan, confirm with user
Stage 3: Execute config      — copy profile (if needed) + edit config.yml (skipped when config already v3)
Stage 4: Verify config       — confirm config + profile.yml exist
Stage 5: Profile field migration — merge missing schema fields into team profile.yml, bump profile_schema (skipped when team profile is current)
Stage 6: Final verify + handoff — show result, suggest commit
```

**Stop on user refusal at any stage.** Partial execution is forbidden — either the planned operations land or the skill aborts before touching anything.

### Stage routing matrix

| Initial state | Stages run |
|---|---|
| config v2 + no team profile.yml | 1 → 2 → 3 → 4 → 5 (profile is fresh from bundled, schema check passes — Stage 5 no-ops) → 6 |
| config v2 + team profile.yml exists (edge — manually created) | 1 → 2 → 3 (3.1 skip-warn) → 4 → 5 (merge missing fields if schema stale) → 6 |
| config v3 + team profile_schema < bundled | 1 → 2 (Stage 2 plan shows profile migration only) → 5 → 6. Stages 3+4 skipped. |
| config v3 + team profile_schema == bundled | 1 refuses with `migrate.stage1.fully_current` |
| config v3 + no team profile.yml | 1 refuses with `migrate.stage1.profile_missing` (suggests one-liner copy or `/immutable:init` rerun) |

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

### 1.3 Probe profile schema (v0.5.7+)

After parsing config.yml, determine the team profile state:

1. Resolve team profile path:
   - If config has `profile: <path>` (uncommented) → that path resolved relative to repo root
   - Else default `<repo_root>/.immutable-prd/profile.yml`
2. If team profile file does NOT exist:
   - When config version is 2 → profile will be created in Stage 3.1 (no profile schema work needed in Stage 5; bundled default ships current schema).
   - When config version is 3 → STOP by rendering `migrate.stage1.profile_missing` with `{profile_dest_path}` and the suggested one-liner. The repo is in an inconsistent state (config was migrated but profile was deleted).
3. If team profile file exists:
   - Read it. Extract `profile_schema:` (integer; default to `1` if missing).
   - Read bundled default profile (`${CLAUDE_PLUGIN_ROOT}/examples/_profiles/default-<team_language>.yml`). Extract its `profile_schema:` (integer).
   - Cache both values for Stages 2 and 5: `team_profile_schema`, `bundled_profile_schema`.

### 1.4 Already-migrated routing

Combine config version + profile schema state into the routing decision:

| Config version | Team profile schema | Action |
|---|---|---|
| 2 | (any or absent) | Run Stage 2-3-4 (config migration), then Stage 5 (profile migration if needed) |
| 3 | < bundled | SKIP Stage 3-4. Run Stage 2 (plan) → Stage 5 (profile migration only) → Stage 6 |
| 3 | == bundled | STOP — render `migrate.stage1.fully_current` with `{config_path}`, `{profile_path}`, `{profile_schema}` |
| 3 | > bundled | STOP — render `migrate.stage1.profile_ahead_of_plugin` with `{team_profile_schema}`, `{bundled_profile_schema}`. Likely the user installed an older plugin version after a newer one. Suggest plugin update. |
| Other (parse failure or unsupported value) | — | Hardcoded English error and abort. |

`migrate.stage1.already_v3` from v0.5.6 is REPLACED by the matrix above. v0.5.6 callers wired only to that key get a fallback rendering of `migrate.stage1.fully_current`.

### 1.5 Switch locale

Once `team_language` is known, all subsequent catalog lookups (Stages 2–6) use `strings.<team_language>.yml` as the primary source.

---

## Stage 2 — Plan preview

Render a combined plan covering both config migration (when needed) and profile field migration (when needed). Always confirm before executing.

### 2.1 Compute substitutions

- `{current_version}` — config version parsed in Stage 1.2.
- `{target_version}` — literal `3` (always, when config migration is in scope).
- `{profile_source_path}` — `${CLAUDE_PLUGIN_ROOT}/examples/_profiles/default-<team_language>.yml`. Render with the expanded absolute path when available; otherwise render the `${CLAUDE_PLUGIN_ROOT}/…` form verbatim.
- `{profile_dest_path}` — `<repo_root>/.immutable-prd/profile.yml`.
- `{team_profile_schema}` / `{bundled_profile_schema}` — from Stage 1.3 (when team profile.yml exists).
- `{profile_field_diff}` — populated by 2.2 below when Stage 5 will run.

### 2.2 Compute profile field diff (when Stage 5 will run)

Apply the per-version migration recipes (see Stage 5.2 below) against the team profile to enumerate **specific fields that will be added**. Each entry in `{profile_field_diff}` names the field path and a one-line description. Example:

```
+ sections[user_stories].max_items: 3 (anti-monolith hard cap)
+ anti_monolith block (3-tier escalation L1/L2/L3)
+ vague_words list (Stage 3 vague-word detection)
+ personas[quality_auditor] (4th adversarial persona)
+ gate.criteria[concern_scope] + gate.total/threshold bump
+ adr.anti_monolith block
```

Fields already present in the team profile are NOT listed (they are preserved; never modified).

### 2.3 Render preview

Render the appropriate template based on the routing matrix from Stage 1.4:

| Stages running | Catalog key |
|---|---|
| Config + Profile (full) | `migrate.stage2.plan_preview_full` |
| Profile only (config already v3) | `migrate.stage2.plan_preview_profile_only` |
| Config only (no profile field migration needed — fresh profile copy) | `migrate.stage2.plan_preview_config_only` |

All three templates accept `{profile_field_diff}` (rendered as empty when not applicable).

Ask the user to reply `yes` / `no` (or equivalents: `진행`, `proceed`, `go`).

### 2.4 Handle decline

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

## Stage 4 — Verify config (when Stage 3 ran)

### 4.1 Verify

Read the updated config.yml and confirm:

- `version: 3` is present.
- `profile: .immutable-prd/profile.yml` (uncommented) is present.
- `<repo_root>/.immutable-prd/profile.yml` exists and is non-empty.

If any assertion fails, surface the failure to the user with a hardcoded English message and suggest `git restore .immutable-prd/config.yml && rm .immutable-prd/profile.yml` as rollback. Do NOT proceed to Stage 5.

### 4.2 Decision

- If Stage 5 will run (per Stage 1.4 routing) → continue to Stage 5.
- Else → skip directly to Stage 6 handoff.

---

## Stage 5 — Profile field migration (v0.5.7+, conditional, v0.5.8+ universal diff)

Add fields introduced by newer plugin versions into the team profile.yml. **Existing values are never modified.** Only missing fields are inserted. Idempotent.

**v0.5.7 → v0.5.8 change**: replaced per-version recipe enumeration with a universal structural diff algorithm (5.2 below). The recipe approach was easy to miss fields (the v0.5.7 recipe omitted `sections[user_stories].structure`, requiring a v0.5.8 fix). The universal diff compares the team profile's structure against the bundled default's structure and identifies every additive difference automatically — no recipe maintenance needed when future plugin versions add new fields.

### 5.1 Pre-conditions

- Team profile.yml exists (Stage 1.3 verified this).
- `team_profile_schema < bundled_profile_schema` (Stage 1.4 routed here).

### 5.2 Universal structural diff (v0.5.8+ — replaces per-version recipes)

The skill computes the diff between the team profile and the bundled default **dynamically** by walking both YAML structures and identifying additive-only differences. This eliminates per-version recipes and ensures any field added in any future plugin version is automatically picked up.

#### 5.2.1 Algorithm

1. Parse both files as YAML mappings.
2. Walk the bundled default's structure top-down. For each key encountered:

   | Bundled has | Team has | Action |
   |---|---|---|
   | mapping | absent | mark for ADD: insert entire bundled subtree at end of file (with header comments) |
   | mapping | mapping | recurse into nested keys |
   | mapping | scalar / sequence | leave team value alone (type mismatch — user override is authoritative) |
   | scalar | absent | mark for ADD: insert key+value at correct nesting position |
   | scalar | scalar | leave team value alone (override preservation) |
   | sequence (id-keyed) | absent | mark for ADD: insert entire bundled list (with header comments) |
   | sequence (id-keyed) | sequence (id-keyed) | for each bundled element by `id`/`key`: if not in team → mark for ADD as entry append; if in team → recurse into its nested fields |
   | sequence (id-keyed) | sequence (anonymous) | leave team value alone (type mismatch) |
   | sequence (anonymous) | absent | mark for ADD: insert entire bundled list |
   | sequence (anonymous) | sequence (any) | leave team value alone (no safe identity for element-level merge) |

3. Output a flat list of additions: `(yaml_path, value, source_comment_block)`.

#### 5.2.2 Sequence type detection

A sequence is **id-keyed** when every element is a mapping containing either an `id` field or a `key` field (used by `normative_keywords`). Examples in current bundled defaults: `sections`, `personas`, `gate.criteria`, `adr.sections`, `adr.personas`, `adr.gate.criteria`, `vague_words`, `identifier_patterns`, `normative_keywords`, `domain_allowlist.reserved_domains`, `naming.forbidden_slug_patterns`.

A sequence is **anonymous** when its elements are scalars (strings/numbers) or when elements lack a stable identifier. Examples: `feature_flag.states` (`[deployed, hidden]`), `feature_flag.required_fields` (`[key, states, ...]`), `personas[*].checks` (lists of free-form strings).

When in doubt, treat as anonymous (preserve team value entirely). The cost is "team misses bundled additions to that list" — acceptable per override-preservation principle.

#### 5.2.3 Override preservation guarantees

The algorithm enforces these invariants:

- **Scalars in team profile are never modified.** If team has `min_items: 2` and bundled has `min_items: 1`, team keeps `2`.
- **Existing id-keyed entries are recursively merged but never replaced.** If team has `personas[product_lead]` with old `checks: [a, b]` and bundled has updated `checks: [a, b, c, d]`, team keeps `[a, b]` (anonymous list — preserved entirely; no per-element diff).
- **Anonymous lists are preserved entirely.** No element-level merging.
- **Comments in the team profile are never touched** (Edit operations only insert new blocks; existing text untouched).
- **Description / heading text edits in bundled defaults do not propagate.** Teams who explicitly customized those keep their text.

#### 5.2.4 Worked example: v1 → v2 transition (current dogfood case)

A v1 team profile (v0.5.0-era) running through the algorithm against the v2 bundled default-ko:

```
ADD top-level: vague_words[*]                 (entire list — locale-specific hedge words)
ADD top-level: anti_monolith                  (3-tier escalation block + header comment)
ADD nested:    sections[user_stories].max_items: 3
ADD nested:    sections[user_stories].structure: per_story_grouped
ADD entry:     personas[quality_auditor]      (4th adversarial persona)
ADD entry:     gate.criteria[concern_scope]   (8th gate criterion)
ADD nested:    adr.anti_monolith              (ADR-side block)
SKIP modify:   sections[user_stories].min_items (team has 2, bundled has 1 — preserve team)
SKIP modify:   sections[edge_cases].min_items   (same)
SKIP modify:   personas[product_lead].checks    (anonymous list — preserve team)
SKIP modify:   personas[customer_support].checks (anonymous list — preserve team)
SKIP modify:   gate.total / gate.pass_threshold  (scalars — preserve team)
SKIP modify:   sections[user_stories].description (scalar text update — preserve team)
```

This example is **descriptive, not prescriptive** — the algorithm above is the source of truth. Future v2→v3 transitions will produce their own diff list automatically without any update to this SKILL.md.

#### 5.2.5 Schema bump

After the diff is collected, plan one final addition:

- Replace exactly `profile_schema: <team_value>` with `profile_schema: <bundled_value>`. This is the only IN-PLACE modification the algorithm performs and it is bound to the schema version field specifically (the file's "I am at version X" marker).
- If the comment immediately above `profile_schema:` is the bundled stock text for the team's old version, update the comment to reflect the bumped version range. Skip the comment update if the user has customized those comment lines (heuristic: any non-stock comment content within the 5 lines before `profile_schema:`).

### 5.3 Plan preview (when Stage 5 is the only stage running)

Already shown in Stage 2 (which renders the structural diff output from 5.2). Skip re-rendering — proceed to 5.4.

### 5.4 Execute additions

For each addition from 5.2's diff list:

1. Run a Grep against the team profile to confirm the field is still missing (defensive — handles the rare case where the user edited the file between Stage 2 and Stage 5).
2. If missing: use Edit to insert the new content at the position dictated by the addition's yaml_path and type:
   - **Top-level mapping/sequence** (`anti_monolith`, `vague_words`, etc.) — append at end of file, preceded by a blank line, including the bundled default's header comment block (lines prefixed with `#` immediately above the key in the bundled file).
   - **Nested scalar** (`sections[user_stories].max_items`, `.structure`) — use Edit with enough surrounding context to make the match unique (typically the entry's `id:` line plus the preceding field acts as anchor). Include inline comments from bundled when present.
   - **Id-keyed sequence entry append** (`personas[quality_auditor]`, `gate.criteria[concern_scope]`) — use Edit matching the last entry of the sequence as old_string, replace with `<last_entry> + blank_line + new_entry`. Preserve YAML indentation.
   - **Nested mapping under id-keyed entry** (e.g., a new field inside `sections[user_stories]`) — Edit matching the entry's id declaration as anchor, insert the new field at the natural position.
3. If present (race condition / already-merged): SKIP and note in handoff. Do NOT abort.

If any Edit fails (old_string not found or not unique), abort the stage with `migrate.stage5.edit_failure` pointing at the specific addition and suggesting manual merge from `${CLAUDE_PLUGIN_ROOT}/examples/_profiles/default-<lang>.yml`. Do NOT continue with further additions — leave the profile in a consistent partial state and let the user inspect.

### 5.5 Bump schema and verify

After all additions land:

1. Edit `profile_schema:` line per 5.2.5.
2. Read the updated profile.yml fully (no Grep-only check — a full Read catches any structural damage).
3. Confirm the bumped `profile_schema` value matches `bundled_profile_schema`.
4. Confirm each planned addition is now present (Grep checks for top-level keys and id-keyed entry ids).
5. Confirm the file still parses as valid YAML (re-run the skill's internal parser against the updated content).

If verification fails, surface the failure with the specific failing assertion and suggest rollback (`git restore .immutable-prd/profile.yml`).

---

## Stage 6 — Final verify + handoff

### 6.1 Combined verify

Re-run all assertions from Stage 4.1 (when Stage 3 ran) and Stage 5.5 (when Stage 5 ran). All must pass.

### 6.2 Handoff

Render `migrate.stage6.handoff` with:

- `{config_path}` — absolute path of config.yml.
- `{profile_path}` — absolute path of profile.yml.
- `{stages_run}` — list of stages that actually executed (e.g., "config v2→v3; profile_schema 1→2 with 6 additions").
- `{post_migration_notes}` — when Stage 5 added `concern_scope`, include the one-line note about manually bumping `gate.total` / `gate.pass_threshold` if the team wants the criterion to count.
- `{commit_suggestion}` — `git add .immutable-prd/ && git commit -m "chore: migrate immutable plugin to <vN>"`.

---

## Hard Prohibitions

1. **Never run git operations.** `git add`, `git commit`, `git restore` are user-only. Only suggest commands.
2. **Never overwrite an existing profile.yml content.** Stage 3.1 skips file creation if it exists. Stage 5 only INSERTS missing fields — never modifies existing values, even when the bundled default differs.
3. **Never edit files outside `.immutable-prd/`.** Pitches, ADRs, READMEs, templates are untouched.
4. **Never proceed past Stage 1 when fully current.** The skill aborts cleanly when both config and profile schema are at the bundled defaults.
5. **Never proceed past Stage 2 without explicit user confirmation.** No auto-execute.
6. **Never leave the repo in a partially-migrated state.** Either the planned operations all land (with documented skips for 3.1 / 3.3 / 5.4-individual-addition idempotency) or the skill aborts before touching anything.
7. **Never modify the bundled starter / profile files.** They live in the plugin (read-only).
8. **Never change existing profile.yml values in Stage 5.** The migration adds missing fields only. Default value changes (e.g., `min_items: 2 → 1` in v0.5.6 defaults) are NOT propagated — teams who set explicit values likely want them.

---

## Idempotency contract

Re-running `/immutable:migrate` on a repo at various states (per the Stage 1.4 routing matrix):

| Prior state | Behavior |
|---|---|
| `version: 3` + profile_schema == bundled | Stage 1 refusal (`migrate.stage1.fully_current`) |
| `version: 3` + profile_schema < bundled | Stage 5 only — adds missing fields, bumps schema |
| `version: 3` + profile.yml missing | Stage 1 refusal (`migrate.stage1.profile_missing`) — user runs one-liner copy if desired |
| `version: 3` + profile_schema > bundled | Stage 1 refusal (`migrate.stage1.profile_ahead_of_plugin`) — suggests plugin update |
| `version: 2` + no profile.yml | Full Stage 2-3-4-5-6 — config bump + profile copy from bundled (which is current schema) + Stage 5 no-op |
| `version: 2` + profile.yml exists (edge — manually created) | Full Stage 2-3-4-5-6 — config bump + Stage 3.1 skip-warn + Stage 5 merge if schema stale |
| Stage 5 partially run before (some fields added but schema not yet bumped) | Defensive Grep checks in Stage 5.4 detect already-present additions and SKIP them. Schema bump in 5.5 lands. |

This contract means `/immutable:migrate` is safe to re-run in CI / automation without guard conditions.

---

## Rollback

If the user decides to undo a completed migration:

```bash
# Undo a config v2 → v3 migration (full):
git restore .immutable-prd/config.yml
rm .immutable-prd/profile.yml

# Undo a Stage 5 profile field migration only (config v3 was already in place):
git restore .immutable-prd/profile.yml
```

Both rollback variants are safe because `/migrate` never touches files outside `.immutable-prd/`.

---

## Credits

- Walk-up detection mirrors `scripts/find_config.sh` + `validate_docs.py`.
- Plan-then-confirm pattern mirrors `/immutable:init` Stage 2.
