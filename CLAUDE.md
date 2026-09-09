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

- **A new skill must be registered in BOTH `skills` arrays — `immutable/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`.** Skills live at the plugin root, not under `skills/`, so nothing is discovered by convention. The marketplace array serves marketplace installs; the plugin.json array serves every other load path — `claude --plugin-dir`, a `.zip`. Missing the first shipped v0.6.2 with five unregistered skills; missing the second made `--plugin-dir` load zero skills (and, because a same-named `--plugin-dir` plugin shadows the installed one, removed `/immutable:*` from the session) until v0.11.0, while `claude plugin validate` passed. `bash immutable/scripts/plugin_manifest.test.sh` checks both against the directories on disk.
- **`immutable/.claude-plugin/plugin.json`'s `description` and `keywords` are mirrored verbatim into `.claude-plugin/marketplace.json`.** Edit one, edit the other; `plugin_manifest.test.sh` is the only check.
- **Dogfood a branch with `claude --plugin-dir <checkout>/immutable`, never by releasing.** It loads the directory directly (no cache copy) and wins over the installed `immutable@skills` for that session; SKILL.md edits are live, `hooks/` and manifest edits need `/reload-plugins`.
- **`immutable/strings/strings.en.yml` and `strings.ko.yml` must stay at key parity.** A key present in `en` but missing from `ko` does not error — it silently falls back to the English string, so a Korean team (the `team_language` default) reads English. This shipped as a real bug in v0.7.4 and was fixed in v0.7.6.
- **`immutable/strings/strings.ja.yml` is a deliberate scaffold holding zero keys**, designed to fall back to English wholesale. Do not "fix" its parity against `en`.
- **`immutable/scripts/validate_docs.py` validates a consumer's SDD repo** (its `pitches/` and ADRs), not this plugin's own source. Running it here checks nothing.
