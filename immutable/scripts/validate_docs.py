#!/usr/bin/env python3
"""validate_docs.py — stand-alone validator for immutable SDD repos.

Checks the invariants documented in SCHEMA.md for a repo that adopts the
two-doc-type model: `pitch` (spec repo) + `adr` (app repo).

Designed to run:

  * from a pre-commit hook or CI workflow
  * from a future `/immutable:adr --validate` skill mode

Coverage (matches SCHEMA.md "Validation invariants"):

  1. `config.yml` parses and has required keys for the declared `repo_mode`.
  2. Each doc's frontmatter parses and contains required fields.
  3. Referenced pitch filenames resolve to an existing file (in this repo for
     spec/single-repo mode, in the spec repo declared by `spec_repo_path` for
     app-repo mode — see `resolve_pitches_for_reference` for how a *relative*
     `spec_repo_path` is resolved when the validator runs from a linked git
     worktree).
  4. Reference policy — ADR `references.pitches` non-empty unless the domain is
     declared `adr_only` in the profile's `domain_allowlist.reserved_domains`
     (e.g., `_global`).
  5. Domain allowlist — `pitches/README.md` rows, with reserved-domain
     special-cases sourced from the profile.
  6. Filename format — matches the profile's `naming.filename_pattern`
     (falls back to `YYYY-MM-DD-<kebab-slug>.md` when no profile is set).
  7. Supersede chain integrity — for each file with non-null `supersedes`, the
     target must exist in the same doc-type set and have `deprecated: true`.
     Multiple active files MAY coexist in the same domain (each on its own
     supersede chain). Fan-out (one predecessor superseded by N successors,
     e.g., a refactor-split) is permitted as long as the shared predecessor
     is deprecated.
  8. pitch / ADR body-level check — **optional, enabled via `--strict-body`.**
     Every `profile.sections[i].required == true` entry (pitch) and
     `profile.adr.sections[i].required == true` entry (ADR) must appear as an
     `##` heading. Additionally, when the active profile sets
     `sections[id=user_stories].structure == per_story_grouped` (v0.5.3+
     default), each pitch's user-stories H2 slice must contain ≥1 `### `
     sub-section, every sub-section must carry ≥1 bracketed normative line,
     and no bracketed normative line may leak between the H2 and the first
     `### `. Off by default to preserve backward compatibility with v0.4 repos
     authored before the profile system existed.

  9. Requirement contract (v0.11+) — `references.tickets[]` entries carry
     non-empty string `tracker` / `id` / `version` (always on); under
     `--strict-body` and the `--strict-since` scope, with the config's
     `requirement_contract.enforcement: required`, every pitch dated on or
     after `requirement_contract.since` (when set) carries a ticket reference
     or a `references.ticket_exemption`; and, once the
     config opts into the contract, a pitch's disagreement section
     (`profile.sections[id=requirement_disagreement]`) holds ≥1 `### ` entry
     whose four labelled bullets are present and whose outcome begins with a
     terminal token — a provisional outcome is a violation, which is the
     merge gate that keeps a pitch PR open until the request is settled.

Not covered (deferred): cycle detection on supersede chains.

Besides validating, `--list-active` prints the repo's active (non-deprecated)
docs — one `<absolute path>\\t<domain>` line per doc — and is the canonical
resolver behind the flow skills' active-pitch pickers (`/immutable:design`,
`/immutable:prd`, `/immutable:plan-review-ceo`). See the flag's help text for
its fail-open contract.

--- Profile awareness (v0.5 / S4) ---
This validator is profile-aware. Resolution order per run:

  1. If `config.yml` declares `profile:` and the file exists, load it.
  2. Otherwise load the bundled default matching `team_language` from
     `<plugin>/examples/_profiles/default-<lang>.yml` (relative to this script).
  3. Otherwise fall back to the hardcoded DEFAULT_* constants below.

`version: 2` and `version: 3` configs are both accepted. v2 configs trigger
step 2 automatically (bundled default profile) — zero user action required.
------------------------------------------------

Exit code 0 when clean; 1 when any check fails. Errors print to stderr.

Requires: PyYAML. Invoke with `python3 -m pip install pyyaml` if missing.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:
    sys.stderr.write(
        "validate_docs.py requires PyYAML. Install with: pip install pyyaml\n"
    )
    sys.exit(2)


# Last-resort defaults used only when profile loading fails entirely.
# Profile fields normally supply these values (see load_profile + helpers).
DEFAULT_FILENAME_REGEX = r"^\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*\.md$"
DEFAULT_RESERVED_DOMAINS: dict[str, dict[str, Any]] = {
    "_global": {"adr_only": True},
    "_shared": {"adr_only": False},
}
DEFAULT_NORMATIVE_TOKENS: list[str] = [
    "MUST NOT",
    "MUST",
    "SHOULD NOT",
    "SHOULD",
    "MAY",
]
# Longest token first for regex alternation (prevents "MUST" matching before "MUST NOT").

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
HEADING_RE = re.compile(r"^(#+) +(.+?)\s*$", re.MULTILINE)
FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
BULLET_LINE_RE = re.compile(r"^\s*[-*]\s+")
GIVEN_WHEN_THEN_RE = {
    "Given": re.compile(r"\*\*Given\*\*", re.IGNORECASE),
    "When": re.compile(r"\*\*When\*\*", re.IGNORECASE),
    "Then": re.compile(r"\*\*Then\*\*", re.IGNORECASE),
}

DOC_TYPES = ("pitch", "adr")
REPO_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
ENFORCEMENT_VALUES = ("optional", "required")
TICKET_REQUIRED_KEYS = ("tracker", "id", "version")
DISAGREEMENT_FIELDS = ("original", "correction", "reason", "outcome")
REPO_MODES = ("two-repo-spec", "two-repo-app", "single-repo")


def die(msg: str) -> None:
    sys.stderr.write(f"error: {msg}\n")
    sys.exit(1)


def warn(violations: list[str], msg: str) -> None:
    violations.append(msg)


def find_config(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    for candidate_dir in [current, *current.parents]:
        candidate = candidate_dir / ".immutable-prd" / "config.yml"
        if candidate.exists():
            return candidate
        if (candidate_dir / ".git").exists():
            return None
    return None


def load_config(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except (yaml.YAMLError, ValueError) as exc:
        # ValueError: PyYAML builds a date object for any unquoted scalar shaped
        # like one and lets `datetime` raise on `2026-13-01` — a traceback out of
        # the validator instead of a config error, for `since` and
        # `strict_body_since` alike.
        die(f"config.yml failed to parse: {exc}")
        raise AssertionError("unreachable")

    required = {"version", "repo_mode", "team_language"}
    missing = required - set(data.keys())
    if missing:
        die(f"config.yml missing required keys: {sorted(missing)}")

    repo_mode = data.get("repo_mode")
    if repo_mode not in REPO_MODES:
        die(f"config.yml repo_mode={repo_mode!r} must be one of {list(REPO_MODES)}")

    # Mode-specific requirements.
    if repo_mode == "two-repo-spec":
        if "pitches_path" not in data:
            die("config.yml repo_mode=two-repo-spec requires pitches_path")
    elif repo_mode == "two-repo-app":
        if "adr_path" not in data:
            die("config.yml repo_mode=two-repo-app requires adr_path")
    elif repo_mode == "single-repo":
        missing_paths = {"pitches_path", "adr_path"} - set(data.keys())
        if missing_paths:
            die(f"config.yml repo_mode=single-repo requires {sorted(missing_paths)}")

    # v0.11+: the optional requirement-contract block. A malformed block is
    # fatal, like a malformed cutoff — a gate that silently degrades to "off"
    # is the failure this validator exists to prevent.
    contract = data.get("requirement_contract")
    if contract is not None:
        if not isinstance(contract, dict):
            die("config.yml requirement_contract must be a mapping")
        enforcement = contract.get("enforcement", "optional")
        if enforcement not in ENFORCEMENT_VALUES:
            die(
                f"config.yml requirement_contract.enforcement must be one of "
                f"{list(ENFORCEMENT_VALUES)}, got {enforcement!r}"
            )
        repo = contract.get("repo")
        if repo is not None and not REPO_SLUG_RE.match(str(repo)):
            die(f"config.yml requirement_contract.repo must be OWNER/NAME, got {repo!r}")
        fetch_command = contract.get("fetch_command")
        if fetch_command is not None and (
            not isinstance(fetch_command, str) or not fetch_command.strip()
        ):
            die("config.yml requirement_contract.fetch_command must be a non-empty string")
        since = contract.get("since")
        if since is not None:
            validate_date_field(str(since).strip(), "config.yml requirement_contract.since")

    return data


def validate_date_field(value: str, source: str) -> str:
    """A zero-padded, real YYYY-MM-DD, or a fatal error — never a silent skip."""
    if not _DATE_RE.match(value):
        die(f"{source} must be a zero-padded YYYY-MM-DD date, got {value!r}.")
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        die(f"{source} {value!r} is not a real calendar date.")
    return value


def contract_since(contract: dict[str, Any] | None) -> str | None:
    """`requirement_contract.since` — the adoption date. Pitches whose filename
    date is before it predate the contract and are exempt from the
    `required` presence rule (they cannot cite a ticket that never bound
    them, and they are append-only). Validated in load_config."""
    if not contract or contract.get("since") is None:
        return None
    return str(contract["since"]).strip()


def config_contract(config: dict[str, Any]) -> dict[str, Any] | None:
    """The validated `requirement_contract` block, or None when the repo has
    not opted in. Callers treat None as "every contract check is a no-op"."""
    block = config.get("requirement_contract")
    return block if isinstance(block, dict) else None


def load_profile(config: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """Resolve and load the active profile for this repo.

    Resolution order:
      1. config.yml `profile:` (relative to repo_root) — load if exists.
      2. Bundled `default-<team_language>.yml` next to this script — load if exists.
      3. Empty dict — callers fall back to the DEFAULT_* module constants.

    Parse failures at steps 1–2 emit a warning and fall through to the next
    step. Missing-file at step 1 silently falls through (user may point at a
    profile that is pending creation).
    """
    profile_ref = config.get("profile")
    if profile_ref:
        candidate = (repo_root / profile_ref).resolve()
        if candidate.exists():
            try:
                with candidate.open("r", encoding="utf-8") as fh:
                    return yaml.safe_load(fh) or {}
            except yaml.YAMLError as exc:
                sys.stderr.write(
                    f"warning: profile at {candidate} failed to parse ({exc}); "
                    f"falling back to bundled default.\n"
                )

    team_lang = config.get("team_language", "en")
    script_dir = Path(__file__).resolve().parent
    bundled = script_dir.parent / "examples" / "_profiles" / f"default-{team_lang}.yml"
    if bundled.exists():
        try:
            with bundled.open("r", encoding="utf-8") as fh:
                return yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            sys.stderr.write(
                f"warning: bundled profile {bundled} failed to parse ({exc}); "
                f"using hardcoded defaults.\n"
            )

    return {}


def profile_filename_pattern(profile: dict[str, Any]) -> re.Pattern[str]:
    pattern = profile.get("naming", {}).get("filename_pattern") if profile else None
    if not pattern:
        pattern = DEFAULT_FILENAME_REGEX
    try:
        return re.compile(pattern)
    except re.error as exc:
        sys.stderr.write(
            f"warning: profile naming.filename_pattern is invalid regex ({exc}); "
            f"using built-in default.\n"
        )
        return re.compile(DEFAULT_FILENAME_REGEX)


def profile_reserved_domains(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    reserved = (
        profile.get("domain_allowlist", {}).get("reserved_domains") if profile else None
    )
    if not reserved:
        return dict(DEFAULT_RESERVED_DOMAINS)
    result: dict[str, dict[str, Any]] = {}
    for entry in reserved:
        if not isinstance(entry, dict):
            continue
        key = entry.get("id")
        if not key:
            continue
        result[key] = {"adr_only": bool(entry.get("adr_only", False))}
    return result or dict(DEFAULT_RESERVED_DOMAINS)


def _extract_required_headings(sections: Any) -> list[str]:
    if not sections:
        return []
    out: list[str] = []
    for entry in sections:
        if not isinstance(entry, dict):
            continue
        if entry.get("required") is not True:
            continue
        heading = entry.get("heading")
        if heading:
            out.append(str(heading).strip())
    return out


def profile_required_adr_headings(profile: dict[str, Any]) -> list[str]:
    sections = profile.get("adr", {}).get("sections") if profile else None
    return _extract_required_headings(sections)


def profile_required_pitch_headings(profile: dict[str, Any]) -> list[str]:
    sections = profile.get("sections") if profile else None
    return _extract_required_headings(sections)


def profile_user_stories_section(profile: dict[str, Any]) -> dict[str, Any] | None:
    """Return the `sections[id=user_stories]` entry, or None if absent.

    Used by the v0.5.3+ pitch structure guard. Callers read `heading` and
    `structure` (default `per_story_grouped`) from the returned entry.
    """
    sections = profile.get("sections") if profile else None
    if not sections:
        return None
    for entry in sections:
        if isinstance(entry, dict) and entry.get("id") == "user_stories":
            return entry
    return None


def profile_disagreement_vocabulary(profile: dict[str, Any]) -> dict[str, Any] | None:
    """What the disagreement-outcome check needs from the profile (v0.11+):
    the section heading plus field labels and outcome tokens. None when any
    of it is missing — the caller then skips the check with a warning rather
    than inventing labels."""
    if not profile:
        return None
    heading = None
    for entry in profile.get("sections") or []:
        if isinstance(entry, dict) and entry.get("id") == "requirement_disagreement":
            heading = str(entry.get("heading") or "").strip()
    block = (profile.get("requirement_contract") or {}).get("disagreement") or {}
    fields = block.get("fields") or {}
    provisional = block.get("outcome_provisional")
    terminal = block.get("outcome_terminal") or []
    if (
        not heading
        or not all(isinstance(fields.get(k), str) and fields[k].strip() for k in DISAGREEMENT_FIELDS)
        or not isinstance(provisional, str)
        or not provisional.strip()
        or not isinstance(terminal, list)
        or not terminal
    ):
        return None
    return {
        "heading": heading,
        "fields": {k: str(fields[k]).strip() for k in DISAGREEMENT_FIELDS},
        "provisional": provisional.strip(),
        "terminal": [str(t).strip() for t in terminal if str(t).strip()],
    }


def profile_normative_tokens(profile: dict[str, Any]) -> list[str]:
    """Return normative keyword tokens from the profile, longest-first.

    Longest-first ordering ensures regex alternation prefers "MUST NOT"
    over "MUST" when both appear as prefixes.
    """
    keywords = profile.get("normative_keywords") if profile else None
    if not keywords:
        return list(DEFAULT_NORMATIVE_TOKENS)
    tokens: list[str] = []
    for entry in keywords:
        if not isinstance(entry, dict):
            continue
        token = entry.get("token")
        if token:
            tokens.append(str(token))
    if not tokens:
        return list(DEFAULT_NORMATIVE_TOKENS)
    # Sort by length descending for regex alternation correctness.
    return sorted(tokens, key=len, reverse=True)


def _bracketed_normative_re(tokens: list[str]) -> re.Pattern[str]:
    """Compile `[<token>]` pattern for the given tokens.

    Matches bare `[MUST]` and markdown-emphasized `**[MUST]**` alike.
    Token match is case-sensitive; `[must]` is not a normative marker.
    """
    alternation = "|".join(re.escape(t) for t in tokens)
    return re.compile(rf"\[(?:{alternation})\]")


def _bullet_head_normative_re(tokens: list[str]) -> re.Pattern[str]:
    """Match lines where a bracketed normative token is the HEAD of a bullet.

    Accepted forms (the bracket is the first non-whitespace-non-marker content):
      - `- [MUST] …`
      - `- **[MUST]** …`
      - `  - **[MUST NOT]** …` (nested bullet)
      - `* _[SHOULD]_ …` (alternate emphasis / marker)

    Rejected forms (bracket mid-bullet = prose with inline bracket, a drift
    signal despite the line starting with a bullet marker):
      - `- 시스템은 카드를 **[MUST]** 먼저 표시한다`
      - `- The system **[MUST]** return 200 on success`
    """
    alternation = "|".join(re.escape(t) for t in tokens)
    # Leading whitespace → bullet marker (- or *) → whitespace →
    # up to 3 emphasis characters (* or _) → `[TOKEN]`.
    return re.compile(rf"^\s*[-*]\s+[\*_]{{0,3}}\[(?:{alternation})\]")


def load_frontmatter(md_path: Path) -> dict[str, Any] | None:
    text = md_path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None
    try:
        fm = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return None
    # Scalar/list frontmatter (`---\njust text\n---`) parses fine but has no
    # `.keys()`/`.get()` — letting it through crashed check_frontmatter with an
    # AttributeError instead of reporting a violation. Not-a-mapping ≙ malformed.
    if not isinstance(fm, dict):
        return None
    return fm


def resolve_dirs(config: dict[str, Any], repo_root: Path) -> dict[str, Path | None]:
    """Resolve directories for each doc type this repo hosts.

    Pitches for app-repo mode are resolved via spec_repo_path for reference checks;
    they are not iterated (the app repo doesn't own pitches).
    """
    mode = config["repo_mode"]
    result: dict[str, Path | None] = {"pitch": None, "adr": None}

    if mode in ("two-repo-spec", "single-repo"):
        result["pitch"] = repo_root / config["pitches_path"]
    if mode in ("two-repo-app", "single-repo"):
        result["adr"] = repo_root / config["adr_path"]

    return result


def main_worktree_root(repo_root: Path) -> Path | None:
    """Root of the MAIN checkout, when `repo_root` is a LINKED git worktree.

    Returns None when git is unavailable, `repo_root` is not a git repo, or the
    checkout already IS the main worktree — in every one of those cases the
    caller keeps its worktree-relative resolution untouched.

    `git worktree list --porcelain` is preferred over `rev-parse
    --git-common-dir`: it always lists the main worktree first and always as an
    absolute path, whereas `--git-common-dir` prints a *relative* `.git` when run
    from the main checkout, and its parent is not the checkout root at all under
    `git init --separate-git-dir` or inside a submodule.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        # git missing, not a repo, or git errored — no main checkout to fall back on.
        return None

    first_line = proc.stdout.splitlines()[0] if proc.stdout else ""
    prefix = "worktree "
    if not first_line.startswith(prefix):
        return None
    main_root = Path(first_line[len(prefix) :]).resolve()
    if main_root == repo_root.resolve():
        return None  # main checkout — the fallback candidate would be identical
    return main_root


def resolve_pitches_for_reference(
    config: dict[str, Any], repo_root: Path
) -> tuple[Path | None, str | None]:
    """Pitches directory used for `references.pitches` existence checks.

    Returns `(pitches_root, error)`:

      * `(path, None)` — resolved; check each `references.pitches` entry against it.
      * `(None, None)` — existence check opted out (app repo declaring no
        `spec_repo_path`). Unchanged behaviour.
      * `(None, error)` — `spec_repo_path` IS declared but no candidate resolves.
        The caller reports `error` once, naming every path tried, instead of
        letting every ADR emit a `file not found` against a phantom directory.

    Spec-repo / single-repo: same as the local pitches dir.
    App-repo: `spec_repo_path` + `pitches_path_in_spec`.

    A *relative* `spec_repo_path` means "the spec repo sits next to my repo". Run
    from a linked git worktree, `repo_root` is the worktree — not the repo — so
    `../` lands somewhere else entirely unless the worktree happens to be a
    sibling of the main checkout. Candidates are therefore tried worktree-first
    (so a spec repo genuinely beside the worktree keeps winning, and no existing
    layout changes behaviour), then relative to the main checkout. An *absolute*
    `spec_repo_path` carries no such ambiguity and is used as-is.
    """
    mode = config["repo_mode"]
    if mode in ("two-repo-spec", "single-repo"):
        return repo_root / config["pitches_path"], None
    # app-repo
    spec_repo = config.get("spec_repo_path")
    if not spec_repo:
        return None, None  # existence not validated; user opted out
    pitches_sub = config.get("pitches_path_in_spec", "pitches/")

    is_relative = not Path(spec_repo).is_absolute()
    candidates = [(repo_root / spec_repo).resolve()]
    if is_relative:
        linked_from = main_worktree_root(repo_root)
        if linked_from is not None:
            candidates.append((linked_from / spec_repo).resolve())

    tried: list[Path] = []
    for spec_root in candidates:
        pitches_root = spec_root / pitches_sub
        if pitches_root.is_dir():
            return pitches_root, None
        tried.append(pitches_root)

    # The worktree hint applies to relative paths only — printing it under an
    # absolute spec_repo_path would point the reader at machinery that never ran.
    hint = (
        " (A relative spec_repo_path is resolved against this checkout first, then "
        "against the main checkout when this is a linked git worktree.)"
        if is_relative
        else ""
    )
    return None, (
        f"spec_repo_path `{spec_repo}` + pitches_path_in_spec `{pitches_sub}` "
        f"does not resolve to an existing directory, so `references.pitches` "
        f"cannot be checked. Tried: {', '.join(str(p) for p in tried)}.{hint}"
    )


def domain_allowlist(pitches_root: Path | None) -> set[str]:
    if pitches_root is None:
        return set()
    readme = pitches_root / "README.md"
    if not readme.exists():
        return set()
    allow: set[str] = set()
    for line in readme.read_text(encoding="utf-8").splitlines():
        # matches rows like: | `notice` | description |
        m = re.match(r"^\|\s*`([a-z][a-z0-9_-]*)`\s*\|", line)
        if m:
            allow.add(m.group(1))
    return allow


def iter_docs(doc_root: Path, doc_type: str) -> list[Path]:
    if not doc_root.exists():
        return []
    pattern = "**/*.md" if doc_type == "pitch" else "*.md"
    return [
        p
        for p in doc_root.glob(pattern)
        if p.is_file() and p.name not in ("README.md", "TEMPLATE.md")
    ]


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FILENAME_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-")


def resolve_strict_since(
    args: argparse.Namespace, config: dict[str, Any]
) -> str | None:
    """The `--strict-body` date cutoff: CLI `--strict-since` wins, else config
    `strict_body_since`, else None.

    A malformed value is fatal. A silently-ignored cutoff would let `--strict-body`
    quietly check every file (or, read the other way, none) — the exact
    silent-degradation this validator exists not to have.
    """
    raw = (
        args.strict_since
        if args.strict_since is not None
        else config.get("strict_body_since")
    )
    if raw is None:
        return None
    cutoff = str(raw).strip()
    source = (
        "--strict-since"
        if args.strict_since is not None
        else "config strict_body_since"
    )
    return validate_date_field(cutoff, source)


def strict_body_in_scope(path: Path, cutoff: str | None) -> bool:
    """Whether `path` is subject to `--strict-body` checks under `cutoff`.

    `cutoff` (YYYY-MM-DD) grandfathers legacy: a file is in scope only when its
    filename date is on or after the cutoff, so structure can be enforced on new
    docs without editing append-only history. No cutoff → every file is in scope
    (the pre-v0.9 behaviour, unchanged). A filename with no leading date is
    fail-closed to IN scope — it cannot dodge the check by being unparseable, and
    the filename-format invariant reports the malformed name on its own. Both
    dates are zero-padded YYYY-MM-DD, so the string compare is chronological.
    """
    if cutoff is None:
        return True
    m = _FILENAME_DATE_RE.match(path.name)
    if not m:
        return True
    return m.group(1) >= cutoff


def check_filename(
    path: Path,
    filename_pattern: re.Pattern[str],
    violations: list[str],
) -> None:
    if not filename_pattern.match(path.name):
        warn(
            violations,
            f"filename format violation: {path} (expected pattern: {filename_pattern.pattern})",
        )


def check_frontmatter(
    path: Path,
    doc_type: str,
    fm: dict[str, Any] | None,
    violations: list[str],
) -> dict[str, Any]:
    if fm is None:
        warn(violations, f"{path}: missing or malformed YAML frontmatter")
        return {}

    required = {"supersedes", "deprecated"}
    if doc_type != "pitch" or "type" in fm:
        required.add("type")
    required.add("domain")  # both pitch and adr need domain
    missing = required - set(fm.keys())
    if missing:
        warn(violations, f"{path}: frontmatter missing fields: {sorted(missing)}")

    if "deprecated" in fm and not isinstance(fm["deprecated"], bool):
        warn(violations, f"{path}: `deprecated` must be a boolean")

    if fm.get("type") and fm["type"] != doc_type:
        warn(
            violations,
            f"{path}: frontmatter type={fm['type']!r} conflicts with directory-inferred type={doc_type!r}",
        )
    return fm


def check_domain(
    path: Path,
    fm: dict[str, Any],
    doc_type: str,
    allow: set[str],
    reserved: dict[str, dict[str, Any]],
    violations: list[str],
) -> None:
    domain = fm.get("domain")
    if domain is None:
        warn(violations, f"{path}: missing frontmatter `domain`")
        return
    if domain in reserved:
        if reserved[domain].get("adr_only") and doc_type != "adr":
            warn(
                violations,
                f"{path}: `{domain}` domain is reserved for ADRs; got doc_type={doc_type}",
            )
        return
    if allow and domain not in allow:
        warn(
            violations,
            f"{path}: domain {domain!r} not in pitches/README.md allowlist",
        )


def check_references(
    path: Path,
    fm: dict[str, Any],
    doc_type: str,
    pitches_ref_root: Path | None,
    reserved: dict[str, dict[str, Any]],
    violations: list[str],
) -> None:
    refs = fm.get("references") or {}
    listed = refs.get("pitches") or []
    if not isinstance(listed, list):
        warn(violations, f"{path}: references.pitches must be a list")
        return

    # Reference policy: ADR must have ≥1 pitch unless its domain is declared
    # `adr_only` in the profile's reserved-domain list (e.g., _global).
    if doc_type == "adr" and not listed:
        domain = fm.get("domain")
        is_adr_only_reserved = (
            domain in reserved and reserved[domain].get("adr_only")
        )
        if not is_adr_only_reserved:
            warn(
                violations,
                f"{path}: ADR references.pitches must be non-empty "
                f"(or use an ADR-only reserved domain like `_global`)",
            )

    # Existence check (pitches only — v0.3 doesn't model adrs/designs/tech_specs refs).
    if pitches_ref_root is None:
        return  # caller opted out of existence check (e.g., app repo without spec_repo_path)
    for value in listed:
        matches = list(pitches_ref_root.glob(f"**/{value}"))
        if not matches:
            warn(
                violations,
                f"{path}: references.pitches file not found: {value} (searched {pitches_ref_root})",
            )


def check_ticket_references(
    path: Path,
    fm: dict[str, Any],
    doc_type: str,
    violations: list[str],
) -> None:
    """Shape of `references.tickets` / `references.ticket_exemption` (v0.11+).

    Always on, for pitches: a ticket record that lacks its version coordinate
    cannot be drift-checked, and a validator that accepts it would let the
    contract silently degrade to "some ticket, some time".
    """
    if doc_type != "pitch":
        return
    refs = fm.get("references") or {}
    if not isinstance(refs, dict):
        return  # check_references already reports non-list pitches; keep one voice
    tickets = refs.get("tickets")
    if tickets is not None:
        if not isinstance(tickets, list):
            warn(violations, f"{path}: references.tickets must be a list")
        else:
            for i, entry in enumerate(tickets):
                if not isinstance(entry, dict):
                    warn(violations, f"{path}: references.tickets[{i}] must be a mapping")
                    continue
                missing = [
                    k for k in TICKET_REQUIRED_KEYS
                    if not isinstance(entry.get(k), (str, int)) or not str(entry.get(k)).strip()
                ]
                if missing:
                    warn(
                        violations,
                        f"{path}: references.tickets[{i}] missing non-empty {missing} "
                        f"(a record without its version coordinate cannot be drift-checked)",
                    )
    exemption = refs.get("ticket_exemption")
    if exemption is not None and (not isinstance(exemption, str) or not exemption.strip()):
        warn(violations, f"{path}: references.ticket_exemption must be a non-empty reason string")


def check_ticket_presence(path: Path, fm: dict[str, Any], violations: list[str]) -> None:
    """`enforcement: required` — a pitch cites a ticket or says why it cannot.
    Runs under --strict-body within the --strict-since scope AND, when the
    config sets `requirement_contract.since`, only for pitches dated on or
    after it — the strict-since window is about body structure and typically
    predates contract adoption, so without its own cutoff the presence rule
    would retroactively fail every pitch written between the two dates."""
    refs = fm.get("references") or {}
    if not isinstance(refs, dict):
        refs = {}
    tickets = refs.get("tickets")
    exemption = refs.get("ticket_exemption")
    has_ticket = isinstance(tickets, list) and len(tickets) > 0
    has_exemption = isinstance(exemption, str) and bool(exemption.strip())
    if not has_ticket and not has_exemption:
        warn(
            violations,
            f"{path}: requirement_contract.enforcement is `required` but the pitch "
            f"records neither references.tickets nor references.ticket_exemption",
        )


def _labelled_bullet_re(label: str) -> re.Pattern[str]:
    """`- **<label>** <text>` — optional emphasis around the label, optional
    colon after it; the label itself is matched literally."""
    return re.compile(
        rf"^\s*[-*]\s+[\*_]{{0,3}}{re.escape(label)}[\*_]{{0,3}}\s*[:：]?\s*(.*)$"
    )


def validate_pitch_disagreement_outcomes(
    path: Path,
    vocab: dict[str, Any],
    violations: list[str],
) -> None:
    """The requirement-contract merge gate (v0.11+).

    When the disagreement section (H2 == `vocab["heading"]`) exists, it must
    hold ≥1 `### ` entry, and every entry must carry the four labelled bullets
    with an outcome that BEGINS with a terminal token. An outcome beginning
    with the provisional token is a violation: the request it records is still
    open, so the pitch may not merge yet. Runs under --strict-body within the
    --strict-since scope.
    """
    text = path.read_text(encoding="utf-8")
    fm_match = FRONTMATTER_RE.match(text)
    body = text[fm_match.end():] if fm_match else text
    body = FENCED_CODE_RE.sub("", body)
    lines = body.splitlines()

    target = vocab["heading"]
    slice_start: int | None = None
    slice_end = len(lines)
    for idx, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if not m:
            continue
        level = len(m.group(1))
        title = m.group(2).strip()
        if slice_start is None:
            if level == 2 and title == target:
                slice_start = idx
        elif level <= 2:
            slice_end = idx
            break
    if slice_start is None:
        return  # no disagreement → nothing to gate

    slice_lines = lines[slice_start + 1 : slice_end]
    entries: list[tuple[int, str]] = []
    for idx, line in enumerate(slice_lines):
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) == 3:
            entries.append((idx, m.group(2).strip()))

    issues: list[str] = []
    if not entries:
        issues.append(f"`## {target}` — section present but holds no `### ` entry")

    fields = vocab["fields"]
    field_res = {k: _labelled_bullet_re(v) for k, v in fields.items()}
    provisional = vocab["provisional"]
    terminal = vocab["terminal"]
    for e_i, (e_start, e_title) in enumerate(entries):
        e_end = entries[e_i + 1][0] if e_i + 1 < len(entries) else len(slice_lines)
        found: dict[str, str] = {}
        for line in slice_lines[e_start + 1 : e_end]:
            for key, pattern in field_res.items():
                if key in found:
                    continue
                m = pattern.match(line)
                if m:
                    found[key] = m.group(1).strip()
                    break
        missing = [fields[k] for k in DISAGREEMENT_FIELDS if k not in found]
        if missing:
            issues.append(f"### {e_title} — missing bullet(s): {', '.join(missing)}")
        outcome = found.get("outcome")
        if outcome is None:
            continue
        if outcome.startswith(provisional):
            issues.append(
                f"### {e_title} — outcome is `{provisional}` (correction request still open); "
                f"settle it as one of {terminal} before merging"
            )
        elif not any(outcome.startswith(t) for t in terminal):
            issues.append(
                f"### {e_title} — outcome must begin with one of {terminal} "
                f"(or `{provisional}` while open); got: {outcome[:60]}"
            )

    if issues:
        bullet = "\n  - " + "\n  - ".join(issues)
        warn(violations, f"{path}: requirement-contract disagreement violation:{bullet}")


def validate_pitch_user_stories_structure(
    path: Path,
    user_stories_heading: str,
    normative_tokens: list[str],
    violations: list[str],
) -> None:
    """Enforce `per_story_grouped` internal layout in a pitch body (v0.5.3+).

    Runs only for pitch doctype, under `--strict-body`, and only when the
    active profile sets `sections[id=user_stories].structure == per_story_grouped`.

    Checks:
      * User-stories H2 slice contains ≥2 `### ` sub-sections (matches
        `profile.sections[user_stories].min_items = 2`).
      * Every `### ` sub-section contains ≥1 bracketed normative keyword line
        on a **bullet-list line** (`^\s*[-*]\s+`). Inline paragraph
        normative is flagged separately as a drift signal.
      * No bracketed normative line leaks between the H2 and the first `### `.

    Not enforced here (by design, to allow legitimate cross-cutting groups):
    presence of a GWT triple inside every sub-section. Section-level
    "≥2 GWT blocks total" is enforced by the Stage 5 gate, not this guard.
    """
    text = path.read_text(encoding="utf-8")
    fm_match = FRONTMATTER_RE.match(text)
    body = text[fm_match.end():] if fm_match else text
    body = FENCED_CODE_RE.sub("", body)
    lines = body.splitlines()

    target = user_stories_heading.strip()
    slice_start: int | None = None
    slice_end: int = len(lines)
    for idx, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if not m:
            continue
        level = len(m.group(1))
        title = m.group(2).strip()
        if slice_start is None:
            if level == 2 and title == target:
                slice_start = idx
        else:
            if level == 2:
                slice_end = idx
                break

    if slice_start is None:
        # Required-sections guard already reports the missing H2.
        return

    slice_lines = lines[slice_start + 1 : slice_end]

    # Collect `### ` sub-section positions (index within slice_lines).
    sub_positions: list[tuple[int, str]] = []
    for idx, line in enumerate(slice_lines):
        m = HEADING_RE.match(line)
        if m and len(m.group(1)) == 3:
            sub_positions.append((idx, m.group(2).strip()))

    bracket_re = _bracketed_normative_re(normative_tokens)
    bullet_head_re = _bullet_head_normative_re(normative_tokens)
    issues: list[str] = []

    if not sub_positions:
        issues.append(f"`## {target}` — no `### ` sub-sections found")
    elif len(sub_positions) < 2:
        issues.append(
            f"`## {target}` — only {len(sub_positions)} `### ` sub-section "
            f"(need ≥2; profile.sections[user_stories].min_items)"
        )
    else:
        # Leakage: any bracketed normative between H2 and first `### `.
        # Leakage check includes both bullet and inline paragraph lines.
        first_sub_idx = sub_positions[0][0]
        for idx in range(first_sub_idx):
            if bracket_re.search(slice_lines[idx]):
                leaked = slice_lines[idx].strip()
                issues.append(
                    f"(between `## {target}` and first `### `) — "
                    f"normative line leaked outside sub-section: {leaked}"
                )
                break  # one example is enough to trigger the violation

        # Each sub-section must carry ≥1 bullet-HEAD bracketed normative.
        # Lines where the bracket appears mid-bullet ("- 시스템은 카드를 **[MUST]**
        # 먼저 표시한다") or in a plain paragraph are flagged as inline drift.
        for sub_i, (sub_start, sub_title) in enumerate(sub_positions):
            sub_end = (
                sub_positions[sub_i + 1][0]
                if sub_i + 1 < len(sub_positions)
                else len(slice_lines)
            )
            block_lines = slice_lines[sub_start + 1 : sub_end]
            has_bullet_head_normative = False
            inline_normative_examples: list[str] = []
            for line in block_lines:
                if not bracket_re.search(line):
                    continue
                stripped = line.strip()
                if stripped.startswith("#"):
                    # heading line — skip (headers with tokens are a different anti-pattern)
                    continue
                if bullet_head_re.match(line):
                    has_bullet_head_normative = True
                else:
                    inline_normative_examples.append(stripped)

            if not has_bullet_head_normative:
                issues.append(
                    f"### {sub_title} — missing normative line "
                    f"(must be a bullet item beginning with the bracket, "
                    f"like `- **[MUST]** …`)"
                )
            # Report at most the first 2 inline offenders per sub-section for
            # message brevity; one or two examples are enough to localize.
            for inline in inline_normative_examples[:2]:
                excerpt = inline if len(inline) <= 80 else inline[:77] + "..."
                issues.append(
                    f"### {sub_title} — inline-position normative "
                    f"(bracket must be at the head of its bullet): {excerpt}"
                )

    if issues:
        bullet = "\n  - " + "\n  - ".join(issues)
        warn(
            violations,
            f"{path}: user-stories structure violation "
            f"(profile structure=per_story_grouped):{bullet}",
        )


def validate_body_headings(
    path: Path,
    doc_type: str,
    required_headings: list[str],
    violations: list[str],
) -> None:
    """Check that every profile-required section appears as an H2 heading.

    Shared by pitch and ADR body checks. Fenced code blocks are stripped
    before heading detection so literal `##` in example code does not
    false-match. Heading comparison is exact after strip() — users who
    customize headings update the profile, so the profile's
    `sections[i].heading` is the authoritative string.
    """
    if not required_headings:
        return
    text = path.read_text(encoding="utf-8")
    fm_match = FRONTMATTER_RE.match(text)
    body = text[fm_match.end():] if fm_match else text
    body = FENCED_CODE_RE.sub("", body)

    found_h2: set[str] = set()
    for match in HEADING_RE.finditer(body):
        level = len(match.group(1))
        if level == 2:
            found_h2.add(match.group(2).strip())

    label = "ADR" if doc_type == "adr" else "pitch"
    for heading in required_headings:
        if heading not in found_h2:
            warn(
                violations,
                f"{path}: missing required {label} section `## {heading}` "
                f"(profile-driven body check)",
            )


def check_supersede_chain_integrity(
    doc_type: str,
    docs: list[tuple[Path, dict[str, Any]]],
    violations: list[str],
) -> None:
    """Enforce per-edge supersede integrity.

    For each file F with non-null F.supersedes:
      - The target T must exist in this doc-type set, in the same domain
        directory as F (cross-domain supersede is not supported by the
        directory convention).
      - T must have `deprecated: true`.

    No global per-(domain, type) cap. Multiple active files may coexist in the
    same domain — each on its own supersede chain. Fan-out (one predecessor
    superseded by N successors, e.g., a refactor-split) is permitted as long
    as the shared predecessor is deprecated.

    Lookup is scoped by (domain, filename) since the same filename (e.g.,
    `2026-04-16-initial.md`) may legitimately appear in multiple domain
    directories.
    """
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for path, fm in docs:
        domain = fm.get("domain") or "_global"
        by_key[(domain, path.name)] = fm

    for path, fm in docs:
        target = fm.get("supersedes")
        if target is None:
            continue
        domain = fm.get("domain") or "_global"
        key = (domain, target)
        if key not in by_key:
            warn(
                violations,
                f"{path}: supersedes `{target}` but target file not found in "
                f"{doc_type} set under domain `{domain}`",
            )
            continue
        target_fm = by_key[key]
        if target_fm.get("deprecated") is not True:
            warn(
                violations,
                f"{path}: supersedes `{target}` but target is still active "
                f"(deprecated: false). Predecessor must be deprecated when a "
                f"successor exists.",
            )


def list_active_docs(
    dirs: dict[str, Path | None],
    types: tuple[str, ...],
    domain_filter: str | None,
    as_json: bool,
) -> int:
    """`--list-active`: print active (non-deprecated) docs, one per line.

    Plain output is `<absolute path>\\t<domain>` (domain `-` when unknown),
    sorted by path within each doc type; `--json` emits
    `{"active": [{"path", "domain", "doc_type"}]}`.

    A doc is excluded ONLY on a positively parsed `deprecated: true` — the same
    real-YAML-parse semantics the rest of this validator (and the read gate in
    `deprecated_read_guard.sh`) uses. This is the resolver behind the flow
    skills' active-pitch pickers, replacing per-skill `grep` filters that were
    wrong in both directions: `deprecated: True` / `deprecated:  true` are live
    YAML a grep for '^deprecated: true' reads as ACTIVE, and a fenced example
    body line starting `deprecated: true` reads as DEPRECATED.

    The lister's contract is that a live doc is never silently dropped, so a
    doc whose frontmatter is missing or malformed is LISTED (fail-open) with a
    warning on stderr — including under `--domain`, since an unknown domain
    cannot be proven not to match. Plain validation reports the underlying
    frontmatter defect; this mode only enumerates.

    Exit 0 even when the list is empty — emptiness is an answer, not an error.
    """
    rows: list[dict[str, Any]] = []
    for doc_type in types:
        doc_root = dirs.get(doc_type)
        if doc_root is None:
            continue
        for md_path in sorted(iter_docs(doc_root, doc_type)):
            fm = load_frontmatter(md_path)
            if fm is not None and fm.get("deprecated") is True:
                continue
            domain = fm.get("domain") if fm is not None else None
            domain = str(domain) if domain is not None else None
            if fm is None:
                sys.stderr.write(
                    f"warning: {md_path}: frontmatter missing or malformed — "
                    f"listed as active with unknown domain (fail-open, so a "
                    f"live doc cannot be silently dropped). Run validation to "
                    f"surface the underlying defect.\n"
                )
            elif domain is None and domain_filter is not None:
                sys.stderr.write(
                    f"warning: {md_path}: no `domain` in frontmatter — listed "
                    f"despite --domain {domain_filter} (unknown domain cannot "
                    f"be proven not to match).\n"
                )
            if (
                domain_filter is not None
                and domain is not None
                and domain != domain_filter
            ):
                continue
            rows.append(
                {"path": str(md_path), "domain": domain, "doc_type": doc_type}
            )

    if as_json:
        print(json.dumps({"active": rows}))
    else:
        for row in rows:
            print(f"{row['path']}\t{row['domain'] or '-'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to .immutable-prd/config.yml (auto-detected if omitted).",
    )
    parser.add_argument(
        "--type",
        choices=[*DOC_TYPES, "all"],
        default="all",
        help="Restrict validation to a single doc type. Default: all.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON summary instead of human-readable text.",
    )
    parser.add_argument(
        "--strict-body",
        action="store_true",
        help=(
            "Also check that each pitch and ADR body contains every "
            "profile-required section heading as H2. Default: off "
            "(backward-compatible with v0.4 repos authored before the "
            "profile system existed)."
        ),
    )
    parser.add_argument(
        "--strict-since",
        metavar="YYYY-MM-DD",
        help=(
            "With --strict-body, apply body-level checks ONLY to files whose "
            "filename date is on or after this cutoff; older files are exempt. "
            "Lets a repo enforce structure on new docs without rewriting "
            "append-only legacy. Overrides the config `strict_body_since` field."
        ),
    )
    parser.add_argument(
        "--list-active",
        action="store_true",
        help=(
            "List active (non-deprecated) docs instead of validating: one line "
            "per doc, `<absolute path>` TAB `<domain>`, sorted; with --json, a "
            "{'active': [...]} object. A doc is excluded only on a positively "
            "parsed `deprecated: true` frontmatter (real YAML parse, never a "
            "text grep); one with missing or malformed frontmatter is listed "
            "with domain `-` and a stderr warning, so a live doc is never "
            "silently dropped. Lists only doc types this config's repo owns; "
            "narrow with --type / --domain. Exits 0 even when empty."
        ),
    )
    parser.add_argument(
        "--domain",
        metavar="NAME",
        help=(
            "With --list-active, keep only docs whose frontmatter `domain` "
            "matches. Docs whose domain is unknown (missing or malformed "
            "frontmatter) are still listed — see --list-active."
        ),
    )
    args = parser.parse_args()

    config_path = args.config or find_config()
    if config_path is None:
        die(
            "could not find .immutable-prd/config.yml via walk-up. "
            "Pass --config explicitly or run from within a configured repo."
        )
    assert config_path is not None
    config = load_config(config_path)
    strict_since = resolve_strict_since(args, config)

    repo_root = config_path.parent.parent
    profile = load_profile(config, repo_root)
    filename_pattern = profile_filename_pattern(profile)
    reserved = profile_reserved_domains(profile)
    required_headings_by_type: dict[str, list[str]] = {
        "adr": profile_required_adr_headings(profile) if args.strict_body else [],
        "pitch": profile_required_pitch_headings(profile) if args.strict_body else [],
    }

    # v0.5.3+: when the profile marks user_stories as per_story_grouped, the
    # strict-body check enforces the sub-section layout for pitches.
    user_stories_section = profile_user_stories_section(profile)
    user_stories_structure = (
        str(user_stories_section.get("structure", "per_story_grouped"))
        if user_stories_section
        else ""
    )
    user_stories_heading = (
        str(user_stories_section.get("heading", "")).strip()
        if user_stories_section
        else ""
    )
    normative_tokens = profile_normative_tokens(profile)
    contract = config_contract(config)
    contract_required = bool(contract and contract.get("enforcement", "optional") == "required")
    since_contract = contract_since(contract)
    contract_exempt_count = 0
    disagreement_vocab = profile_disagreement_vocabulary(profile) if contract else None
    if contract and args.strict_body and disagreement_vocab is None:
        sys.stderr.write(
            "warning: requirement_contract is declared in config.yml but the active "
            "profile lacks sections[id=requirement_disagreement] or "
            "requirement_contract.disagreement — the disagreement-outcome check is "
            "skipped. Run /immutable:migrate to pick up the bundled vocabulary.\n"
        )
    strict_structure_enabled = bool(
        args.strict_body
        and user_stories_section
        and user_stories_structure == "per_story_grouped"
        and user_stories_heading
    )

    dirs = resolve_dirs(config, repo_root)

    if args.list_active:
        if args.strict_body or args.strict_since is not None:
            sys.stderr.write(
                "warning: --strict-body/--strict-since have no effect with "
                "--list-active.\n"
            )
        types = DOC_TYPES if args.type == "all" else (args.type,)
        return list_active_docs(dirs, types, args.domain, args.json)

    pitches_ref_root, pitches_ref_error = resolve_pitches_for_reference(config, repo_root)

    # Allowlist comes from local pitches README when available,
    # otherwise from the reference root (app repo walks to sibling spec).
    allow = domain_allowlist(dirs.get("pitch") or pitches_ref_root)

    violations: list[str] = []
    strict_exempt_count = 0

    # An unresolvable spec repo is ONE configuration violation, reported once —
    # not one bogus "file not found" per ADR against a directory that isn't there.
    if pitches_ref_error:
        warn(violations, pitches_ref_error)

    types = DOC_TYPES if args.type == "all" else (args.type,)
    for doc_type in types:
        doc_root = dirs.get(doc_type)
        if doc_root is None:
            continue
        collected: list[tuple[Path, dict[str, Any]]] = []
        for md_path in iter_docs(doc_root, doc_type):
            check_filename(md_path, filename_pattern, violations)
            fm = load_frontmatter(md_path)
            fm_checked = check_frontmatter(md_path, doc_type, fm, violations)
            if fm_checked:
                check_domain(
                    md_path, fm_checked, doc_type, allow, reserved, violations
                )
                check_references(
                    md_path,
                    fm_checked,
                    doc_type,
                    pitches_ref_root,
                    reserved,
                    violations,
                )
                check_ticket_references(md_path, fm_checked, doc_type, violations)
                if args.strict_body:
                    if strict_body_in_scope(md_path, strict_since):
                        validate_body_headings(
                            md_path,
                            doc_type,
                            required_headings_by_type[doc_type],
                            violations,
                        )
                        if strict_structure_enabled and doc_type == "pitch":
                            validate_pitch_user_stories_structure(
                                md_path,
                                user_stories_heading,
                                normative_tokens,
                                violations,
                            )
                        if doc_type == "pitch" and contract_required:
                            if strict_body_in_scope(md_path, since_contract):
                                check_ticket_presence(md_path, fm_checked, violations)
                            else:
                                contract_exempt_count += 1
                        if doc_type == "pitch" and disagreement_vocab is not None:
                            validate_pitch_disagreement_outcomes(
                                md_path, disagreement_vocab, violations
                            )
                    else:
                        strict_exempt_count += 1
                collected.append((md_path, fm_checked))
        check_supersede_chain_integrity(doc_type, collected, violations)

    # Scoping is observable, never silent: say how many files the cutoff exempted.
    if args.strict_body and strict_since is not None:
        sys.stderr.write(
            f"note: --strict-body scoped to files dated on/after {strict_since}; "
            f"{strict_exempt_count} legacy file(s) exempt.\n"
        )
    elif args.strict_since is not None and not args.strict_body:
        sys.stderr.write(
            "warning: --strict-since has no effect without --strict-body.\n"
        )
    if args.strict_body and contract_required and since_contract is not None:
        sys.stderr.write(
            f"note: requirement_contract.since {since_contract}: {contract_exempt_count} "
            f"pitch(es) predate the contract; presence rule not applied to them.\n"
        )
    if args.domain is not None:
        sys.stderr.write("warning: --domain has no effect without --list-active.\n")

    if args.json:
        print(json.dumps({"violations": violations, "clean": not violations}))
    else:
        if violations:
            for v in violations:
                sys.stderr.write(v + "\n")
            sys.stderr.write(f"\n{len(violations)} violation(s) found.\n")
        else:
            print("all checks passed.")

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
