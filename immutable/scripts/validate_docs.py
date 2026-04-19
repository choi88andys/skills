#!/usr/bin/env python3
"""validate_docs.py — stand-alone validator for immutable-prd SDD repos (v0.3).

Checks the invariants documented in prd/SCHEMA.md for a repo that adopts the
v0.3 two-doc-type model: `pitch` (spec repo) + `adr` (app repo).

Designed to run:

  * from a pre-commit hook or CI workflow
  * from a future `/immutable:adr --validate` skill mode

Coverage (matches SCHEMA.md "Validation invariants"):

  1. `config.yml` parses and has required keys for the declared `repo_mode`.
  2. Each doc's frontmatter parses and contains required fields.
  3. Referenced pitch filenames resolve to an existing file (in this repo for
     spec/single-repo mode, in sibling spec repo for app-repo mode).
  4. Reference policy — ADR `references.pitches` non-empty unless `domain: _global`.
  5. Domain allowlist (with `_global` ADR special-case).
  6. Filename format matches `YYYY-MM-DD-<kebab-slug>.md`.
  7. Single-active-per-chain invariant per (domain, type).

Not covered (deferred): cycle detection on supersede chains, body-level
constraints (e.g., ADR "Consequences" section presence).

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


FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*\.md$")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

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


def check_filename(path: Path, violations: list[str]) -> None:
    if not FILENAME_RE.match(path.name):
        warn(
            violations,
            f"filename format violation: {path} (expected YYYY-MM-DD-<kebab-slug>.md)",
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
    violations: list[str],
) -> None:
    domain = fm.get("domain")
    if domain is None:
        warn(violations, f"{path}: missing frontmatter `domain`")
        return
    if domain == "_global":
        if doc_type != "adr":
            warn(
                violations,
                f"{path}: `_global` domain is reserved for ADRs; got doc_type={doc_type}",
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
    violations: list[str],
) -> None:
    refs = fm.get("references") or {}
    listed = refs.get("pitches") or []
    if not isinstance(listed, list):
        warn(violations, f"{path}: references.pitches must be a list")
        return

    # Reference policy: ADR must have ≥1 pitch unless _global.
    if doc_type == "adr":
        if not listed and fm.get("domain") != "_global":
            warn(
                violations,
                f"{path}: ADR references.pitches must be non-empty (or use domain: _global)",
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
            check_filename(md_path, violations)
            fm = load_frontmatter(md_path)
            fm_checked = check_frontmatter(md_path, doc_type, fm, violations)
            if fm_checked:
                check_domain(md_path, fm_checked, doc_type, allow, violations)
                check_references(
                    md_path, fm_checked, doc_type, pitches_ref_root, violations
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
