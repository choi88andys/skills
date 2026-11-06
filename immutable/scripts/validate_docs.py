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
     is deprecated. Fan-in (v0.17+, pitches only — a fold): `supersedes` may
     list several files of the pitch's own domain, each of which must be
     deprecated. `changes` (v0.17+), when present, is a list of
     `{section, kind: add|modify|remove}` on a pitch that supersedes something.
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

  9. Requirement contract (v0.11+) — none of this applies to a `deprecated: true`
     doc (v0.12.1): a dead doc in an append-only repo can be neither edited nor
     superseded, so it has no remedy, and `coverage` / `drift` only read active
     docs; the frozen count goes to stderr. For an ACTIVE doc:
     `references.tickets[]` entries carry
     non-empty string `tracker` / `id` / `version`, with `id` matching the
     canonical charset `requirement_contract.py` enforces on its own `--id`
     (always on, v0.12+); under
     `--strict-body` and the `--strict-since` scope, with the config's
     `requirement_contract.enforcement: required`, every pitch dated on or
     after `requirement_contract.since` (when set) carries a ticket reference
     or a `references.ticket_exemption`; and, once the
     config opts into the contract, a pitch's disagreement section
     (`profile.sections[id=requirement_disagreement]`) holds ≥1 `### ` entry
     whose four labelled bullets are present and whose outcome begins with a
     terminal token — a provisional outcome is a violation, which is the
     merge gate that keeps a pitch PR open until the request is settled. Its
     correction bullet must pass the profile's wording rules that apply to
     corrections (`requirement_contract.wording_rules[]`, plus the legacy
     `disagreement.deferral_patterns[]`; v0.13+): a `block` hit is a
     violation, a `warn` hit a stderr warning. The rules are compiled by
     `requirement_contract.py` — the same reader its `lint` uses. A rule
     with `since` (v0.16+) judges a correction only when the contested
     ticket was created on or after it — the day comes from the ticket
     record's `created_at`, else the pitch's filename date plus a day — and a
     pitch dated within a day of the earliest `since`, or later, records
     `created_at` for every ticket a disagreement entry contests (a malformed
     `created_at` is a violation at any date, always on). A wording rule the
     compiler cannot trust is a violation, as `lint` refuses it. The
     acknowledgement ledger beside config.yml
     (`contract-acknowledgements.yml`, v0.15+), when present, must have the
     shape `requirement_contract.py`'s `ledger_entries` reads — the gate's
     own reader; always on once the repo opts into the contract.

 10. Cross-pitch references (v0.17+) — under `--strict-body` within the
     `--strict-since` scope, for an ACTIVE pitch: no body line names another
     pitch's path together with one of the profile's `precedence_keywords`
     (only `supersedes` changes another pitch's meaning), and every cited
     pitch path is a pitch whose supersede chain reaches an active one. The
     pitch's own `supersedes` targets are exempt from both.
 11. Size (v0.17+) — under the same scope, an ACTIVE pitch file is at most the
     profile's `max_bytes` (default 50000): Claude Code's Read returns a
     partial page past about 55 KB of Korean pitch text.
 13. Input contract (v0.18+) — under the same scope, for an ACTIVE pitch: the
     `sections[id=input_contract]` section, when present, holds either a table
     whose header is the profile's four `columns` and whose every row has four
     decided cells and a field of its own, or a statement that the pitch
     defines no input; a bracketed normative line matching `input_markers` in a
     pitch without the section is a warning, and a violation for a pitch dated
     on or after the section's `since`. See `check_input_contract`.
     (12 is the `--supersede-diff` mode below.)

Not covered (deferred): cycle detection on supersede chains.

Besides validating, `--list-active` prints the repo's active (non-deprecated)
docs — one `<absolute path>\\t<domain>` line per doc — and is the canonical
resolver behind the flow skills' active-pitch pickers (`/immutable:design`,
`/immutable:prd`, `/immutable:plan-review-ceo`). See the flag's help text for
its fail-open contract.

`--supersede-diff` (v0.17+) compares a successor pitch with its predecessor(s),
`### ` sub-section by sub-section after whitespace normalization, and fails on
any difference its `changes` frontmatter does not declare. It judges the paths
given, or with `--base REV` every pitch added since REV — the CI and pre-push
form. See `run_supersede_diff`.

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

# The wording rules a correction is judged by are compiled by the parser
# module that `lint` uses on ticket items — one reader, so the authoring skill,
# a CI lint and this merge gate cannot disagree about what a rule says. The
# plugin ships both scripts side by side; consumers check out the whole plugin.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import requirement_contract as _contract  # noqa: E402


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
# The canonical ticket id, identical to `requirement_contract.py`'s `TICKET_ID_RE`.
# It is deliberately tracker-neutral: a bare number (GitHub, Redmine), `PROJ-123`
# (Jira, Linear) and dotted ids all pass. The two layers must agree, because
# `coverage` matches a pitch to a ticket by exact string equality on this field.
TICKET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
DISAGREEMENT_FIELDS = ("original", "correction", "reason", "outcome")
REPO_MODES = ("two-repo-spec", "two-repo-app", "single-repo")
# What a successor pitch may do to one section of its predecessor (`changes[].kind`).
CHANGE_KINDS = ("add", "modify", "remove")
# Byte ceiling per pitch file when the profile sets none. Claude Code's Read stops
# at 25,000 tokens a call and shows a partial page; Korean pitch text runs about
# 0.45 tokens a byte, so the page ends near 55 KB (measured 2026-11-06 on merged
# lounge-x-spec domains). 50,000 leaves headroom under it. A byte count, not a
# line or story count: the read limit is a token limit.
DEFAULT_MAX_BYTES = 50_000
# Files under the pitches directory that are not pitches and are never cited as one.
NON_PITCH_FILES = ("README.md", "TEMPLATE.md")
# How many changed lines one undeclared change prints per side.
DIFF_SAMPLE_LINES = 6
# Internal key for the content before a pitch's first `## ` — its title unit.
TITLE_KEY = "\x00title"
# The four cells of an Inputs table row, in column order (v0.18+): the field, how
# it is entered, the accepted values, what happens on an invalid value. The
# labels come from `sections[id=input_contract].columns`.
INPUT_COLUMNS = ("field", "entry", "accepted", "invalid")
# A cell holding nothing but placeholder punctuation says nothing.
PLACEHOLDER_CELL_RE = re.compile(r"^[\s\-–—.…_*`~]*$")
# Undecided markers every locale writes the same way; the profile's
# `gate.unresolved_tag` is added per run.
TBD_RE = re.compile(r"\bTB[DC]\b", re.IGNORECASE)
# One cell of a GFM delimiter row: at least one dash, optional alignment colons.
TABLE_DELIMITER_CELL_RE = re.compile(r"^:?-+:?$")
# A heading as CommonMark reads it — up to three spaces of indent, an optional
# closing run of `#` (`## 입력 항목 ##`). The input contract finds its section with
# it, so a heading a renderer shows is never reported missing.
ATX_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
BLOCKQUOTE_PREFIX_RE = re.compile(r"^\s*(?:>\s?)+")
UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
# How many lines one input-contract message lists.
INPUT_SAMPLE_LINES = 5


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
        window = contract.get("response_window")
        if window is not None and (not isinstance(window, str) or not window.strip()):
            die("config.yml requirement_contract.response_window must be a non-empty string")

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
            except (yaml.YAMLError, ValueError) as exc:
                # ValueError: an unquoted impossible date (`since: 2026-02-30`) —
                # PyYAML builds a date object and `datetime` raises, as in load_config.
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
        except (yaml.YAMLError, ValueError) as exc:
            sys.stderr.write(
                f"warning: bundled profile {bundled} failed to parse ({exc}); "
                f"using hardcoded defaults.\n"
            )

    return {}


def load_bundled_profile(config: dict[str, Any]) -> dict[str, Any]:
    """The bundled `default-<team_language>.yml`, or {} when absent or broken.

    The fallback for a field a team profile predates (v0.17+): the validator
    reads ONE profile, so without it a team profile below the schema that
    introduced a field would run the check with nothing — a gate that is off
    because nobody migrated, indistinguishable from a clean run."""
    team_lang = config.get("team_language", "en")
    bundled = Path(__file__).resolve().parent.parent / "examples" / "_profiles" / f"default-{team_lang}.yml"
    try:
        with bundled.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def profile_field(
    profile: dict[str, Any], bundled: dict[str, Any], key: str
) -> tuple[Any, bool]:
    """`(value, from_bundled)` — the team profile's top-level `key`, else the
    bundled default's. `from_bundled` lets the caller say so on stderr."""
    if profile and key in profile:
        return profile[key], False
    return bundled.get(key), True


def profile_max_bytes(
    profile: dict[str, Any], bundled: dict[str, Any], problems: list[str]
) -> tuple[int, bool]:
    """The pitch byte ceiling (v0.17+): the profile's `max_bytes`, else the
    bundled default's, else `DEFAULT_MAX_BYTES`. A value that is not a
    positive integer is reported in `problems` and the default applies — a
    typo never switches the ceiling off."""
    value, from_bundled = profile_field(profile, bundled, "max_bytes")
    if value is None:
        return DEFAULT_MAX_BYTES, True
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        problems.append(
            f"max_bytes must be a positive integer, got {value!r} — "
            f"the default {DEFAULT_MAX_BYTES} applies until the profile is fixed"
        )
        return DEFAULT_MAX_BYTES, from_bundled
    return value, from_bundled


def profile_precedence_keywords(
    profile: dict[str, Any], bundled: dict[str, Any], problems: list[str]
) -> tuple[list[str], bool]:
    """The phrases that mark a sentence as overriding another pitch (v0.17+),
    matched as literal, case-insensitive substrings. The profile's list, else
    the bundled default's. A malformed list is reported in `problems` and the
    bundled list applies."""
    value, from_bundled = profile_field(profile, bundled, "precedence_keywords")
    if value is None:
        return [], True
    if not isinstance(value, list) or not all(isinstance(k, str) and k.strip() for k in value):
        problems.append(
            "precedence_keywords must be a list of non-empty strings — "
            "the bundled list applies until the profile is fixed"
        )
        fallback = bundled.get("precedence_keywords")
        if isinstance(fallback, list):
            return [str(k).strip() for k in fallback if isinstance(k, str) and k.strip()], True
        return [], True
    return [k.strip() for k in value], from_bundled


def _section_entry(profile: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    """The `sections[id=section_id]` entry of `profile`, or None."""
    for entry in (profile or {}).get("sections") or []:
        if isinstance(entry, dict) and entry.get("id") == section_id:
            return entry
    return None


def _columns_ok(value: Any) -> bool:
    return isinstance(value, dict) and all(
        isinstance(value.get(k), str) and value[k].strip() for k in INPUT_COLUMNS
    )


def profile_input_contract(
    profile: dict[str, Any], bundled: dict[str, Any], problems: list[str]
) -> dict[str, Any] | None:
    """What the input-contract check reads (v0.18+, profile_schema 9), or None
    when neither the profile nor the bundled default defines the section.

    `sections[id=input_contract]` gives the heading, the four column labels
    (`columns`, in `INPUT_COLUMNS` order) and `since`; the top-level
    `input_markers` regexes find normative lines that speak of an input. A
    field the team profile lacks comes from the bundled default and is named
    in `from_bundled`. `blocking` is False when the SECTION itself is the
    bundled one: its `since` is the plugin's date, not one the team chose at
    migration, and applying it would block pitches written before the team
    knew the rule — so an unmigrated profile warns and never blocks. A team
    section without `since` blocks every pitch (the team chose no date). A
    malformed field is reported in `problems` (a violation under
    --strict-body) and the bundled value applies; a malformed `since` also
    leaves the rule warn-only, since the run already fails on the problem."""
    team = _section_entry(profile, "input_contract")
    base = _section_entry(bundled, "input_contract")
    entry = team or base
    if entry is None:
        return None
    from_bundled: list[str] = [] if team is not None else ["sections[id=input_contract]"]

    heading = entry.get("heading")
    if not isinstance(heading, str) or not heading.strip():
        problems.append("sections[id=input_contract].heading must be a non-empty string")
        heading = (base or {}).get("heading")
        if not isinstance(heading, str) or not heading.strip():
            return None
    columns = entry.get("columns")
    if not _columns_ok(columns):
        problems.append(
            f"sections[id=input_contract].columns must map each of {list(INPUT_COLUMNS)} "
            f"to a non-empty label — the bundled labels apply until the profile is fixed"
        )
        columns = (base or {}).get("columns")
        if not _columns_ok(columns):
            return None
    assert isinstance(columns, dict)

    since: str | None = None
    blocking = team is not None
    if team is not None and "since" in team:
        raw = team["since"]
        value = raw.isoformat() if isinstance(raw, datetime.date) else str(raw).strip()
        try:
            if not _DATE_RE.match(value):
                raise ValueError
            datetime.date.fromisoformat(value)
            since = value
        except ValueError:
            problems.append(
                f"sections[id=input_contract].since must be a YYYY-MM-DD date, got {raw!r} — "
                f"an undeclared input is warned, not blocked, until the profile is fixed"
            )
            blocking = False

    # A key present with no value (`input_markers:`) is malformed, not absent: read
    # as absent it would skip both the check and the bundled fallback, silently.
    raw_markers, markers_bundled = profile_field(profile, bundled, "input_markers")
    markers: list[re.Pattern[str]] = []
    if markers_bundled:
        from_bundled.append("input_markers")
    if raw_markers is not None or not markers_bundled:
        try:
            if not isinstance(raw_markers, list) or not all(isinstance(m, str) and m.strip() for m in raw_markers):
                raise ValueError("must be a list of non-empty regex strings")
            markers = [re.compile(m, re.IGNORECASE) for m in raw_markers]
        except (ValueError, re.error) as exc:
            problems.append(f"input_markers {exc} — the bundled list applies until the profile is fixed")
            fallback = bundled.get("input_markers")
            markers = [
                re.compile(m, re.IGNORECASE) for m in fallback if isinstance(m, str) and m.strip()
            ] if isinstance(fallback, list) else []

    # The tag key by key: a team `gate` that sets only its counts keeps the bundled tag.
    tag = next(
        (
            g["unresolved_tag"].strip()
            for g in ((profile or {}).get("gate"), bundled.get("gate"))
            if isinstance(g, dict) and isinstance(g.get("unresolved_tag"), str) and g["unresolved_tag"].strip()
        ),
        None,
    )
    if team is None:
        warn_only = "the team profile predates the rule (profile_schema 9)"
    elif not blocking:
        warn_only = "the profile's sections[id=input_contract].since is malformed (reported as a profile violation)"
    else:
        warn_only = f"dated before its since {since}"
    return {
        "heading": norm_line(heading),
        "columns": [norm_line(str(columns[k])) for k in INPUT_COLUMNS],
        "since": since,
        "blocking": blocking,
        "warn_only": warn_only,
        "markers": markers,
        "unresolved_tag": tag,
        "from_bundled": from_bundled,
    }


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
    the section heading plus field labels and outcome tokens, and the wording
    rules a correction must pass (v0.13+, compiled by `requirement_contract`'s
    `compile_wording`: `wording_rules[]` that apply to `correction`, plus the
    legacy `disagreement.deferral_patterns[]`). None when the heading, labels
    or tokens are missing — the caller then skips the check with a warning
    rather than inventing labels. A rule that does not compile is left out
    of `wording["rules"]` and named in `wording["problems"]`, which `main`
    reports as violations (v0.16+)."""
    if not profile:
        return None
    heading = None
    for entry in profile.get("sections") or []:
        if isinstance(entry, dict) and entry.get("id") == "requirement_disagreement":
            heading = str(entry.get("heading") or "").strip()
    contract_block = profile.get("requirement_contract") or {}
    block = contract_block.get("disagreement") or {}
    fields = block.get("fields") or {}
    provisional = block.get("outcome_provisional")
    terminal = block.get("outcome_terminal") or []
    wording = _contract.compile_wording(contract_block)
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
        "wording": wording,
        # Both optional: a profile may carry neither (pre-v0.11 vocabulary) or
        # only the legacy deferral_patterns (pre-v0.13).
        "correction_rules": sum("correction" in r["applies_to"] for r in wording["rules"]),
        "has_wording_rules": "wording_rules" in contract_block,
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
    if "supersedes" in fm:
        problem = supersedes_shape_problem(fm["supersedes"], doc_type)
        if problem:
            warn(violations, f"{path}: {problem}")
    if "changes" in fm:
        for problem in changes_shape_problems(fm, doc_type):
            warn(violations, f"{path}: {problem}")
    return fm


def supersedes_shape_problem(value: Any, doc_type: str) -> str | None:
    """Why a `supersedes` value is malformed, or None.

    A filename or null; for a pitch also a non-empty list of distinct
    filenames (fan-in, v0.17+), which the chain check resolves one by one in
    the pitch's own domain. An ADR supersedes one file. Before v0.17 a list
    reached the chain check as a dict key and crashed it with a TypeError."""
    if value is None or (isinstance(value, str) and value.strip()):
        return None
    if isinstance(value, list):
        if doc_type != "pitch":
            return f"`supersedes` lists {len(value)} files; an ADR supersedes one file (fan-in is pitch-only)"
        if not value:
            return "`supersedes: []` — write `null` when nothing is superseded"
        if not all(isinstance(v, str) and v.strip() for v in value):
            return "every `supersedes` entry must be a filename"
        names = [v.strip() for v in value]
        twice = sorted({n for n in names if names.count(n) > 1})
        if twice:
            return f"`supersedes` names {', '.join(twice)} more than once"
        return None
    kinds = "a filename, a list of filenames, or null" if doc_type == "pitch" else "a filename or null"
    return f"`supersedes` must be {kinds}, got {value!r}"


def supersede_targets(fm: dict[str, Any] | None, doc_type: str) -> list[str]:
    """The filenames a doc supersedes — [] for null or for a malformed value
    (which `check_frontmatter` reports), so no reader crashes on one."""
    value = (fm or {}).get("supersedes")
    if supersedes_shape_problem(value, doc_type) is not None or value is None:
        return []
    return [value.strip()] if isinstance(value, str) else [v.strip() for v in value]


def changes_shape_problems(fm: dict[str, Any], doc_type: str) -> list[str]:
    """Shape of `changes` (v0.17+): the successor's declared difference from
    its predecessor(s) — a list of `{section, kind}`, `kind` one of
    `CHANGE_KINDS`, each section once. `--supersede-diff` checks the body
    against it; this is the static half, always on."""
    changes = fm.get("changes")
    if doc_type != "pitch":
        return ["`changes` is a pitch field (the supersede diff runs on pitches only)"]
    if not isinstance(changes, list):
        return ["`changes` must be a list of {section, kind}"]
    problems: list[str] = []
    if not supersede_targets(fm, doc_type):
        problems.append("`changes` declares a difference from a predecessor, but `supersedes` names none")
    seen: set[str] = set()
    for i, entry in enumerate(changes):
        if not isinstance(entry, dict) or set(entry) - {"section", "kind"}:
            problems.append(f"changes[{i}] must be a mapping with exactly `section` and `kind`")
            continue
        section = entry.get("section")
        if not isinstance(section, str) or not section_key(section):
            problems.append(f"changes[{i}].section must name a heading of the pitch")
            continue
        if entry.get("kind") not in CHANGE_KINDS:
            problems.append(f"changes[{i}].kind must be one of {list(CHANGE_KINDS)}, got {entry.get('kind')!r}")
        key = section_key(section)
        if key in seen:
            problems.append(f"changes names section {section!r} more than once")
        seen.add(key)
    return problems


def norm_line(line: str) -> str:
    """A line with every whitespace run collapsed — what the supersede diff compares."""
    return " ".join(line.split())


def section_key(heading: str) -> str:
    """A heading as `changes[].section` names it: leading `#`s dropped, whitespace normalized."""
    return norm_line(re.sub(r"^\s*#+\s*", "", heading))


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
    contract silently degrade to "some ticket, some time". `id` must also be
    the canonical form the reconciler matches on — see `check_ticket_id`.

    `repo` stays optional by design: the config-level `requirement_contract.repo`
    is the documented default for a bare id, so requiring it here would break
    every record already written. The consequence is that a record citing a
    ticket in a *different* repository carries no way to say so, and `coverage`
    will place it in the configured repo's set; such a pitch should spell `repo`
    out.
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
                check_ticket_id(path, i, entry, violations)
                check_ticket_ledger(path, i, entry, violations)
                created = entry.get("created_at")
                if created is not None and _contract.created_date(created, datetime.timezone.utc) is None:
                    warn(
                        violations,
                        f"{path}: references.tickets[{i}].created_at {str(created)!r} is neither "
                        f"YYYY-MM-DD nor a timestamp with an offset — copy the parser's source.created_at",
                    )
    exemption = refs.get("ticket_exemption")
    if exemption is not None and (not isinstance(exemption, str) or not exemption.strip()):
        warn(violations, f"{path}: references.ticket_exemption must be a non-empty reason string")


def check_ticket_id(path: Path, i: int, entry: dict[str, Any], violations: list[str]) -> None:
    """The recorded id must be the canonical one (v0.12+).

    `requirement_contract.py coverage` matches a pitch to a ticket by exact
    string equality on this field, and enforces the same charset on its own
    `--id`. Until this check existed the two layers disagreed: a decorated id
    (`owner/repo#3654`) passed the validator, matched no pitch during
    reconciliation, and so *satisfied* the presence rule while being invisible
    to the check that presence exists for — one malformed record buying a pass.
    The rule is a charset, not a tracker: bare numbers, `PROJ-123` and dotted
    ids all pass.
    """
    raw = entry.get("id")
    if not isinstance(raw, (str, int)) or not str(raw).strip():
        return  # already reported as missing
    value = str(raw).strip()
    if TICKET_ID_RE.match(value):
        return
    warn(
        violations,
        f"{path}: references.tickets[{i}].id {value!r} is not a canonical ticket id "
        f"(letters, digits, `.`, `_`, `-`; first character a letter or digit). "
        f"This is the string `requirement_contract.py coverage` matches on, so a decorated "
        f"id silently reconciles against nothing — record the bare id and name the "
        f"repository in `repo:`",
    )


def _ledger_items_ok(items: Any) -> bool:
    return items is None or (
        isinstance(items, list) and bool(items) and all(isinstance(x, int) and x > 0 for x in items)
    )


def check_ticket_ledger(path: Path, i: int, entry: dict[str, Any], violations: list[str]) -> None:
    """Shape of the accounting ledger under a ticket record (v0.11+):
    `covers` = mapping of binding id → list of {group, items?, shared?};
    `delegates` = list of {binding, group, items?, to, why?}. Semantics
    (does the group exist, is every item claimed) are `requirement_contract.py
    coverage`'s job — it needs the live ticket; this is the static half."""
    where = f"{path}: references.tickets[{i}]"
    covers = entry.get("covers")
    if covers is not None:
        if not isinstance(covers, dict):
            warn(violations, f"{where}.covers must be a mapping of binding id → list of {{group, items?, shared?}}")
        else:
            for binding, decls in covers.items():
                if not isinstance(decls, list):
                    warn(violations, f"{where}.covers.{binding} must be a list")
                    continue
                for j, d in enumerate(decls):
                    if not isinstance(d, dict) or "group" not in d:
                        warn(violations, f"{where}.covers.{binding}[{j}] must be a mapping with `group`")
                        continue
                    if not _ledger_items_ok(d.get("items")):
                        warn(violations, f"{where}.covers.{binding}[{j}].items must be a non-empty list of positive integers")
                    if "shared" in d and not isinstance(d["shared"], bool):
                        warn(violations, f"{where}.covers.{binding}[{j}].shared must be a boolean")
    delegates = entry.get("delegates")
    if delegates is not None:
        if not isinstance(delegates, list):
            warn(violations, f"{where}.delegates must be a list")
        else:
            for j, d in enumerate(delegates):
                if not isinstance(d, dict) or "binding" not in d or "group" not in d:
                    warn(violations, f"{where}.delegates[{j}] must be a mapping with `binding` and `group`")
                    continue
                if not isinstance(d.get("to"), str) or not d["to"].strip():
                    warn(violations, f"{where}.delegates[{j}].to must name who owns the literal (e.g. Figma)")
                if not _ledger_items_ok(d.get("items")):
                    warn(violations, f"{where}.delegates[{j}].items must be a non-empty list of positive integers")


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


# A pitch's filename date is its author's local date, which can trail the
# day a ticket's creation is read in (`since_utc_offset`) by up to a day. When
# the filename date stands in for a ticket's creation day it is moved a day
# later, so a pitch near the boundary is judged by the newer rule, never spared.
AUTHOR_DATE_MARGIN = datetime.timedelta(days=1)


def check_ticket_created_at(
    path: Path, fm: dict[str, Any], cutoff: datetime.date, heading: str,
    default_repo: str | None, violations: list[str],
) -> None:
    """A ticket a disagreement entry contests carries `created_at` in the
    pitch's record (v0.16+), once the pitch is dated within a day of `cutoff`
    — the earliest `since` among the profile's wording rules — or later.

    The validator lints corrections offline, with no ticket fetch, so the
    record is the only place a since-gated rule learns whether the contested
    ticket predates it. It is required only where it is read — a ticket no
    entry contests needs none, so a pitch written before the field existed
    turns red only if it carries a correction a dated rule would judge.
    Older pitches are unaffected: every ticket they cite existed before them."""
    pitch_date = filename_date(path)
    if pitch_date is not None and pitch_date + AUTHOR_DATE_MARGIN < cutoff:
        return
    reported: set[int] = set()
    for title in _contract.disagreement_titles(path.read_text(encoding="utf-8"), heading):
        record = ticket_record(title, fm, default_repo)
        if record is None or record[0] in reported or record[1].get("created_at") not in (None, ""):
            continue
        reported.add(record[0])
        warn(
            violations,
            f"{path}: references.tickets[{record[0]}] has no created_at — a disagreement entry "
            f"contests that ticket and the pitch is dated on or after {cutoff - AUTHOR_DATE_MARGIN} "
            f"(the earliest wording-rule `since`, less a day for the author's time zone), so the "
            f"ticket's creation date must be recorded — copy the parser's source.created_at",
        )


def filename_date(path: Path) -> datetime.date | None:
    m = _FILENAME_DATE_RE.match(path.name)
    if not m:
        return None
    try:
        return datetime.date.fromisoformat(m.group(1))
    except ValueError:
        return None


def ticket_record(
    title: str, fm: dict[str, Any] | None, default_repo: str | None
) -> tuple[int, dict[str, Any]] | None:
    """(index, entry) of the pitch's ticket record a disagreement entry's
    header names, or None when the header names no recorded ticket."""
    m = _contract.DISAGREEMENT_TITLE_RE.match(title)
    refs = (fm or {}).get("references") or {}
    tickets = refs.get("tickets") if isinstance(refs, dict) else None
    if not m or not isinstance(tickets, list):
        return None
    repo = m.group("repo") or default_repo
    for i, entry in enumerate(tickets):
        if not isinstance(entry, dict) or str(entry.get("id")) != m.group("id"):
            continue
        if str(entry.get("tracker") or "github") != m.group("tracker"):
            continue
        if (entry.get("repo") or default_repo) != repo:
            continue
        return i, entry
    return None


def contested_ticket_created(
    title: str, fm: dict[str, Any] | None, default_repo: str | None, tz: datetime.timezone
) -> datetime.date | None:
    """The creation day of the ticket a disagreement entry contests, from the
    pitch's own ticket record — None when the header names no recorded ticket
    or the record carries no readable `created_at`."""
    record = ticket_record(title, fm, default_repo)
    return _contract.created_date(record[1].get("created_at"), tz) if record else None


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
    fm: dict[str, Any] | None = None,
    default_repo: str | None = None,
    withheld: dict[str, int] | None = None,
) -> None:
    """The requirement-contract merge gate (v0.11+).

    When the disagreement section (H2 == `vocab["heading"]`) exists, it must
    hold ≥1 `### ` entry, and every entry must carry the four labelled bullets
    with an outcome that BEGINS with a terminal token. An outcome beginning
    with the provisional token is a violation: the request it records is still
    open, so the pitch may not merge yet. Runs under --strict-body within the
    --strict-since scope.

    A since-gated wording rule (v0.16+) judges a correction only when the
    ticket the entry contests was created on or after its `since`: the
    creation day comes from the pitch's ticket record (`fm`), and when the
    record has none, the pitch's own filename date stands in for it, a day
    later (`AUTHOR_DATE_MARGIN`) — a ticket cannot postdate the pitch citing
    it, so an older pitch is never judged by a newer rule, and a newer one is
    judged by every rule (fail-closed).
    Withheld would-be hits are counted into `withheld` (rule id → hits).
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
        # The correction becomes the requirement if the ticket stays silent past
        # the response window; one that defers, hedges or hands the decision
        # elsewhere cannot be confirmed by silence, so it is not a correction.
        # A `block` hit is a violation (the first one is named); a `warn` hit is
        # printed and does not gate.
        correction = found.get("correction")
        if correction is not None:
            wording = vocab["wording"]
            created = contested_ticket_created(e_title, fm, default_repo, wording["utc_offset"])
            if created is None and filename_date(path) is not None:
                created = filename_date(path) + AUTHOR_DATE_MARGIN
            in_force, held = _contract.rules_in_force(wording, created)
            hits = _contract.wording_hits(in_force, correction, "correction")
            for rule in held:
                n = len(_contract.wording_hits({**wording, "rules": [rule]}, correction, "correction"))
                if n and withheld is not None:
                    withheld[rule["id"]] = withheld.get(rule["id"], 0) + n
            excerpt = correction if len(correction) <= 80 else correction[:77] + "..."
            blocking = next((h for h in hits if h["severity"] == "block"), None)
            if blocking is not None and blocking["source"] == "deferral_patterns":
                issues.append(
                    f"### {e_title} — `{fields['correction']}` defers instead of deciding "
                    f"(matched deferral_patterns[{blocking['rule']}] on {blocking['match']!r}): {excerpt}"
                )
            elif blocking is not None:
                issues.append(
                    f"### {e_title} — `{fields['correction']}` is not a decision "
                    f"(matched wording_rules[{blocking['rule']}] on {blocking['match']!r} — {blocking['hint']}): {excerpt}"
                )
            for h in hits:
                if h["severity"] == "warn":
                    sys.stderr.write(
                        f"warning: {path}: ### {e_title} — `{fields['correction']}` "
                        f"matched wording_rules[{h['rule']}] on {h['match']!r} ({h['hint']})\n"
                    )
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


def iter_body(text: str) -> list[tuple[int, str, bool]]:
    """`(line number in the file, line, fenced)` for each body line.

    The frontmatter is skipped; a fence delimiter and everything between two
    of them is `fenced`, so a `## ` or a pitch path inside example code is
    neither a heading nor a citation."""
    m = FRONTMATTER_RE.match(text)
    offset = text[: m.end()].count("\n") if m else 0
    out: list[tuple[int, str, bool]] = []
    fenced = False
    for n, line in enumerate((text[m.end():] if m else text).splitlines(), start=offset + 1):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            out.append((n, line, True))
            continue
        out.append((n, line, fenced))
    return out


def pitch_path_re(config: dict[str, Any]) -> re.Pattern[str]:
    """A pitch path as a body cites it: `<pitches dir>/<domain>/<file>.md`,
    with or without a leading repo-relative prefix (`spec/pitches/…`)."""
    dirname = Path(str(config.get("pitches_path") or "pitches/").rstrip("/")).name or "pitches"
    return re.compile(
        rf"(?<![\w-]){re.escape(dirname)}/([A-Za-z0-9_][A-Za-z0-9_-]*)/([A-Za-z0-9][A-Za-z0-9._-]*\.md)"
    )


def live_ends(
    target: Path,
    index: dict[Path, dict[str, Any] | None],
    successors: dict[Path, list[Path]],
) -> list[Path]:
    """The active pitches `target`'s supersede chain leads to: `target` itself
    when active, else the live ends of its successors, transitively (a split
    forks the chain, a fold joins it). Empty when the chain ends in a
    deprecated pitch that nothing supersedes — the rule it held is gone."""
    ends: list[Path] = []
    seen: set[Path] = set()
    stack = [target]
    while stack:
        p = stack.pop()
        if p in seen:
            continue
        seen.add(p)
        fm = index.get(p)
        if fm is None or fm.get("deprecated") is not True:
            if p not in ends:
                ends.append(p)
            continue
        stack.extend(successors.get(p, []))
    return sorted(ends)


def check_pitch_references(
    path: Path,
    fm: dict[str, Any],
    pitches_root: Path,
    path_re: re.Pattern[str],
    index: dict[Path, dict[str, Any] | None],
    successors: dict[Path, list[Path]],
    keywords: list[str],
    violations: list[str],
    stale: list[tuple[Path, Path, list[Path]]],
) -> None:
    """No prose override and no dead citation in an active pitch (v0.17+).

    The incident (lounge-x-spec, 2026-11-06): a sibling pitch outranked one
    clause of a baseline with a sentence naming the baseline's file
    (「그 조항에 한해 … 우선한다」). A later supersede of the baseline could not
    see that sentence and copied the clause back, and two live pitches
    demanded 4 and 3 payment-auth methods. A body line that names another
    pitch's path must therefore not carry a `precedence_keywords` phrase:
    `supersedes` is the only relation that changes another pitch's meaning,
    so the rule moves into the pitch that owns it.

    A cited path names a supersede CHAIN, not a version: "this is owned by X"
    stays true when X gets a new version, and the deprecated-doc read guard
    hands a reader the successor. So a citation fails only when the chain
    reaches no active pitch (the cited rule is gone) or the path is no pitch
    at all. A citation of an older version is collected in `stale` — the
    caller reports the count, and the ones whose chain forks into several
    active pitches by name. Failing every older-version citation instead
    would make each supersede re-version every citer, transitively (measured
    2026-11-06: 29 of 71 active lounge-x-spec pitches cite an older version,
    almost all as ownership pointers).

    The pitch's own `supersedes` targets are exempt: a successor naming the
    version it replaces is the supersede itself, said in prose. Lines are
    judged one by one, so a line naming any other pitch is enough.
    """
    text = path.read_text(encoding="utf-8")
    me = path.resolve()
    own = {(path.parent / t).resolve() for t in supersede_targets(fm, "pitch")}
    folded_keywords = [(k, k.casefold()) for k in keywords]
    issues: list[str] = []
    for lineno, line, fenced in iter_body(text):
        if fenced:
            continue
        cited: dict[Path, str] = {}
        for m in path_re.finditer(line):
            if m.group(2) in NON_PITCH_FILES:
                continue
            target = (pitches_root / m.group(1) / m.group(2)).resolve()
            if target != me and target not in own:
                cited.setdefault(target, m.group(0))
        if not cited:
            continue
        # Keywords are sought in the line WITHOUT its pitch paths: a cited slug
        # like `…-price-overrides.md` is a name, not an override, and the
        # citer could never fix it — filenames are immutable.
        folded = path_re.sub(" ", line).casefold()
        hit = next((k for k, kf in folded_keywords if kf in folded), None)
        if hit is not None:
            issues.append(
                f"line {lineno}: names `{next(iter(cited.values()))}` and says \"{hit}\" — a pitch "
                f"changes another pitch's meaning only through `supersedes`. Move the rule into the "
                f"pitch that owns it (a new version of that pitch), or fold the two into one"
            )
        for target, shown in cited.items():
            if target not in index:
                issues.append(f"line {lineno}: cites `{shown}`, which is not a pitch in this repo")
                continue
            target_fm = index[target]
            if target_fm is None or target_fm.get("deprecated") is not True:
                continue
            reached = live_ends(target, index, successors)
            ends = [e for e in reached if e != me]
            if reached and not ends:
                continue  # the chain leads back to this pitch — a mention of its own history
            if not ends:
                issues.append(
                    f"line {lineno}: cites `{shown}`, which is deprecated, and its supersede chain "
                    f"reaches no active pitch — the rule it pointed to is gone. Drop or replace the "
                    f"citation in a new version of this pitch"
                )
                continue
            stale.append((path, target, ends))
    if issues:
        bullet = "\n  - " + "\n  - ".join(issues)
        warn(violations, f"{path}: cross-pitch reference violation:{bullet}")


def check_pitch_size(path: Path, max_bytes: int, violations: list[str]) -> None:
    """An active pitch stays under the byte ceiling a reader takes in one call (v0.17+)."""
    size = path.stat().st_size
    if size > max_bytes:
        warn(
            violations,
            f"{path}: {size} bytes, over max_bytes {max_bytes} — past about 55 KB of Korean "
            f"pitch text Claude Code's Read returns a partial page (25,000 tokens), and a "
            f"reader can act on part of the pitch as if it were the whole. Split it along its "
            f"user-facing feature areas (/immutable:prd refactor-split)",
        )


def _table_cells(line: str) -> list[str]:
    """The cells of one markdown table row, whitespace-normalized; `\\|` is a
    literal bar, and the leading and trailing pipes are optional, as in GFM."""
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|") and not inner.endswith("\\|"):
        inner = inner[:-1]
    return [norm_line(c.replace("\\|", "|")) for c in UNESCAPED_PIPE_RE.split(inner)]


def _field_bare(cell: str) -> str:
    """A field cell as plain text: link markup reduced to its text, emphasis,
    code and quote marks dropped."""
    return re.sub(r"[`*_「」『』\"]", "", MARKDOWN_LINK_RE.sub(r"\1", cell)).strip()


def _field_key(cell: str) -> str:
    """The identity of a declared field: its plain text without parentheticals,
    casefolded — so 「생년월일」, 「**생년월일**」 and 「생년월일 (선택)」 are one
    field, and declaring it twice is caught even when the rows are marked up
    differently (the incident's shape: one value, two contradictory rows)."""
    return norm_line(re.sub(r"\s*[(（][^)）]*[)）]", "", _field_bare(cell))).casefold()


def _field_names(cell: str) -> list[str]:
    """The names a field cell gives its value, casefolded, for matching a story
    line: the plain text with and without parentheticals, and each
    alternative separated by `/` or `,` (「휴대폰 번호 / 전화번호」)."""
    bare = _field_bare(cell)
    names = {bare.casefold(), _field_key(cell)}
    names.update(p.strip().casefold() for p in re.split(r"\s*[/,、]\s*", _field_key(cell)))
    return sorted(n for n in names if n)


def check_input_contract(
    path: Path,
    ic: dict[str, Any],
    tokens: list[str],
    violations: list[str],
    counts: dict[str, int],
) -> None:
    """Every value the user enters is declared, per field (v0.18+).

    The incident (lounge-x-app 2.3.1, 2026-11-06): the signup pitch asked for an
    optional birthdate and said neither how it is entered nor what happens to a
    wrong value; the ticket was silent and the design drew a plain text field,
    so the app stored six typed digits as impossible dates. A pitch-level rule
    ("the edge table has an invalid-input row") passed that very pitch — its
    table had one-time-code error rows — and flagged 1 of the 9 input-bearing
    pitches of the repo. So the check is per field, and the author declares the
    fields in the `ic["heading"]` section:

    * a table there must have the profile's four column labels as its header,
      a GFM delimiter row of as many cells, at least one row, four cells a row,
      no empty or placeholder cell, no undecided cell (`gate.unresolved_tag`,
      TBD/TBC) and no field twice, however the two rows mark it up — a
      violation, at any date: the section is new, so no existing pitch has one;
    * a section with no table must say something — one line that the pitch
      defines no input and which pitch does, held to what a cell is held to (not
      a sub-heading, a dash or an undecided marker). A broken table never counts
      as that line: any line holding an unescaped `|`, with or without the
      leading pipe and inside a blockquote too, is judged as a table;
    * a bracketed normative line matching `ic["markers"]` in a pitch WITHOUT the
      section is a warning, and a violation when `ic["blocking"]` and the
      pitch is dated on or after `ic["since"]` — the rule is prospective, like
      the dated wording rules;
    * with a table, such a line naming none of its fields is a warning — the
      per-field net for the measured miss (a table for the code, none for the
      birthdate). It never blocks: a story may name a field differently.

    Warnings go to stderr; `counts` collects them for the summary note."""
    # An HTML comment (the template's guidance) is neither a statement nor a
    # table; blanking it keeps every line number.
    text = HTML_COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), path.read_text(encoding="utf-8"))
    body = iter_body(text)
    heading = ic["heading"]
    in_section = False
    section: list[tuple[int, str, bool]] = []
    present = False
    normative = _bracketed_normative_re(tokens)
    marked: list[tuple[int, str]] = []
    for n, line, fenced in body:
        m = None if fenced else ATX_HEADING_RE.match(line)
        if m and len(m.group(1)) <= 2:
            in_section = len(m.group(1)) == 2 and norm_line(m.group(2)) == heading
            present = present or in_section
            continue
        if fenced:
            continue
        if in_section:
            section.append((n, line, bool(m)))
        elif normative.search(line) and any(p.search(line) for p in ic["markers"]):
            marked.append((n, line.strip()))

    def sample(lines: list[tuple[int, str]]) -> str:
        shown = ", ".join(str(n) for n, _ in lines[:INPUT_SAMPLE_LINES])
        more = f" (+{len(lines) - INPUT_SAMPLE_LINES} more)" if len(lines) > INPUT_SAMPLE_LINES else ""
        return f"line(s) {shown}{more}"

    if not present:
        if not marked:
            return
        head = (
            f"{len(marked)} normative line(s) speak of a user-entered value — {sample(marked)} — "
            f"but the pitch has no `## {heading}` section"
        )
        remedy = (
            f"Declare each value the user enters as a row of `| {' | '.join(ic['columns'])} |`, "
            f"or, when another pitch defines it, say so in one line of that section"
        )
        if ic["blocking"] and strict_body_in_scope(path, ic["since"]):
            excerpt = "\n  - ".join(
                f"line {n}: {t if len(t) <= 120 else t[:117] + '...'}" for n, t in marked[:INPUT_SAMPLE_LINES]
            )
            warn(violations, f"{path}: input contract violation: {head}. {remedy}.\n  - {excerpt}")
            return
        sys.stderr.write(f"warning: {path}: {head} — a warning, not a violation: {ic['warn_only']}. {remedy}.\n")
        counts["undeclared"] = counts.get("undeclared", 0) + 1
        return

    undecided = [t for t in (ic["unresolved_tag"],) if t]

    def is_undecided(text: str) -> bool:
        return bool(TBD_RE.search(text)) or any(t in text for t in undecided)

    # Any line holding an unescaped `|` — with or without the leading pipe, inside
    # a blockquote too — is a table line: GFM renders `a | b` rows as a table,
    # and a table the check did not see as one would pass as the statement.
    tables: list[list[tuple[int, str]]] = []
    statement: list[str] = []
    for n, line, is_heading in section:
        bare = BLOCKQUOTE_PREFIX_RE.sub("", line)
        if not is_heading and UNESCAPED_PIPE_RE.search(bare):
            if tables and tables[-1][-1][0] == n - 1:
                tables[-1].append((n, bare))
            else:
                tables.append([(n, bare)])
        elif not is_heading and not PLACEHOLDER_CELL_RE.match(bare):
            statement.append(bare.strip())
    issues: list[str] = []
    if not tables:
        # The statement is held to what a cell is held to: a sub-heading, a dash
        # or an undecided marker says nothing about which pitch defines the input.
        if not statement:
            issues.append(
                f"`## {heading}` holds neither a table nor a statement — declare the values the user "
                f"enters, or say in one line that this pitch defines none and which pitch does"
            )
        elif any(is_undecided(s) for s in statement):
            issues.append(f"`## {heading}` — the statement is undecided: {next(s for s in statement if is_undecided(s))}")
    fields: dict[str, int] = {}
    names: list[str] = []
    columns = ic["columns"]
    for table in tables:
        (h_n, h_line), rest = table[0], table[1:]
        # A header cell may carry emphasis (`**항목**`); the label itself is exact.
        if [re.sub(r"^[*_]+|[*_]+$", "", c).strip() for c in _table_cells(h_line)] != columns:
            issues.append(
                f"line {h_n}: the table header must be `| {' | '.join(columns)} |`, got `{h_line.strip()}`"
            )
            continue
        delimiter = _table_cells(rest[0][1]) if rest else []
        if len(delimiter) != len(columns) or not all(TABLE_DELIMITER_CELL_RE.match(c) for c in delimiter):
            issues.append(
                f"line {h_n}: the header is not followed by a delimiter row of {len(columns)} cells (`|---|`)"
            )
            continue
        if len(rest) == 1:
            issues.append(f"line {h_n}: the table has no row — one row per value the user enters")
        for n, line in rest[1:]:
            cells = _table_cells(line)
            if len(cells) != len(columns):
                issues.append(f"line {n}: a row has {len(cells)} cell(s), the table {len(columns)}")
                continue
            field = cells[0] or "(no field)"
            for label, cell in zip(columns, cells):
                if PLACEHOLDER_CELL_RE.match(cell):
                    issues.append(f"line {n}: «{field}» — `{label}` is empty")
                elif is_undecided(cell):
                    issues.append(f"line {n}: «{field}» — `{label}` is undecided: {cell}")
            key = _field_key(cells[0])
            if not key or PLACEHOLDER_CELL_RE.match(cells[0]):
                continue
            if key in fields:
                issues.append(f"line {n}: «{field}» is declared twice (first at line {fields[key]})")
            else:
                fields[key] = n
                names.extend(_field_names(cells[0]))
    if issues:
        bullet = "\n  - " + "\n  - ".join(issues)
        warn(violations, f"{path}: input contract violation:{bullet}")
    if not names:
        return
    for n, line in marked:
        folded = line.casefold()
        if not any(name in folded for name in names):
            excerpt = line if len(line) <= 120 else line[:117] + "..."
            sys.stderr.write(
                f"warning: {path}: line {n} speaks of a user-entered value but names no field of "
                f"`## {heading}` — add its row, or leave it when the line is about a value this "
                f"pitch does not define: {excerpt}\n"
            )
            counts["unnamed"] = counts.get("unnamed", 0) + 1


def check_supersede_chain_integrity(
    doc_type: str,
    docs: list[tuple[Path, dict[str, Any]]],
    violations: list[str],
) -> None:
    """Enforce per-edge supersede integrity.

    For each file F with non-null F.supersedes:
      - The target T must exist in this doc-type set: a pitch's target in the
        same domain as F, an ADR's target anywhere in the ADR set.
      - T must have `deprecated: true`.

    No global per-(domain, type) cap. Multiple active files may coexist in the
    same domain — each on its own supersede chain. Fan-out (one predecessor
    superseded by N successors, e.g., a refactor-split) is permitted as long
    as the shared predecessor is deprecated. Fan-in (v0.17+, pitches only —
    a fold of N pitches into one) lists several targets; each edge is judged
    on its own, so every listed target must resolve and be deprecated.

    The lookup key differs by doc type because the two layouts differ:

      - pitch: (domain, filename). Pitches live in per-domain directories
        (`pitches/<domain>/`), where the same filename (e.g.,
        `2026-04-16-initial.md`) may legitimately appear in several domains,
        so a filename alone does not name one pitch. A cross-domain pitch
        supersede stays unresolvable.
      - adr: filename alone. ADRs live in one flat directory with the domain
        in frontmatter (SCHEMA.md "Naming conventions"; `iter_docs` globs
        them non-recursively), so a filename already names exactly one ADR.
        Keying by domain as well bought no disambiguation and made a chain
        whose subject legitimately moves to another domain unresolvable by
        construction.
    """

    def lookup_key(fm: dict[str, Any], filename: str) -> tuple[str, ...]:
        if doc_type == "pitch":
            return (fm.get("domain") or "_global", filename)
        return (filename,)

    by_key: dict[tuple[str, ...], dict[str, Any]] = {}
    for path, fm in docs:
        by_key[lookup_key(fm, path.name)] = fm

    for path, fm in docs:
        for target in supersede_targets(fm, doc_type):
            key = lookup_key(fm, target)
            if key not in by_key:
                scope = f"{doc_type} set"
                if doc_type == "pitch":
                    scope += f" under domain `{fm.get('domain') or '_global'}`"
                warn(
                    violations,
                    f"{path}: supersedes `{target}` but target file not found in "
                    f"{scope}",
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


def diff_units(text: str) -> tuple[str, dict[tuple[str, ...], list[str]]]:
    """`(title, units)` — a pitch body cut into the pieces `changes` names.

    A unit is the text under one `## ` up to its first `### ` (key
    `("##", heading)`), or under one `### ` (key `("###", enclosing ## heading,
    heading)`); deeper headings are content. The `# ` title and anything
    before the first `## ` form the title unit, `(TITLE_KEY,)`, so a retitled
    successor still pairs with its predecessor. Keys carry the level and the
    parent, so a `### Limits` under two different `## ` headings stays two
    units. Lines are whitespace-normalized, blank lines dropped, order kept,
    duplicates once."""
    title = ""
    units: dict[tuple[str, ...], list[str]] = {(TITLE_KEY,): []}
    key: tuple[str, ...] = (TITLE_KEY,)
    parent = ""
    for _, line, fenced in iter_body(text):
        m = None if fenced else HEADING_RE.match(line)
        if m and len(m.group(1)) == 1 and key == (TITLE_KEY,) and not title:
            title = norm_line(m.group(2))
            continue
        if m and len(m.group(1)) == 2:
            parent = section_key(m.group(2))
            key = ("##", parent)
            units.setdefault(key, [])
            continue
        if m and len(m.group(1)) == 3:
            key = ("###", parent, section_key(m.group(2)))
            units.setdefault(key, [])
            continue
        n = norm_line(line)
        if n and n not in units[key]:
            units[key].append(n)
    return title, units


def git_toplevel(repo_root: Path) -> Path | None:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    top = proc.stdout.strip()
    return Path(top).resolve() if proc.returncode == 0 and top else None


def added_pitches_since(repo_root: Path, base: str, pitches_root: Path) -> list[Path]:
    """Pitches added between `base` and HEAD — the successors a PR or a push introduces.

    `-z` with `core.quotePath=false`: git otherwise prints a path holding a
    non-ASCII byte (a Korean directory anywhere above the pitch) quoted and
    octal-escaped, which no `.md` suffix test recognises — the file was
    silently never judged."""
    try:
        proc = subprocess.run(
            ["git", "-c", "core.quotePath=false", "-C", str(repo_root), "diff", "--no-renames",
             "--diff-filter=A", "--name-only", "-z", base, "HEAD", "--", str(pitches_root)],
            capture_output=True, text=True, timeout=30, check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        sys.stderr.write(f"error: cannot diff against --base {base}: {detail.strip()}\n")
        sys.exit(2)
    root = git_toplevel(repo_root) or repo_root
    return [
        (root / name).resolve()
        for name in proc.stdout.split("\0")
        if name.endswith(".md") and Path(name).name not in NON_PITCH_FILES
    ]


def text_at(repo_root: Path, rev: str, path: Path) -> str | None:
    """`path`'s content at `rev`, or None when it did not exist there."""
    top = git_toplevel(repo_root)
    if top is None or not path.is_relative_to(top):
        return None
    proc = subprocess.run(
        ["git", "-C", str(top), "show", f"{rev}:{path.relative_to(top).as_posix()}"],
        capture_output=True, text=True, timeout=30, check=False,
    )
    return proc.stdout if proc.returncode == 0 else None


def supersede_diff_group(
    successors: list[Path],
    docs: dict[Path, tuple[dict[str, Any] | None, str]],
    tokens: list[str],
    repo_root: Path,
    base: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Diff one supersede group — successors judged together (a refactor-split's
    N files) against the union of their predecessors (a fold's N files).

    A unit present on both sides with different lines is a `modify`, one
    only in the successors an `add`, one only in the predecessors a
    `remove`. Each must be declared in some successor's `changes` with that
    kind; a declaration that matches no change is stale and also fails, so
    `changes` is a true account of the diff in both directions. Lines are
    compared as sets — a split may repeat a cross-cutting line in every file,
    and a fold merges two edge-case tables in any order. With `base`, a
    predecessor that existed at `base` is read as it was there, so an edit
    to the predecessor in the same change cannot make the diff agree."""
    def rel(p: Path) -> str:
        return str(p.relative_to(repo_root)) if p.is_relative_to(repo_root) else str(p)

    normative = _bracketed_normative_re(tokens)
    violations: list[str] = []
    preds: list[Path] = []
    for s in successors:
        for t in supersede_targets(docs[s][0], "pitch"):
            p = (s.parent / t).resolve()
            if p not in preds:
                preds.append(p)
    label = " + ".join(rel(s) for s in successors)
    missing = [p for p in preds if p not in docs]
    report: dict[str, Any] = {
        "successors": [rel(s) for s in successors],
        "predecessors": [rel(p) for p in preds],
        "changes": [],
    }
    if missing:
        violations.append(
            f"{label}: cannot diff — predecessor not found: {', '.join(rel(p) for p in missing)}"
        )
        return report, violations

    pred_text: dict[Path, str] = {}
    for p in preds:
        at_base = text_at(repo_root, base, p) if base is not None else None
        pred_text[p] = at_base if at_base is not None else docs[p][1]
        if at_base is not None:
            report["predecessors"][preds.index(p)] += f"@{base}"

    def union(texts: list[str]) -> tuple[list[str], dict[tuple[str, ...], list[str]]]:
        titles: list[str] = []
        merged: dict[tuple[str, ...], list[str]] = {}
        for text in texts:
            title, units = diff_units(text)
            titles.append(title)
            for k, lines in units.items():
                bucket = merged.setdefault(k, [])
                bucket.extend(x for x in lines if x not in bucket)
        return titles, merged

    succ_titles, after = union([docs[s][1] for s in successors])
    _, before = union([pred_text[p] for p in preds])
    keys = list(dict.fromkeys([*after, *before]))

    # A unit's name is its heading; where two units share a heading, `## X`
    # and `<parent> / X` tell them apart, in the report and in `changes`.
    short = {k: (k[-1] if k[0] != TITLE_KEY else "") for k in keys}
    clash = {n for n in short.values() if n and list(short.values()).count(n) > 1}

    def shown(k: tuple[str, ...]) -> str:
        if k[0] == TITLE_KEY:
            return f"# {succ_titles[0]}"
        if k[-1] not in clash:
            return k[-1]
        return f"## {k[1]}" if k[0] == "##" else (f"{k[1]} / {k[2]}" if k[1] else f"### {k[2]}")

    def resolve(raw: str) -> tuple[tuple[str, ...] | None, str | None]:
        """The unit a `changes[].section` names, or (None, why not).

        `<parent> / <child>` names a `### ` under a `## `; when no such pair
        exists the whole string is read as one heading, because a heading may
        itself hold " / " (「결제 시점 본인 잠금 (PIN / 생체)」 — before v0.18 it
        was split and reported as no such section)."""
        raw = raw.strip()
        if re.match(r"^#(?!#)\s", raw):
            return (TITLE_KEY,), None
        if raw.startswith("### "):
            want = [k for k in keys if k[0] == "###" and k[2] == section_key(raw)]
        elif raw.startswith("## "):
            want = [k for k in keys if k[0] == "##" and k[1] == section_key(raw)]
        else:
            want = []
            if " / " in raw:
                parent, _, child = raw.partition(" / ")
                want = [k for k in keys if k[0] == "###" and k[1] == section_key(parent) and k[2] == section_key(child)]
            if not want:
                want = [k for k in keys if k[0] != TITLE_KEY and k[-1] == section_key(raw)]
            if not want and section_key(raw) in succ_titles:
                return (TITLE_KEY,), None
        if len(want) == 1:
            return want[0], None
        if not want:
            return None, "the pitch has no such section"
        return None, (
            "it names more than one section — write "
            + " or ".join(f"`{shown(k)}`" for k in want)
        )

    declared: dict[tuple[str, ...], str] = {}
    for s in successors:
        changes = (docs[s][0] or {}).get("changes")
        if not isinstance(changes, list):
            continue
        for entry in changes:
            if not (isinstance(entry, dict) and isinstance(entry.get("section"), str) and section_key(entry["section"])):
                continue  # the shape check reports it
            key, why = resolve(entry["section"])
            if key is None:
                violations.append(
                    f"{label}: «{entry['section'].strip()}» is declared `{entry.get('kind')}` in `changes`, but {why}"
                )
                continue
            declared[key] = str(entry.get("kind"))

    rows: list[dict[str, Any]] = []
    changed: set[tuple[str, ...]] = set()
    for key in keys:
        a, b = after.get(key), before.get(key)
        if a is not None and b is not None and set(a) == set(b):
            continue
        if key == (TITLE_KEY,) and not (a or b):
            continue  # a retitle alone is not a change in content
        changed.add(key)
        kind = "add" if b is None else "remove" if a is None else "modify"
        removed = [x for x in (b or []) if x not in set(a or [])]
        added = [x for x in (a or []) if x not in set(b or [])]
        rows.append({"section": shown(key), "kind": kind, "declared": declared.get(key),
                     "removed": removed, "added": added})
        want = declared.get(key)
        if want == kind:
            continue
        head = (
            f"{label}: «{shown(key)}» — {kind} not declared in `changes`"
            if want is None
            else f"{label}: «{shown(key)}» is declared `{want}` but the change is `{kind}`"
        )
        sample: list[str] = []
        for sign, lines in (("-", removed), ("+", added)):
            ordered = [x for x in lines if normative.search(x)] + [x for x in lines if not normative.search(x)]
            for x in ordered[:DIFF_SAMPLE_LINES]:
                sample.append(f"{sign} {x if len(x) <= 160 else x[:157] + '...'}")
            if len(ordered) > DIFF_SAMPLE_LINES:
                sample.append(f"{sign} (+{len(ordered) - DIFF_SAMPLE_LINES} more line(s))")
        violations.append(head + ("\n  " + "\n  ".join(sample) if sample else ""))
    for key, kind in declared.items():
        if key not in changed:
            violations.append(f"{label}: «{shown(key)}» is declared `{kind}` in `changes`, but nothing in it changed")
    report["changes"] = rows
    return report, violations


def run_supersede_diff(
    paths: list[Path],
    base: str | None,
    pitches_root: Path | None,
    repo_root: Path,
    tokens: list[str],
    as_json: bool,
) -> int:
    """`--supersede-diff`: does each judged successor differ from its
    predecessor(s) only where its `changes` says it does? (v0.17+)

    Why it exists: supersedes that claimed to inherit text unchanged drifted
    when the body was re-authored — measured 2026-11-06 in lounge-x-spec, one
    kept 5 of 15 inherited normative lines identical and added a duty, another
    resurrected three items its parent had removed — while single-purpose
    supersede PRs stayed byte-identical outside their change. The authoring
    skill now copies the predecessor and edits declared hunks; this proves it.

    Judged: the given paths, plus with `base` every pitch added in base..HEAD.
    A judged pitch whose `supersedes` is null is skipped with a note; one whose
    frontmatter or `supersedes` / `changes` is malformed is a violation, since
    this mode runs on its own in a pre-push hook. Successors sharing a
    predecessor — directly or through another successor — are judged as one
    group, whatever the order they were given in, so pass every file of a
    split together (`--base` does). Exit 0 clean, 1 on any violation, 2 when
    it cannot run (no pitch directory, a path outside it, git failing)."""
    if pitches_root is None or not pitches_root.is_dir():
        sys.stderr.write(
            f"error: --supersede-diff needs the repo's pitch directory, and "
            f"{pitches_root if pitches_root is not None else 'this repo mode'} is none\n"
        )
        return 2
    root = pitches_root.resolve()
    repo_root = repo_root.resolve()
    judged: list[Path] = []
    for p in paths:
        q = p.resolve()
        if not q.is_file() or not q.is_relative_to(root):
            sys.stderr.write(f"error: --supersede-diff {p}: not a pitch file under {root}\n")
            return 2
        judged.append(q)
    if base is not None:
        judged.extend(added_pitches_since(repo_root, base, root))
    judged = list(dict.fromkeys(judged))

    def rel(p: Path) -> str:
        return str(p.relative_to(repo_root)) if p.is_relative_to(repo_root) else str(p)

    docs: dict[Path, tuple[dict[str, Any] | None, str]] = {}
    for p in iter_docs(root, "pitch"):
        docs[p.resolve()] = (load_frontmatter(p), p.read_text(encoding="utf-8"))

    violations: list[str] = []
    successors: list[Path] = []
    for p in judged:
        fm = docs.get(p, (None, ""))[0]
        if fm is None:
            violations.append(f"{rel(p)}: frontmatter missing or malformed — what it supersedes cannot be read")
            continue
        problem = supersedes_shape_problem(fm.get("supersedes"), "pitch")
        if problem:
            violations.append(f"{rel(p)}: {problem}")
            continue
        if "changes" in fm:
            violations.extend(f"{rel(p)}: {x}" for x in changes_shape_problems(fm, "pitch"))
        if supersede_targets(fm, "pitch"):
            successors.append(p)
        else:
            sys.stderr.write(f"note: {p}: supersedes nothing — no predecessor to diff against.\n")

    # Connected components over shared predecessors: a successor that bridges
    # two groups merges them, so the grouping never depends on argument order.
    groups: list[tuple[list[Path], set[Path]]] = []
    for s in successors:
        mine = {(s.parent / t).resolve() for t in supersede_targets(docs[s][0], "pitch")}
        members, preds = [s], set(mine)
        for g in [g for g in groups if g[1] & mine]:
            groups.remove(g)
            members = g[0] + members
            preds |= g[1]
        groups.append((members, preds))

    reports: list[dict[str, Any]] = []
    for members, _ in groups:
        report, found = supersede_diff_group(members, docs, tokens, repo_root, base)
        reports.append(report)
        violations.extend(found)

    if as_json:
        print(json.dumps({"groups": reports, "violations": violations, "clean": not violations}, ensure_ascii=False))
    else:
        for report in reports:
            print(f"{' + '.join(report['successors'])}  <-  {' + '.join(report['predecessors'])}")
            if not report["changes"]:
                print("  (no difference outside the frontmatter)")
            for row in report["changes"]:
                mark = "declared" if row["declared"] == row["kind"] else "UNDECLARED"
                print(f"  {row['kind']:<7} {mark:<10} {row['section']}")
        sys.stdout.flush()  # the summary reads first; the violations below explain it
        if violations:
            for v in violations:
                sys.stderr.write(v + "\n")
            sys.stderr.write(f"\n{len(violations)} violation(s) found.\n")
        else:
            print(f"supersede diff: {len(successors)} successor(s), every change declared.")
    return 1 if violations else 0


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
    parser.add_argument(
        "--supersede-diff",
        nargs="*",
        type=Path,
        metavar="PITCH",
        help=(
            "Instead of validating, diff each given successor pitch against its "
            "`supersedes` target(s), `### ` sub-section by sub-section after "
            "whitespace normalization, and fail on any difference its `changes` "
            "frontmatter does not declare (or a declaration nothing matches). "
            "Pass every file of a split together. With --base, also judge every "
            "pitch added since that commit. Exit 0 clean, 1 on a violation, 2 "
            "when it cannot run."
        ),
    )
    parser.add_argument(
        "--base",
        metavar="REV",
        help=(
            "With --supersede-diff, judge every pitch added in REV..HEAD — the "
            "PR base or the pre-push tip."
        ),
    )
    args = parser.parse_args()
    if args.base is not None and args.supersede_diff is None:
        parser.error("--base needs --supersede-diff")
    if args.supersede_diff is not None and not args.supersede_diff and args.base is None:
        parser.error("--supersede-diff needs PITCH paths, --base REV, or both")

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
    contract_frozen_count = 0
    disagreement_vocab = profile_disagreement_vocabulary(profile) if contract else None
    # The profile's wording rules, compiled once. A rule the compiler cannot
    # trust is a violation (v0.16+), never a quietly weaker check — `lint`
    # exits 2 on the same rule. The earliest `since` decides from when a
    # contested ticket's creation date must be recorded.
    contract_wording = (
        disagreement_vocab["wording"] if disagreement_vocab is not None
        else _contract.compile_wording((profile or {}).get("requirement_contract") or {}) if contract
        else None
    )
    created_at_cutoff = _contract.earliest_since(contract_wording) if contract_wording is not None else None
    since_withheld: dict[str, int] = {}
    if contract and args.strict_body and disagreement_vocab is None:
        sys.stderr.write(
            "warning: requirement_contract is declared in config.yml but the active "
            "profile lacks sections[id=requirement_disagreement] or "
            "requirement_contract.disagreement — the disagreement-outcome check is "
            "skipped. Run /immutable:migrate to pick up the bundled vocabulary.\n"
        )
    elif contract and args.strict_body and disagreement_vocab is not None and not disagreement_vocab["correction_rules"]:
        sys.stderr.write(
            "warning: the active profile has no requirement_contract.wording_rules applying "
            "to corrections and no requirement_contract.disagreement.deferral_patterns — "
            "corrections that defer instead of deciding are not checked. Run "
            "/immutable:migrate to pick up the bundled rules.\n"
        )
    elif contract and args.strict_body and disagreement_vocab is not None and not disagreement_vocab["has_wording_rules"]:
        sys.stderr.write(
            "warning: the active profile predates requirement_contract.wording_rules "
            "(profile_schema 5) — corrections are checked against the legacy "
            "disagreement.deferral_patterns only. Run /immutable:migrate to pick up "
            "the bundled rules.\n"
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

    if args.supersede_diff is not None:
        return run_supersede_diff(
            args.supersede_diff, args.base, dirs.get("pitch"), repo_root, normative_tokens, args.json
        )

    # v0.17+: the size ceiling and the cross-pitch reference rules. A team
    # profile that predates them reads the bundled default's values, and says so.
    bundled_profile = load_bundled_profile(config)
    profile_problems: list[str] = []
    max_bytes, max_bytes_bundled = profile_max_bytes(profile, bundled_profile, profile_problems)
    precedence_keywords, keywords_bundled = profile_precedence_keywords(
        profile, bundled_profile, profile_problems
    )
    if args.strict_body and (max_bytes_bundled or keywords_bundled) and config.get("profile"):
        fields = [n for n, b in (("max_bytes", max_bytes_bundled), ("precedence_keywords", keywords_bundled)) if b]
        sys.stderr.write(
            f"note: the active profile has no {' / '.join(fields)} (profile_schema 8) — using the "
            f"bundled default-{config.get('team_language', 'en')} value. Run /immutable:migrate.\n"
        )
    # v0.18+: the per-field input contract. A team profile without the section
    # reads the bundled vocabulary and only warns — see profile_input_contract.
    input_contract = profile_input_contract(profile, bundled_profile, profile_problems)
    input_counts: dict[str, int] = {}
    if args.strict_body and input_contract is not None and input_contract["from_bundled"] and config.get("profile"):
        unmigrated = "sections[id=input_contract]" in input_contract["from_bundled"]
        sys.stderr.write(
            f"note: the active profile has no {' / '.join(input_contract['from_bundled'])} (profile_schema 9) — "
            f"using the bundled default-{config.get('team_language', 'en')} value"
            + (
                "; an undeclared input is warned, never blocked, until /immutable:migrate adds the "
                "section with its since date.\n" if unmigrated else ". Run /immutable:migrate.\n"
            )
        )
    if args.strict_body and input_contract is not None and not input_contract["markers"]:
        # An empty list is a team's choice, never a silent one: say what it turns off.
        sys.stderr.write(
            "note: no input_markers are in force — a normative line that speaks of a user-entered "
            "value is never detected; only a present input table is checked.\n"
        )

    pitches_ref_root, pitches_ref_error = resolve_pitches_for_reference(config, repo_root)

    # Allowlist comes from local pitches README when available,
    # otherwise from the reference root (app repo walks to sibling spec).
    allow = domain_allowlist(dirs.get("pitch") or pitches_ref_root)

    violations: list[str] = []
    strict_exempt_count = 0
    stale_citations: list[tuple[Path, Path, list[Path]]] = []

    # An unresolvable spec repo is ONE configuration violation, reported once —
    # not one bogus "file not found" per ADR against a directory that isn't there.
    if pitches_ref_error:
        warn(violations, pitches_ref_error)

    types = DOC_TYPES if args.type == "all" else (args.type,)
    for doc_type in types:
        doc_root = dirs.get(doc_type)
        if doc_root is None:
            continue
        # Every pitch's frontmatter by resolved path, and who supersedes whom —
        # the cross-pitch reference rules resolve a cited path against them.
        pitch_index: dict[Path, dict[str, Any] | None] = {}
        pitch_successors: dict[Path, list[Path]] = {}
        if doc_type == "pitch" and args.strict_body:
            for p in iter_docs(doc_root, doc_type):
                pfm = load_frontmatter(p)
                pitch_index[p.resolve()] = pfm
                for t in supersede_targets(pfm, doc_type):
                    pitch_successors.setdefault((p.parent / t).resolve(), []).append(p.resolve())
        path_re = pitch_path_re(config)
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
                # Invariant 9 is frozen on a `deprecated: true` doc. In an
                # append-only repo a dead doc has NO remedy — it cannot be
                # edited and it cannot be superseded (that would revive it) —
                # so a violation there is noise a tightened check creates
                # retroactively, and `coverage` / `drift` never read it anyway.
                # An ACTIVE doc keeps the error: its remedy is a new pitch.
                doc_frozen = fm_checked.get("deprecated") is True
                if doc_frozen:
                    contract_frozen_count += 1
                else:
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
                        # v0.17+: frozen like invariant 9 — a deprecated pitch has
                        # no remedy, and nobody implements from it.
                        if doc_type == "pitch" and not doc_frozen:
                            check_pitch_size(md_path, max_bytes, violations)
                            check_pitch_references(
                                md_path, fm_checked, doc_root, path_re, pitch_index,
                                pitch_successors, precedence_keywords, violations,
                                stale_citations,
                            )
                            if input_contract is not None:
                                check_input_contract(
                                    md_path, input_contract, normative_tokens, violations, input_counts,
                                )
                        if doc_type == "pitch" and contract_required and not doc_frozen:
                            if strict_body_in_scope(md_path, since_contract):
                                check_ticket_presence(md_path, fm_checked, violations)
                            else:
                                contract_exempt_count += 1
                        if doc_type == "pitch" and disagreement_vocab is not None:
                            if created_at_cutoff is not None and not doc_frozen:
                                check_ticket_created_at(
                                    md_path, fm_checked, created_at_cutoff, disagreement_vocab["heading"],
                                    contract.get("repo") if contract else None, violations,
                                )
                            validate_pitch_disagreement_outcomes(
                                md_path, disagreement_vocab, violations,
                                fm_checked, contract.get("repo") if contract else None,
                                since_withheld,
                            )
                    else:
                        strict_exempt_count += 1
                collected.append((md_path, fm_checked))
        check_supersede_chain_integrity(doc_type, collected, violations)

    if args.strict_body:
        for problem in profile_problems:
            warn(violations, f"active profile: {problem}")

    for problem in (contract_wording or {}).get("problems", []):
        warn(
            violations,
            f"active profile: requirement_contract.{problem} — the rule is not applied until the "
            f"profile is fixed (requirement_contract.py lint refuses the same rule)",
        )

    # v0.15+: the acknowledgement ledger beside config.yml, shape only — whether
    # each entry's hit still exists needs the live ticket (`requirement_contract.py
    # gate`). Always on once the repo opts into the contract; the reader is the
    # gate's own (`ledger_entries`), so the two cannot disagree about the format.
    ledger_path = config_path.parent / _contract.LEDGER_FILENAME
    if contract and ledger_path.is_file():
        try:
            ledger_data = yaml.safe_load(ledger_path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, ValueError) as exc:
            warn(violations, f"{ledger_path}: acknowledgement ledger is not valid YAML: {exc}")
        else:
            for problem in _contract.ledger_entries(ledger_data, contract.get("repo"))[1]:
                warn(violations, f"{ledger_path}: acknowledgement ledger: {problem}")

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
    if stale_citations:
        forked = [(c, t, e) for c, t, e in stale_citations if len(e) > 1]
        sys.stderr.write(
            f"note: {len(stale_citations)} citation(s) name an older version of a pitch; each "
            f"resolves along its supersede chain (the read guard names the successor). "
            f"{len(forked)} of them fork into several active pitches, so the reader picks the owner:\n"
        )
        for citer, target, ends in forked:
            sys.stderr.write(
                f"  {citer} -> {target.parent.name}/{target.name} -> {', '.join(e.name for e in ends)}\n"
            )
    if input_counts and input_contract is not None:
        parts = []
        if input_counts.get("undeclared"):
            parts.append(
                f"{input_counts['undeclared']} pitch(es) speak of a user-entered value without a "
                f"`## {input_contract['heading']}` section and were warned, not blocked"
            )
        if input_counts.get("unnamed"):
            parts.append(f"{input_counts['unnamed']} normative line(s) name no field of their pitch's table")
        sys.stderr.write(f"note: input contract: {'; '.join(parts)}.\n")
    if contract_frozen_count:
        sys.stderr.write(
            f"note: {contract_frozen_count} deprecated doc(s) frozen: the requirement-contract "
            "checks do not apply to a doc that can no longer be edited or superseded.\n"
        )
    if args.strict_body and contract_required and since_contract is not None:
        sys.stderr.write(
            f"note: requirement_contract.since {since_contract}: {contract_exempt_count} "
            f"pitch(es) predate the contract; presence rule not applied to them.\n"
        )
    if since_withheld:
        detail = ", ".join(f"{rule} ×{n}" for rule, n in sorted(since_withheld.items()))
        sys.stderr.write(
            f"note: since-gated wording rule(s) not applied to corrections on tickets created "
            f"before their since date: {detail}.\n"
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
