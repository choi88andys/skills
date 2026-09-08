#!/usr/bin/env python3
"""requirement_contract.py — read the binding sections of a tracker Epic.

The immutable plugin's *requirement contract* lets a pitch be authored against
a tracker ticket whose designated sections bind it — in the pilot, an Epic's
「완료 조건」 and 「QA 통과 리스트」. The contract has two machine halves, and
BOTH read the ticket through this script so they cannot disagree about what
an item is or what its text is:

  * `/immutable:prd` Stage 1.5 — fetches the Epic, classifies every binding
    item, and quotes the ones the pitch commits to (with an `as of` marker).
  * The consuming spec repo's CI — re-reads the Epic later and compares the
    pitch's quoted text against the live body to report drift.

Subcommands
  parse   read a ticket body from a file (`-` = stdin) and emit JSON
  fetch   `gh issue view <N> --repo <owner/name>`, then parse; adds `source`

The script carries NO section vocabulary of its own. Which headings bind is
passed by the caller — `--binding ID=HEADING`, repeatable — and the plugin
sources those from the active profile, so a team's tracker template is data,
not code. Everything else the parser recognises is plain GitHub-flavoured
markdown:

  * a binding section is the slice from its heading (any `#` level; 「」 marks,
    a trailing colon, case and whitespace are ignored when matching) up to the
    next heading of the same or a higher level;
  * inside it, a whole-line `**bold**` label OR a deeper heading starts a
    group. The Epic template's groups are bold lines between `###` headings,
    so a heading-only split silently loses them;
  * an item is a task-list line (`- [ ]` / `- [x]`), a plain bullet, or an
    ordered-list line; an indented non-list line directly below continues the
    item above;
  * HTML comments are removed first (issue templates ship their guidance in
    them), and fenced code never yields headings, groups, or items.

Output contract (`schema: 1`) — always JSON on stdout, even on failure:

  bindings[]   one per `--binding`, in caller order: `id`, `heading`, `found`,
               the matched heading's `matched_heading` / `level` / `line`,
               `groups[]` of `items[]`, and `item_count`
  items        `ordinal` (1-based within the section, across groups), `group`,
               `depth`, `checkbox`, `checked`, `struck`, `text`, `line`
  sections[]   the whole outline, binding or not, each with its raw slice —
               the non-binding context a classifier needs to spot a
               self-contradiction (a 비고 / 미해결 note) lives here
  warnings[]   tolerated but worth a look: plain bullets, prose lines, empty
               items, duplicate item text, fenced code inside a binding section
  errors[]     what made the exit code non-zero
  source       `fetch` only: repo, number, title, url, state, labels,
               milestone, updated_at, fetched_at, as_of

`text` is the ONE canonical form both halves compare: NFC-normalised, outer
whitespace stripped, inner whitespace runs collapsed to a single space, inline
markdown kept verbatim. A struck item keeps its `~~`; `struck: true` says so.

Exit codes
  0  every binding section was found and holds at least one item
  1  a binding section is missing or empty — JSON is still emitted, so the
     caller renders `errors` instead of guessing
  2  usage error, or `fetch` could not reach the ticket

Requires python3 only (no PyYAML). `fetch` needs the `gh` CLI on PATH,
authenticated for the target repo. Line numbers in the output are 1-based
and refer to the body as fetched (comments are blanked, not deleted, so they
stay stable).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from typing import Any

SCHEMA = 1

HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
HEADING_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+(\S.*?)[ \t]*$")
BOLD_LABEL_RE = re.compile(r"^\s*(?:\*\*|__)(.+?)(?:\*\*|__)\s*[:：]?\s*$")
CHECKBOX_RE = re.compile(r"^(\s*)[-*+][ \t]+\[([ xX])\][ \t]*(.*)$")
BULLET_RE = re.compile(r"^(\s*)[-*+][ \t]+(.*)$")
ORDERED_RE = re.compile(r"^(\s*)\d{1,3}[.)][ \t]+(.*)$")
STRUCK_RE = re.compile(r"^~~.+~~$")
BINDING_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
WS_RE = re.compile(r"\s+")
HEADING_QUOTES = "「」『』\"'“”‘’"
EXCERPT_LEN = 60
GH_TIMEOUT_SECONDS = 60


# --------------------------------------------------------------------------
# text normalisation — the one definition both halves of the contract share
# --------------------------------------------------------------------------


def norm_text(s: str) -> str:
    """Canonical item text: NFC, trimmed, inner whitespace collapsed."""
    return WS_RE.sub(" ", unicodedata.normalize("NFC", s)).strip()


def norm_heading(s: str) -> str:
    """Heading match key: `norm_text`, then 「」-style quotes and colons stripped
    from both ends (in any order — `「완료 조건」:` must match `완료 조건`), casefold."""
    return norm_text(s).strip(HEADING_QUOTES + ":：").strip().casefold()


def excerpt(s: str) -> str:
    s = norm_text(s)
    return s if len(s) <= EXCERPT_LEN else s[: EXCERPT_LEN - 1] + "…"


# --------------------------------------------------------------------------
# body → lines, fence mask, outline
# --------------------------------------------------------------------------


def preprocess(body: str) -> list[str]:
    body = unicodedata.normalize("NFC", body.replace("\r\n", "\n").replace("\r", "\n"))
    # Blank comments instead of deleting them so every reported line number
    # still points at the same line of the body the reader sees on GitHub.
    body = HTML_COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), body)
    return body.split("\n")


def fenced_lines(lines: list[str]) -> set[int]:
    inside: set[int] = set()
    fence: str | None = None
    for i, ln in enumerate(lines):
        m = FENCE_RE.match(ln)
        if m:
            tok = m.group(1)[0]
            if fence is None:
                fence = tok
                inside.add(i)
                continue
            if tok == fence:
                fence = None
                inside.add(i)
                continue
        if fence is not None:
            inside.add(i)
    return inside


def outline(lines: list[str], fenced: set[int]) -> list[dict[str, Any]]:
    heads: list[dict[str, Any]] = []
    for i, ln in enumerate(lines):
        if i in fenced:
            continue
        m = HEADING_RE.match(ln)
        if m:
            heads.append({"level": len(m.group(1)), "title": norm_text(m.group(2)), "line": i})
    for idx, h in enumerate(heads):
        end = len(lines)
        for nxt in heads[idx + 1 :]:
            if nxt["level"] <= h["level"]:
                end = nxt["line"]
                break
        h["end"] = end
    return heads


# --------------------------------------------------------------------------
# binding section → groups of items
# --------------------------------------------------------------------------


def match_item(ln: str) -> tuple[str, bool, bool | None, str] | None:
    """(indent, is_checkbox, checked, raw_text) for a list line, else None."""
    m = CHECKBOX_RE.match(ln)
    if m:
        return m.group(1), True, m.group(2).lower() == "x", m.group(3)
    m = BULLET_RE.match(ln)
    if m:
        return m.group(1), False, None, m.group(2)
    m = ORDERED_RE.match(ln)
    if m:
        return m.group(1), False, None, m.group(2)
    return None


def parse_section(
    lines: list[str], fenced: set[int], head: dict[str, Any], label: str, warnings: list[str]
) -> tuple[list[dict[str, Any]], int]:
    groups: list[dict[str, Any]] = []
    current_group: dict[str, Any] | None = None
    current_item: dict[str, Any] | None = None
    ordinal = 0
    plain = 0
    fenced_warned = False

    def new_group(name: str | None) -> dict[str, Any]:
        g = {"index": len(groups), "label": name, "items": []}
        groups.append(g)
        return g

    for i in range(head["line"] + 1, head["end"]):
        ln = lines[i]
        if i in fenced:
            current_item = None
            if not fenced_warned:
                warnings.append(f"{label}: fenced code inside the section is ignored (line {i + 1})")
                fenced_warned = True
            continue
        if not ln.strip():
            current_item = None
            continue
        hm = HEADING_RE.match(ln)
        if hm:
            current_group = new_group(norm_text(hm.group(2)))
            current_item = None
            continue
        item = match_item(ln)
        if item is not None:
            indent, is_checkbox, checked, raw = item
            text = norm_text(raw)
            if not text:
                warnings.append(f"{label}: empty list item ignored (line {i + 1})")
                current_item = None
                continue
            if current_group is None:
                current_group = new_group(None)
            ordinal += 1
            if not is_checkbox:
                plain += 1
            current_item = {
                "ordinal": ordinal,
                "group": current_group["label"],
                "depth": len(indent.expandtabs(4)) // 2,
                "checkbox": is_checkbox,
                "checked": checked,
                "struck": False,
                "text": text,
                "line": i + 1,
            }
            current_group["items"].append(current_item)
            continue
        bm = BOLD_LABEL_RE.match(ln)
        if bm:
            current_group = new_group(norm_text(bm.group(1)))
            current_item = None
            continue
        if current_item is not None and ln[:1] in (" ", "\t"):
            current_item["text"] = norm_text(current_item["text"] + " " + ln)
            continue
        current_item = None
        warnings.append(f"{label}: line {i + 1} is not a list item and was ignored: {excerpt(ln)}")

    seen: dict[str, int] = {}
    for g in groups:
        for it in g["items"]:
            it["struck"] = bool(STRUCK_RE.match(it["text"]))
            first = seen.setdefault(it["text"], it["line"])
            if first != it["line"]:
                warnings.append(
                    f"{label}: duplicate item text at lines {first} and {it['line']} — "
                    f"quotes cannot tell them apart: {excerpt(it['text'])}"
                )
    if plain:
        warnings.append(
            f"{label}: {plain} list item(s) without a task-list checkbox — "
            f"kept as items; the template uses `- [ ]`"
        )
    return groups, ordinal


def parse_body(body: str, bindings: list[tuple[str, str]]) -> dict[str, Any]:
    lines = preprocess(body)
    fenced = fenced_lines(lines)
    heads = outline(lines, fenced)
    warnings: list[str] = []
    errors: list[str] = []
    by_key: dict[str, list[dict[str, Any]]] = {}
    for h in heads:
        by_key.setdefault(norm_heading(h["title"]), []).append(h)

    binding_of_line: dict[int, str] = {}
    out_bindings: list[dict[str, Any]] = []
    for bid, heading in bindings:
        label = f"{bid} ({heading})"
        matches = by_key.get(norm_heading(heading), [])
        if not matches:
            present = ", ".join(f"{'#' * h['level']} {h['title']}" for h in heads) or "(no headings at all)"
            errors.append(f"binding section not found: {label} — headings present: {present}")
            out_bindings.append(
                {
                    "id": bid,
                    "heading": heading,
                    "found": False,
                    "matched_heading": None,
                    "level": None,
                    "line": None,
                    "groups": [],
                    "item_count": 0,
                }
            )
            continue
        if len(matches) > 1:
            where = ", ".join(str(h["line"] + 1) for h in matches)
            warnings.append(f"{label}: {len(matches)} headings match (lines {where}); using the first")
        head = matches[0]
        binding_of_line[head["line"]] = bid
        groups, count = parse_section(lines, fenced, head, label, warnings)
        if count == 0:
            errors.append(f"binding section has no list items: {label} (line {head['line'] + 1})")
        out_bindings.append(
            {
                "id": bid,
                "heading": heading,
                "found": True,
                "matched_heading": head["title"],
                "level": head["level"],
                "line": head["line"] + 1,
                "groups": groups,
                "item_count": count,
            }
        )

    sections = [
        {
            "heading": h["title"],
            "level": h["level"],
            "line": h["line"] + 1,
            "binding": binding_of_line.get(h["line"]),
            "text": "\n".join(lines[h["line"] + 1 : h["end"]]).strip("\n"),
        }
        for h in heads
    ]
    return {
        "schema": SCHEMA,
        "source": None,
        "bindings": out_bindings,
        "sections": sections,
        "warnings": warnings,
        "errors": errors,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_binding_args(parser: argparse.ArgumentParser, raw: list[str] | None) -> list[tuple[str, str]]:
    if not raw:
        parser.error("at least one --binding ID=HEADING is required (the plugin passes these from the profile)")
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for spec in raw:
        bid, sep, heading = spec.partition("=")
        bid, heading = bid.strip(), heading.strip()
        if not sep or not bid or not heading:
            parser.error(f"--binding expects ID=HEADING, got {spec!r}")
        if not BINDING_ID_RE.match(bid):
            parser.error(f"--binding id must match [a-z][a-z0-9_]*, got {bid!r}")
        if bid in seen:
            parser.error(f"--binding id given twice: {bid!r}")
        seen.add(bid)
        out.append((bid, heading))
    return out


def read_body(path: str) -> str:
    """UTF-8 always — never the locale's codec — so a C-locale CI runner and a
    ko_KR desktop read the same bytes the same way."""
    if path == "-":
        return sys.stdin.buffer.read().decode("utf-8")
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8")


def fetch_issue(repo: str, number: int) -> dict[str, Any]:
    if shutil.which("gh") is None:
        sys.stderr.write("error: `gh` CLI not found on PATH — needed for `fetch`\n")
        sys.exit(2)
    cmd = [
        "gh", "issue", "view", str(number), "--repo", repo,
        "--json", "number,title,body,url,state,labels,milestone,updatedAt",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, encoding="utf-8", timeout=GH_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        sys.stderr.write(f"error: gh did not answer within {GH_TIMEOUT_SECONDS}s for {repo}#{number}\n")
        sys.exit(2)
    except OSError as exc:
        sys.stderr.write(f"error: could not run gh: {exc}\n")
        sys.exit(2)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "(no output)"
        sys.stderr.write(f"error: gh exited {proc.returncode} for {repo}#{number}: {detail}\n")
        sys.exit(2)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"error: gh returned non-JSON for {repo}#{number}: {exc}\n")
        sys.exit(2)
    if not isinstance(data, dict) or "body" not in data:
        sys.stderr.write(f"error: gh output for {repo}#{number} carries no `body`\n")
        sys.exit(2)
    return data


def emit(result: dict[str, Any], compact: bool) -> None:
    payload = json.dumps(result, ensure_ascii=False, indent=None if compact else 2) + "\n"
    sys.stdout.buffer.write(payload.encode("utf-8"))
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="requirement_contract.py",
        description="Read the binding sections of a tracker Epic into JSON (see module docstring).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--binding", action="append", metavar="ID=HEADING",
            help="a binding section: stable id + the heading text as it appears on the ticket (repeatable)",
        )
        p.add_argument("--compact", action="store_true", help="single-line JSON")

    p_parse = sub.add_parser("parse", help="parse a ticket body from a file (`-` = stdin)")
    p_parse.add_argument("body", help="path to the body, or `-` for stdin")
    add_common(p_parse)

    p_fetch = sub.add_parser("fetch", help="gh issue view, then parse")
    p_fetch.add_argument("--repo", required=True, metavar="OWNER/NAME")
    p_fetch.add_argument("--issue", required=True, type=int, metavar="N")
    add_common(p_fetch)

    args = parser.parse_args(argv)
    bindings = parse_binding_args(parser, args.binding)

    if args.command == "parse":
        try:
            body = read_body(args.body)
        except (OSError, UnicodeDecodeError) as exc:
            parser.error(f"cannot read body: {exc}")
        result = parse_body(body, bindings)
    else:
        if not REPO_RE.match(args.repo):
            parser.error(f"--repo must be OWNER/NAME, got {args.repo!r}")
        if args.issue <= 0:
            parser.error("--issue must be a positive integer")
        data = fetch_issue(args.repo, args.issue)
        now = _dt.datetime.now().astimezone()
        result = parse_body(data.get("body") or "", bindings)
        milestone = data.get("milestone") or None
        result["source"] = {
            "tracker": "github",
            "repo": args.repo,
            "number": data.get("number", args.issue),
            "title": data.get("title"),
            "url": data.get("url"),
            "state": data.get("state"),
            "labels": [lb.get("name") for lb in (data.get("labels") or []) if isinstance(lb, dict)],
            "milestone": milestone.get("title") if isinstance(milestone, dict) else None,
            "updated_at": data.get("updatedAt"),
            "fetched_at": now.isoformat(timespec="seconds"),
            "as_of": now.date().isoformat(),
        }

    emit(result, args.compact)
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
