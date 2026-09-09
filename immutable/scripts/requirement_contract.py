#!/usr/bin/env python3
"""requirement_contract.py — read the binding sections of a tracker Epic.

The immutable plugin's *requirement contract* lets a pitch be authored against
a tracker ticket whose designated sections bind it — in the pilot, an Epic's
「완료 조건」 and 「QA 통과 리스트」. The contract has two machine halves, and
BOTH read the ticket through this script so they cannot disagree about what
an item is or what its text is:

  * `/immutable:prd` Stage 1.5 — fetches the Epic, judges every binding item,
    and records the ticket's identity + version coordinate in the pitch.
  * A drift check (the consuming repos' CI or tracker bot) — re-reads the
    Epic later and compares the recorded version against the live one, item
    by item, so a requirement cannot move underneath a pitch unnoticed.

Subcommands
  parse     read a ticket body from a file (`-` = stdin) and emit JSON
  fetch     obtain the ticket through an adapter, then parse; adds `source`
  drift     fetch the ticket and compare it with a recorded version coordinate
  coverage  fetch the ticket and reconcile the pitches that cite it: every
            binding item must be claimed by exactly one pitch (or shared by
            agreement), via the pitches' frontmatter ledgers

Nothing tracker-specific is baked in beyond one default adapter:

  * Which headings bind is passed by the caller — `--binding ID=HEADING`,
    repeatable — and the plugin sources those from the active profile, so a
    team's tracker template is data, not code.
  * How a ticket is obtained is an *adapter*: any command that prints the
    ticket-input JSON below. `--fetch-command` (or the consuming repo's
    `requirement_contract.fetch_command`) names it; the placeholders `{repo}`
    and `{id}` are substituted per argv element — the template is split with
    shlex and run WITHOUT a shell, so a placeholder value can never become
    shell syntax. Absent, the built-in GitHub adapter runs `gh api graphql`.
  * The version coordinate is an opaque string; the only operation this
    script performs on it is equality. GitHub's is the body's last-edit time.

Ticket-input JSON (what an adapter prints; `history` is optional):

  {"id": "3755", "title": "…", "url": "…", "body": "<markdown>",
   "version": "2026-09-08T05:25:01Z", "state": "OPEN",
   "labels": ["ux"], "milestone": "v2.3.1",
   "history": [{"version": "…", "body": "<markdown at that version>"}, …]}

Everything the parser recognises is plain GitHub-flavoured markdown:

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
               the non-binding context a judgement needs to spot a
               self-contradiction (a 비고 / 미해결 note) lives here
  warnings[]   tolerated but worth a look: plain bullets, prose lines, empty
               items, duplicate item text, fenced code inside a binding section
  errors[]     what made the exit code non-zero
  source       `fetch`/`drift`: tracker, repo, id, title, url, state, labels,
               milestone, version, fetched_at, read_at

`drift` adds: `recorded_version`, `current_version`, `drift` (versions
differ), `history_available` (the recorded body could be retrieved),
`binding_changed` (a binding item was added or removed — false when history
proves the change touched only non-binding text), and per binding `added[]`,
`removed[]`, `unchanged` (item texts compared as multisets).

`coverage` reads the ledger each pitch keeps in its frontmatter under the
matching `references.tickets[]` entry (PyYAML needed for this subcommand
only):

  covers:                       # what THIS pitch reflects, by binding id
    acceptance:
      - group: 적립             # a whole group (label as the ticket writes it;
      - group: 주문·결제 화면   #   null = the items before any label)
        items: [1]              # or only these in-group ordinals (1-based)
        shared: true            # claimed by another pitch too, on purpose
  delegates:                    # reflected in substance, literal owned elsewhere
    - binding: qa_checklist
      group: 이용 안내·쿠폰 표기
      items: [2]
      to: Figma
      why: 문구의 진실 소스는 시안

Accounting is per SET — every pitch file given that cites the ticket — so a
pitch never has to enumerate what its siblings own. Output: `pitches[]`
(path, recorded version, claim counts), `uncovered[]` (no pitch claims the
item), `overlaps[]` (claimed by several without `shared` on every side),
`stale[]` (a declaration naming a binding, group or ordinal the ticket does
not have — a drift symptom), `shared[]` (informational), `version_mismatch[]`
(a pitch recorded a version other than the live one; run `drift` for
detail), `covered` / `total` counts. Exit 0 when every item is claimed
exactly once (or shared by agreement) and nothing is stale; 1 otherwise;
2 on adapter or file errors.

`text` is the ONE canonical form every consumer compares: NFC-normalised,
outer whitespace stripped, inner whitespace runs collapsed to a single
space, inline markdown kept verbatim. A struck item keeps its `~~`;
`struck: true` says so.

Exit codes
  parse/fetch  0 every binding section found with ≥1 item · 1 a binding
               section is missing or empty (JSON still emitted, so the caller
               renders `errors` instead of guessing) · 2 usage or adapter error
  drift        0 no drift, or drift proven to touch no binding item · 1 a
               binding item changed, or the change could not be examined
               (no history for the recorded version) · 2 usage or adapter error

Requires python3 only (no PyYAML). The default adapter needs the `gh` CLI on
PATH, authenticated for the target repo. Line numbers are 1-based and refer
to the body as fetched (comments are blanked, not deleted, so they stay
stable).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shlex
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter
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
TICKET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
WS_RE = re.compile(r"\s+")
HEADING_QUOTES = "「」『』\"'“”‘’"
EXCERPT_LEN = 60
ADAPTER_TIMEOUT_SECONDS = 60
HISTORY_PAGE = 100
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

# The built-in GitHub adapter. `userContentEdits` holds the FULL body after each
# edit (the creation counts as the first edit), which is what lets `drift` show
# the item-level difference instead of only "the ticket moved".
GITHUB_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    issue(number: $number) {
      number title body url state createdAt lastEditedAt
      labels(first: 100) { nodes { name } }
      milestone { title }
      userContentEdits(first: %d) { totalCount nodes { editedAt diff } }
    }
  }
}
""" % HISTORY_PAGE


# --------------------------------------------------------------------------
# text normalisation — the one definition every consumer shares
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
    # still points at the same line of the body the reader sees on the tracker.
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


def binding_texts(parsed: dict[str, Any]) -> dict[str, list[str]]:
    """Binding id → canonical item texts, in document order."""
    return {
        b["id"]: [it["text"] for g in b["groups"] for it in g["items"]]
        for b in parsed["bindings"]
    }


# --------------------------------------------------------------------------
# adapters — obtaining a ticket
# --------------------------------------------------------------------------


def adapter_fail(msg: str) -> None:
    sys.stderr.write(f"error: {msg}\n")
    sys.exit(2)


def run_argv(argv: list[str], what: str) -> str:
    if shutil.which(argv[0]) is None:
        adapter_fail(f"`{argv[0]}` not found on PATH — needed to {what}")
    try:
        proc = subprocess.run(
            argv, capture_output=True, encoding="utf-8", timeout=ADAPTER_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired:
        adapter_fail(f"`{argv[0]}` did not answer within {ADAPTER_TIMEOUT_SECONDS}s while trying to {what}")
    except OSError as exc:
        adapter_fail(f"could not run `{argv[0]}`: {exc}")
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "(no output)"
        adapter_fail(f"`{argv[0]}` exited {proc.returncode} while trying to {what}: {detail}")
    return proc.stdout


def load_json_output(raw: str, what: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        adapter_fail(f"non-JSON output while trying to {what}: {exc}")


def github_fetch(repo: str, ticket_id: str) -> dict[str, Any]:
    """Built-in adapter: the issue plus its full edit history via GraphQL."""
    if not ticket_id.isdigit():
        adapter_fail(f"the GitHub adapter needs a numeric issue id, got {ticket_id!r}")
    owner, name = repo.split("/", 1)
    what = f"fetch {repo}#{ticket_id}"
    raw = run_argv(
        [
            "gh", "api", "graphql",
            "-f", f"query={GITHUB_QUERY}",
            "-F", f"owner={owner}", "-F", f"name={name}", "-F", f"number={int(ticket_id)}",
        ],
        what,
    )
    data = load_json_output(raw, what)
    issue = (((data or {}).get("data") or {}).get("repository") or {}).get("issue")
    if not isinstance(issue, dict):
        errs = (data or {}).get("errors") if isinstance(data, dict) else None
        detail = "; ".join(str(e.get("message", e)) for e in errs) if errs else "no issue in response"
        adapter_fail(f"could not {what}: {detail}")
    version = issue.get("lastEditedAt") or issue.get("createdAt")
    edits = issue.get("userContentEdits") or {}
    history = [
        {"version": n.get("editedAt"), "body": n.get("diff")}
        for n in (edits.get("nodes") or [])
        if isinstance(n, dict) and n.get("editedAt") and n.get("diff") is not None
    ]
    if history and version and not any(h["version"] == version for h in history):
        # The current version's edit record can be missing only when the edit
        # log is longer than one page; the current body still stands for it.
        history.append({"version": version, "body": issue.get("body") or ""})
    total = edits.get("totalCount")
    milestone = issue.get("milestone") or None
    return {
        "id": str(issue.get("number", ticket_id)),
        "title": issue.get("title"),
        "url": issue.get("url"),
        "body": issue.get("body") or "",
        "version": version,
        "state": issue.get("state"),
        "labels": [lb.get("name") for lb in ((issue.get("labels") or {}).get("nodes") or []) if isinstance(lb, dict)],
        "milestone": milestone.get("title") if isinstance(milestone, dict) else None,
        "history": history,
        "history_truncated": bool(isinstance(total, int) and total > HISTORY_PAGE),
    }


def command_fetch(template: str, repo: str | None, ticket_id: str) -> dict[str, Any]:
    """A consumer-supplied adapter: shlex-split template, placeholders swapped
    per argv element, run without a shell, output = ticket-input JSON."""
    try:
        parts = shlex.split(template)
    except ValueError as exc:
        adapter_fail(f"--fetch-command is not a valid command line: {exc}")
    if not parts:
        adapter_fail("--fetch-command is empty")
    argv = [p.replace("{repo}", repo or "").replace("{id}", ticket_id) for p in parts]
    what = f"fetch ticket {ticket_id} via `{parts[0]}`"
    data = load_json_output(run_argv(argv, what), what)
    if not isinstance(data, dict):
        adapter_fail(f"adapter output must be a JSON object while trying to {what}")
    return data


def normalize_ticket(data: dict[str, Any], ticket_id: str) -> dict[str, Any]:
    """Validate an adapter's output against the ticket-input contract."""
    problems: list[str] = []
    if not isinstance(data.get("body"), str):
        problems.append("`body` (string) missing")
    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        problems.append("`version` (non-empty string) missing — the drift check has nothing to compare")
    if problems:
        adapter_fail(f"adapter output for ticket {ticket_id} is incomplete: " + "; ".join(problems))
    history_in = data.get("history") or []
    history = [
        {"version": str(h["version"]), "body": h["body"]}
        for h in history_in
        if isinstance(h, dict) and h.get("version") and isinstance(h.get("body"), str)
    ]
    labels = data.get("labels") or []
    return {
        "id": str(data.get("id") or ticket_id),
        "title": data.get("title"),
        "url": data.get("url"),
        "body": data["body"],
        "version": version.strip(),
        "state": data.get("state"),
        "labels": [str(x) for x in labels] if isinstance(labels, list) else [],
        "milestone": data.get("milestone"),
        "history": history,
        "history_truncated": bool(data.get("history_truncated", False)),
    }


def obtain_ticket(args: argparse.Namespace) -> dict[str, Any]:
    if args.fetch_command:
        raw = command_fetch(args.fetch_command, args.repo, args.id)
    else:
        if not args.repo:
            adapter_fail("--repo OWNER/NAME is required for the built-in GitHub adapter")
        raw = github_fetch(args.repo, args.id)
    return normalize_ticket(raw, args.id)


def source_block(args: argparse.Namespace, ticket: dict[str, Any]) -> dict[str, Any]:
    now = _dt.datetime.now().astimezone()
    return {
        "tracker": args.tracker,
        "repo": args.repo,
        "id": ticket["id"],
        "title": ticket["title"],
        "url": ticket["url"],
        "state": ticket["state"],
        "labels": ticket["labels"],
        "milestone": ticket["milestone"],
        "version": ticket["version"],
        "fetched_at": now.isoformat(timespec="seconds"),
        "read_at": now.date().isoformat(),
    }


# --------------------------------------------------------------------------
# drift — recorded version vs. current
# --------------------------------------------------------------------------


def pick_items(binding: dict[str, Any], wanted: Counter) -> list[dict[str, Any]]:
    """The items of `binding`, in document order, whose text is in `wanted`
    (a multiset — a text listed twice is picked twice, then no more)."""
    left = Counter(wanted)
    picked: list[dict[str, Any]] = []
    for g in binding["groups"]:
        for it in g["items"]:
            if left.get(it["text"], 0) > 0:
                left[it["text"]] -= 1
                picked.append({"ordinal": it["ordinal"], "group": it["group"], "text": it["text"]})
    return picked


def compute_drift(
    ticket: dict[str, Any], recorded: str, bindings: list[tuple[str, str]]
) -> dict[str, Any]:
    current = parse_body(ticket["body"], bindings)
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "source": None,
        "recorded_version": recorded,
        "current_version": ticket["version"],
        "drift": ticket["version"] != recorded,
        "history_available": True,
        "binding_changed": False,
        "bindings": [],
        "warnings": list(current["warnings"]),
        "errors": [],
    }
    if not result["drift"]:
        result["bindings"] = [
            {"id": b["id"], "heading": b["heading"], "added": [], "removed": [],
             "unchanged": b["item_count"]}
            for b in current["bindings"]
        ]
        return result

    old_body = next((h["body"] for h in ticket["history"] if h["version"] == recorded), None)
    if old_body is None:
        result["history_available"] = False
        result["binding_changed"] = True  # unproven → treat as changed
        note = " (the edit log was longer than one page)" if ticket.get("history_truncated") else ""
        result["warnings"].append(
            f"no body is available for recorded version {recorded!r}{note}; "
            f"cannot tell which items changed — re-read the ticket"
        )
        result["bindings"] = [
            {"id": b["id"], "heading": b["heading"], "added": [], "removed": [],
             "unchanged": None}
            for b in current["bindings"]
        ]
        return result

    old = parse_body(old_body, bindings)
    old_texts = binding_texts(old)
    new_by_id = {b["id"]: b for b in current["bindings"]}
    for b in old["bindings"]:
        bid = b["id"]
        new_b = new_by_id[bid]
        old_c = Counter(old_texts[bid])
        new_c = Counter(it["text"] for g in new_b["groups"] for it in g["items"])
        removed = pick_items(b, old_c - new_c)
        added = pick_items(new_b, new_c - old_c)
        unchanged = sum((old_c & new_c).values())
        if added or removed:
            result["binding_changed"] = True
        result["bindings"].append(
            {"id": bid, "heading": b["heading"], "added": added, "removed": removed,
             "unchanged": unchanged}
        )
    return result


# --------------------------------------------------------------------------
# coverage — the set of pitches citing a ticket vs. the ticket's items
# --------------------------------------------------------------------------


def load_frontmatter_yaml(path: str) -> dict[str, Any] | None:
    """A pitch's frontmatter as a mapping, or None when absent/malformed.
    PyYAML is imported here, not at module top, so parse/fetch/drift stay
    dependency-free."""
    try:
        import yaml  # type: ignore
    except ImportError:
        adapter_fail("`coverage` needs PyYAML to read pitch frontmatter (pip install pyyaml)")
    try:
        text = open(path, "rb").read().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        adapter_fail(f"cannot read pitch {path}: {exc}")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    try:
        fm = yaml.safe_load(m.group(1))
    except Exception:  # yaml errors and date ValueErrors alike
        return None
    return fm if isinstance(fm, dict) else None


def ticket_entry_for(fm: dict[str, Any], args: argparse.Namespace) -> dict[str, Any] | None:
    refs = fm.get("references") or {}
    for entry in (refs.get("tickets") or []) if isinstance(refs, dict) else []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("id")) != args.id:
            continue
        if str(entry.get("tracker", "github")) != args.tracker:
            continue
        if args.repo and entry.get("repo") and str(entry["repo"]) != args.repo:
            continue
        return entry
    return None


def item_index(parsed: dict[str, Any]) -> dict[tuple[str, str | None, int], dict[str, Any]]:
    """(binding id, group label, in-group ordinal) → item, for every binding item."""
    index: dict[tuple[str, str | None, int], dict[str, Any]] = {}
    for b in parsed["bindings"]:
        for g in b["groups"]:
            for k, it in enumerate(g["items"], start=1):
                index[(b["id"], g["label"], k)] = {**it, "binding": b["id"], "in_group": k}
    return index


def resolve_declaration(
    index: dict[tuple[str, str | None, int], dict[str, Any]],
    binding: str, group: Any, items: Any, where: str, stale: list[str],
) -> list[tuple[str, str | None, int]]:
    """Keys a `covers`/`delegates` entry denotes; stale parts are reported, not guessed."""
    label = None if group is None else norm_text(str(group))
    keys = sorted(k for k in index if k[0] == binding and k[1] == label)
    if not keys:
        known = sorted({k[0] for k in index})
        if binding not in known:
            stale.append(f"{where}: binding {binding!r} is not one of {known}")
        else:
            groups = sorted({str(k[1]) for k in index if k[0] == binding})
            stale.append(f"{where}: group {label!r} not in {binding} — groups on the ticket: {groups}")
        return []
    if items is None:
        return keys
    if not isinstance(items, list) or not all(isinstance(i, int) and i > 0 for i in items):
        stale.append(f"{where}: items must be a list of positive in-group ordinals, got {items!r}")
        return []
    have = {k[2] for k in keys}
    out: list[tuple[str, str | None, int]] = []
    for i in items:
        if i not in have:
            stale.append(f"{where}: item {i} not in {binding} · {label!r} (the group has {len(have)})")
        else:
            out.append((binding, label, i))
    return out


def compute_coverage(
    ticket: dict[str, Any], bindings: list[tuple[str, str]], pitch_paths: list[str], args: argparse.Namespace
) -> dict[str, Any]:
    parsed = parse_body(ticket["body"], bindings)
    index = item_index(parsed)
    claims: dict[tuple[str, str | None, int], list[dict[str, Any]]] = {k: [] for k in index}
    stale: list[str] = []
    warnings: list[str] = list(parsed["warnings"])
    errors: list[str] = list(parsed["errors"])
    pitches_out: list[dict[str, Any]] = []
    mismatch: list[dict[str, Any]] = []

    for path in pitch_paths:
        fm = load_frontmatter_yaml(path)
        if fm is None:
            warnings.append(f"{path}: no readable frontmatter; skipped")
            continue
        entry = ticket_entry_for(fm, args)
        if entry is None:
            continue  # cites another ticket, or none — not part of this set
        n_cov = n_del = 0
        covers = entry.get("covers") or {}
        if not isinstance(covers, dict):
            stale.append(f"{path}: covers must be a mapping of binding id → list")
            covers = {}
        for binding, decls in covers.items():
            if not isinstance(decls, list):
                stale.append(f"{path}: covers.{binding} must be a list")
                continue
            for d in decls:
                if not isinstance(d, dict) or "group" not in d:
                    stale.append(f"{path}: covers.{binding} entry must be a mapping with `group`: {d!r}")
                    continue
                for key in resolve_declaration(index, str(binding), d.get("group"), d.get("items"), f"{path} covers.{binding}", stale):
                    claims[key].append({"pitch": path, "kind": "covers", "shared": bool(d.get("shared", False))})
                    n_cov += 1
        for d in entry.get("delegates") or []:
            if not isinstance(d, dict) or "binding" not in d or "group" not in d or not str(d.get("to") or "").strip():
                stale.append(f"{path}: delegates entry needs `binding`, `group`, `to`: {d!r}")
                continue
            for key in resolve_declaration(index, str(d["binding"]), d.get("group"), d.get("items"), f"{path} delegates", stale):
                claims[key].append({"pitch": path, "kind": "delegates", "to": str(d["to"]), "shared": bool(d.get("shared", False))})
                n_del += 1
        recorded = str(entry.get("version") or "")
        if recorded != ticket["version"]:
            mismatch.append({"pitch": path, "recorded_version": recorded, "current_version": ticket["version"]})
        pitches_out.append({"path": path, "recorded_version": recorded, "covers": n_cov, "delegates": n_del})

    def describe(key: tuple[str, str | None, int]) -> dict[str, Any]:
        it = index[key]
        return {"binding": key[0], "group": key[1], "item": key[2], "ordinal": it["ordinal"], "text": it["text"]}

    uncovered = [describe(k) for k in sorted(index, key=lambda k: index[k]["ordinal"] + (0 if k[0] == bindings[0][0] else 10_000)) if not claims[k]]
    overlaps: list[dict[str, Any]] = []
    shared: list[dict[str, Any]] = []
    for k, cs in claims.items():
        if len(cs) < 2:
            continue
        row = {**describe(k), "claimed_by": [c["pitch"] for c in cs]}
        (shared if all(c["shared"] for c in cs) else overlaps).append(row)
    total = len(index)
    if mismatch:
        warnings.append(
            f"{len(mismatch)} pitch(es) recorded a version other than the live one — run `drift` to see what moved"
        )
    return {
        "schema": SCHEMA,
        "source": None,
        "total": total,
        "covered": total - len(uncovered),
        "pitches": pitches_out,
        "uncovered": uncovered,
        "overlaps": overlaps,
        "shared": shared,
        "stale": stale,
        "version_mismatch": mismatch,
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


def emit(result: dict[str, Any], compact: bool) -> None:
    payload = json.dumps(result, ensure_ascii=False, indent=None if compact else 2) + "\n"
    sys.stdout.buffer.write(payload.encode("utf-8"))
    sys.stdout.flush()


def validate_ticket_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.repo is not None and not REPO_RE.match(args.repo):
        parser.error(f"--repo must be OWNER/NAME, got {args.repo!r}")
    if not TICKET_ID_RE.match(args.id):
        parser.error(f"--id may contain only letters, digits, `.`, `_`, `-`; got {args.id!r}")


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

    def add_ticket(p: argparse.ArgumentParser) -> None:
        p.add_argument("--id", required=True, metavar="TICKET_ID", help="ticket identifier (issue number on GitHub)")
        p.add_argument("--repo", metavar="OWNER/NAME", help="repository the ticket lives in (required for the GitHub adapter)")
        p.add_argument("--tracker", default="github", metavar="NAME", help="label recorded in `source.tracker` (default: github)")
        p.add_argument(
            "--fetch-command", metavar="TEMPLATE",
            help="adapter command printing ticket-input JSON; `{repo}` and `{id}` are substituted per argv element, no shell",
        )

    p_parse = sub.add_parser("parse", help="parse a ticket body from a file (`-` = stdin)")
    p_parse.add_argument("body", help="path to the body, or `-` for stdin")
    add_common(p_parse)

    p_fetch = sub.add_parser("fetch", help="obtain the ticket through an adapter, then parse")
    add_ticket(p_fetch)
    add_common(p_fetch)

    p_drift = sub.add_parser("drift", help="compare the live ticket with a recorded version coordinate")
    add_ticket(p_drift)
    p_drift.add_argument("--version", required=True, metavar="RECORDED", help="the version coordinate the pitch recorded")
    add_common(p_drift)

    p_cov = sub.add_parser("coverage", help="reconcile the pitches citing the ticket against its binding items")
    add_ticket(p_cov)
    p_cov.add_argument("pitches", nargs="+", metavar="PITCH.md", help="pitch files to consider (those citing the ticket form the set)")
    add_common(p_cov)

    args = parser.parse_args(argv)
    bindings = parse_binding_args(parser, args.binding)

    if args.command == "parse":
        try:
            body = read_body(args.body)
        except (OSError, UnicodeDecodeError) as exc:
            parser.error(f"cannot read body: {exc}")
        result = parse_body(body, bindings)
        emit(result, args.compact)
        return 1 if result["errors"] else 0

    validate_ticket_args(parser, args)
    ticket = obtain_ticket(args)

    if args.command == "fetch":
        result = parse_body(ticket["body"], bindings)
        result["source"] = source_block(args, ticket)
        emit(result, args.compact)
        return 1 if result["errors"] else 0

    if args.command == "coverage":
        result = compute_coverage(ticket, bindings, args.pitches, args)
        result["source"] = source_block(args, ticket)
        emit(result, args.compact)
        return 1 if (result["uncovered"] or result["overlaps"] or result["stale"] or result["errors"]) else 0

    recorded = args.version.strip()
    if not recorded:
        parser.error("--version must not be empty")
    result = compute_drift(ticket, recorded, bindings)
    result["source"] = source_block(args, ticket)
    emit(result, args.compact)
    return 1 if result["binding_changed"] else 0


if __name__ == "__main__":
    sys.exit(main())
