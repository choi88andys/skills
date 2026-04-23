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
     spec/single-repo mode, in sibling spec repo for app-repo mode).
  4. Reference policy — ADR `references.pitches` non-empty unless the domain is
     declared `adr_only` in the profile's `domain_allowlist.reserved_domains`
     (e.g., `_global`).
  5. Domain allowlist — `pitches/README.md` rows, with reserved-domain
     special-cases sourced from the profile.
  6. Filename format — matches the profile's `naming.filename_pattern`
     (falls back to `YYYY-MM-DD-<kebab-slug>.md` when no profile is set).
  7. Single-active-per-chain invariant per (domain, type).
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

Not covered (deferred): cycle detection on supersede chains.

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
import json
import re
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
    except yaml.YAMLError as exc:
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

    return data


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
        return yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return None


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


def resolve_pitches_for_reference(
    config: dict[str, Any], repo_root: Path
) -> Path | None:
    """Pitches directory used for `references.pitches` existence checks.

    Spec-repo / single-repo: same as the local pitches dir.
    App-repo: resolved relative to spec_repo_path + pitches_path_in_spec.
    """
    mode = config["repo_mode"]
    if mode in ("two-repo-spec", "single-repo"):
        return repo_root / config["pitches_path"]
    # app-repo
    spec_repo = config.get("spec_repo_path")
    if not spec_repo:
        return None  # existence not validated; user opted out
    spec_root = (repo_root / spec_repo).resolve()
    pitches_sub = config.get("pitches_path_in_spec", "pitches/")
    return spec_root / pitches_sub


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


def check_single_active_invariant(
    doc_type: str,
    docs: list[tuple[Path, dict[str, Any]]],
    violations: list[str],
) -> None:
    by_chain: dict[tuple[str, str], list[Path]] = {}
    for path, fm in docs:
        if fm.get("deprecated") is True:
            continue
        domain = fm.get("domain") or "_global"
        by_chain.setdefault((domain, doc_type), []).append(path)
    for (domain, dtype), paths in by_chain.items():
        if len(paths) > 1:
            warn(
                violations,
                f"single-active invariant violated for ({domain!r}, {dtype!r}): "
                f"{len(paths)} active files — {[str(p) for p in paths]}",
            )


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
    args = parser.parse_args()

    config_path = args.config or find_config()
    if config_path is None:
        die(
            "could not find .immutable-prd/config.yml via walk-up. "
            "Pass --config explicitly or run from within a configured repo."
        )
    assert config_path is not None
    config = load_config(config_path)

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
    strict_structure_enabled = bool(
        args.strict_body
        and user_stories_section
        and user_stories_structure == "per_story_grouped"
        and user_stories_heading
    )

    dirs = resolve_dirs(config, repo_root)
    pitches_ref_root = resolve_pitches_for_reference(config, repo_root)

    # Allowlist comes from local pitches README when available,
    # otherwise from the reference root (app repo walks to sibling spec).
    allow = domain_allowlist(dirs.get("pitch") or pitches_ref_root)

    violations: list[str] = []

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
                if args.strict_body:
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
                collected.append((md_path, fm_checked))
        check_single_active_invariant(doc_type, collected, violations)

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
