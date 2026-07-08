# CLAUDE.md — choi88andys/skills

Repo language is English: commits, `CHANGELOG.md`, PR bodies, and this file.

## Release procedure

Gitflow. `develop` integrates unreleased work; `main` is what marketplace clients pull.

1. Branch off `develop` → PR → **squash-merge** into `develop`.
2. **`--no-ff`** merge `develop` → `main`, message `Merge branch 'develop' into main for vX.Y.Z release`. Push `main` directly — develop→main takes no PR.
3. Tag the `main` merge commit and push the tag. That fires `.github/workflows/release.yml`, which creates a GitHub Release titled `vX.Y.Z` (the workflow strips only the `immutable--` prefix, so the `v` stays).

Use a **lightweight** tag — `git tag immutable--vX.Y.Z <sha>`, never `git tag -a`. Every release tag is a commit object, and `release.yml` calls `gh release create --generate-notes`, which never reads a tag message.

`develop` is never merged back from `main`; it stays at the last feature squash.

The version is declared once, in `immutable/.claude-plugin/plugin.json`. The changelog is `immutable/CHANGELOG.md` — there is no top-level one, and `.claude-plugin/marketplace.json` carries no version field.

## Gotchas

- **A new skill must be registered in `.claude-plugin/marketplace.json`'s `skills` array.** Creating `immutable/<name>/SKILL.md` is not enough, and nothing fails loudly — v0.6.2 shipped with five unregistered skills.
- **`immutable/.claude-plugin/plugin.json`'s `description` is mirrored verbatim into `.claude-plugin/marketplace.json`.** Edit one, edit the other; no check enforces it.
- **`immutable/strings/strings.en.yml` and `strings.ko.yml` must stay at key parity.** A key present in `en` but missing from `ko` does not error — it silently falls back to the English string, so a Korean team (the `team_language` default) reads English. This shipped as a real bug in v0.7.4 and was fixed in v0.7.6.
- **`immutable/strings/strings.ja.yml` is a deliberate scaffold holding zero keys**, designed to fall back to English wholesale. Do not "fix" its parity against `en`.
- **`immutable/scripts/validate_docs.py` validates a consumer's SDD repo** (its `pitches/` and ADRs), not this plugin's own source. Running it here checks nothing.
