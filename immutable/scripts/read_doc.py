#!/usr/bin/env python3
"""Read a text file, withholding deprecated immutable documents before stdout."""
import argparse
import json
import os
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
        "For an intentional raw-body audit or supersede review, use cat or git show.",
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claude-hook", metavar="ROOT", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    path = args.file.absolute()
    root = args.claude_hook
    if root is None:
        # Check both names: a linked skill checkout, a document symlink inside
        # a consumer, and an outside alias to a consumer document all work.
        for candidate in (path.resolve(strict=True), path):
            if candidate.suffix == ".md":
                root = next((p for p in candidate.parents if (p / ".immutable-prd").is_dir()), None)
                if root:
                    path = candidate
                    break

    raw = path.read_bytes()
    content = None
    if root is not None:
        try:
            import yaml  # noqa: F401  (preserve Claude's missing-dependency diagnostic)
        except ImportError:
            msg = "[immutable-deprecated-guard] PyYAML missing. Install PyYAML to read SDD documents."
            if args.claude_hook is None:
                sys.exit(msg)
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PostToolUse", "additionalContext": msg + " Claude Read gate is INERT.",
            }}))
            return
        # Classify exactly the bytes we might release, even if the file changes concurrently.
        text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        content = replacement(path, root, text)
    if args.claude_hook is not None:
        if content is not None:
            print(json.dumps(claude_result(path, content)))
    else:
        sys.stdout.buffer.write(raw if content is None else content.encode("utf-8"))


if __name__ == "__main__":
    try:
        main()
    except (OSError, UnicodeError) as exc:
        sys.exit(str(exc))
