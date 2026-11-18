#!/usr/bin/env python3
"""Read a text file, withholding deprecated immutable documents before stdout."""
import argparse
import io
import itertools
import json
import os
import re
import shlex
import sys
from pathlib import Path


def log(path, outcome, detail):
    dest = os.environ.get("IMMUTABLE_DEPRECATED_GUARD_LOG")
    if dest:
        try:
            with open(dest, "a", encoding="utf-8") as stream:
                print(outcome, path, detail, sep="\t", file=stream)
        except OSError:
            pass


def replacement(path, root, text):
    from validate_docs import load_frontmatter, split_frontmatter, supersede_targets

    fm, header = split_frontmatter(text)
    if not fm or fm.get("deprecated") is not True:
        log(path, "pass", "active-or-unparsed")
        return None

    successors = []
    for sibling in sorted(path.parent.glob("*.md")):
        if sibling == path or sibling.name in ("README.md", "TEMPLATE.md"):
            continue
        try:
            meta = load_frontmatter(sibling)
        except (OSError, UnicodeError):
            continue
        if meta and path.name in supersede_targets(meta, meta.get("type", "pitch")):
            name = str(sibling.relative_to(root))
            if meta.get("deprecated") is True:
                name += " (itself deprecated — read it to follow the chain)"
            successors.append("  - " + name)

    lines = [
        header,
        "[IMMUTABLE DEPRECATED-DOC GUARD] Body withheld.",
        f"`{path.relative_to(root)}` is marked `deprecated: true` (frontmatter shown in full).",
        "Its body is a dead spec. Do not implement from it.",
        "",
    ]
    if successors:
        lines.extend(["Superseded by (implement from these instead):", *successors])
    else:
        lines.append("No successor found in this directory. Check the supersede history.")
    lines.extend([
        "",
        "Only for historical audit or supersede review, run:",
        shlex.join(["python3", "-B", str(Path(__file__).resolve()), "--audit", "--", str(path)]),
        "To un-deprecate, edit the deprecated flag in the visible frontmatter.",
    ])
    log(path, "withheld", f"successors={len(successors)}")
    return "\n".join(lines)


def claude_result(path, content):
    # Claude silently ignores updatedToolOutput unless it mirrors Read's file object.
    lines = content.count("\n") + 1
    return {"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "updatedToolOutput": {"type": "text", "file": {
            "filePath": str(path), "content": content, "numLines": lines,
            "startLine": 1, "totalLines": lines,
        }},
    }}


def document_scope(path):
    """Return the document spelling and nearest marker used to classify it."""
    path = path.absolute()
    for candidate in (path.resolve(), path):
        if candidate.suffix == ".md":
            root = next((p for p in candidate.parents if (p / ".immutable-prd").is_dir()), None)
            if root:
                return candidate, root
    return path, None


def read_document(path, root=None):
    """Classify exactly the bytes we might release, including during concurrent edits."""
    if root is None:
        path, root = document_scope(path)
    raw = path.read_bytes()
    if root is not None:
        import yaml  # Check before importing the validator, which exits if PyYAML is missing.

        text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        banner = replacement(path, root, text)
        if banner is not None:
            return (banner + "\n").encode("utf-8"), True
    return raw, False


def line_range(value):
    if not re.fullmatch(r"[1-9][0-9]*(?:,(?:[1-9][0-9]*|\$))?", value):
        raise ValueError("expected a positive line N, N,M or N,$")
    start, _, end = value.partition(",")
    first = int(start)
    return first - 1, None if end == "$" else max(first, int(end or start))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--claude-hook", metavar="ROOT", type=Path, help=argparse.SUPPRESS)
    mode.add_argument("--audit", action="store_true", help="show raw text for historical review")
    mode.add_argument("--lines", type=line_range, metavar="N[,M]", help="select active document lines")
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    if (args.claude_hook or args.lines or args.audit) and len(args.files) != 1:
        parser.error("this mode takes one file")
    for path in args.files:
        if args.audit:
            sys.stdout.buffer.write(b"[IMMUTABLE HISTORICAL AUDIT] For supersede/history review only.\n")
            sys.stdout.buffer.write(path.read_bytes())
            sys.stdout.buffer.write(b"\n[END IMMUTABLE HISTORICAL AUDIT]\n")
            return
        try:
            data, withheld = read_document(path, args.claude_hook)
        except ModuleNotFoundError as exc:
            if exc.name != "yaml":
                raise
            msg = "[immutable-deprecated-guard] PyYAML missing. Install PyYAML to read SDD documents."
            if args.claude_hook is None:
                sys.exit(msg)
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PostToolUse", "additionalContext": msg + " Claude Read gate is INERT.",
            }}))
            return
        if args.claude_hook is not None:
            if withheld:
                print(json.dumps(claude_result(path, data.decode("utf-8").rstrip("\n"))))
        elif args.lines and not withheld:
            sys.stdout.buffer.writelines(itertools.islice(io.BytesIO(data), *args.lines))
        else:
            sys.stdout.buffer.write(data)


if __name__ == "__main__":
    try:
        main()
    except (OSError, UnicodeError) as exc:
        sys.exit(str(exc))
