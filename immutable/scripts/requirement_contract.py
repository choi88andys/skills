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
  lint      judge the WORDING of every binding item — or of drafted
            correction sentences — against the profile's wording rules: a
            completion condition nobody can judge (「필요 시」), one deferring to
            the very pitch that must follow it, an unpinned design made the
            oracle. Deterministic, no LLM; the skill and CI run the same rules

Nothing tracker-specific is baked in beyond one default adapter:

  * Which headings bind is passed by the caller — `--binding ID=HEADING`,
    repeatable — and the plugin sources those from the active profile, so a
    team's tracker template is data, not code.
  * Whether a declared section MUST be there is data too — `--optional-binding
    ID`, repeatable, naming an id already declared with `--binding`; the
    plugin sources it from `ticket_sections[].required` in the same profile.
    A required section that the ticket does not supply is an error (exit 1);
    an optional one is a warning, `found: false`, `item_count: 0`, and a row
    in `absent[]`. Requiredness is per section and per team because a ticket
    whose template was never filled in is the consuming organisation's
    problem, not a property of the parser: refusing is right at authoring
    time, where the author is told why and fills the ticket, and wrong in a
    reconciliation run, where it turns the build red through no fault of the
    pitch under review.
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

Output contract (`schema: 2`) — always JSON on stdout, even on failure:

  bindings[]   one per `--binding`, in caller order: `id`, `heading`,
               `required` (false when `--optional-binding` named it), `found`,
               the matched heading's `matched_heading` / `level` / `line`,
               `groups[]` of `items[]`, and `item_count`
  absent[]     every declared binding the ticket supplies no items for —
               `id`, `heading`, `required`, `why`. Emitted by every
               subcommand, `coverage` and `drift` included: a section that
               merely vanished from a reconciliation report is how a check
               goes quietly fail-open
  items        `ordinal` (1-based within the section, across groups — a sort
               key), `in_group` (1-based within its group — the number the
               ledger's `items` and every `<group> <n>` reference use), `group`,
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
        items: [1]              # or only these in-group ordinals (the parser's in_group)
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
detail), `covered` / `total` counts. An item row names the item by
`binding`, `group`, `in_group` — the ledger's coordinate — plus `ordinal` and
`text`. Exit 0 when every item is claimed
exactly once (or shared by agreement) and nothing is stale; 1 otherwise;
2 on adapter or file errors.

`lint` reads its rules from `--profile` — `requirement_contract.wording_rules[]`
and `wording_strip[]` (profile_schema 5), plus the legacy
`disagreement.deferral_patterns[]`, which apply to corrections only (see
`compile_wording`). A profile without `wording_rules` falls back to the bundled
default for its `locale`, named in `rules.fallback` and a warning. The ticket
comes from the same flags as `fetch`, or `--from-json` (the JSON a prior
`parse`/`fetch` printed — what the author actually read), or the input is
`--correction SENTENCE` (repeatable) instead of a ticket. Output: `rules`
(profile, fallback, rule counts per target), `hits[]`, `counts`, plus
`source`, `absent`, `warnings`, `errors` as `fetch` prints them. A hit carries
the item's ledger coordinate — `binding`, `group`, `in_group` — with
`ordinal`, `line`, `text`, and the rule's `rule` (id), `source`
(`wording_rules` | `deferral_patterns`), `category`, `severity`
(`block` | `warn`), `match`, `hint`; `target` says `ticket_item` or
`correction` (a correction hit has no coordinate). Struck items are withdrawn
requirements and are not linted (`counts.struck_skipped`).

`text` is the ONE canonical form every consumer compares: NFC-normalised,
outer whitespace stripped, inner whitespace runs collapsed to a single
space, inline markdown kept verbatim. A struck item keeps its `~~`;
`struck: true` says so.

Exit codes
  parse/fetch  0 every REQUIRED binding section found with ≥1 item · 1 a
               required binding section is missing or empty (JSON still
               emitted, so the caller renders `errors` instead of guessing) ·
               2 usage or adapter error
  drift        0 no drift, or drift proven to touch no binding item · 1 a
               binding item changed, or the change could not be examined
               (no history for the recorded version) · 2 usage or adapter error
  lint         0 no `block` hit · 1 a `block` hit, or a required binding
               section missing (as `fetch`) · 2 usage, adapter or profile
               error — a rule the profile states but the script cannot
               compile is an error, never a silently weaker lint

Requires python3; `coverage` and `lint` also need PyYAML (they read YAML —
pitch frontmatter, the profile). The default adapter needs the `gh` CLI on
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
from pathlib import Path
from typing import Any

SCHEMA = 2

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
WORDING_TARGETS = ("ticket_item", "correction")
WORDING_SEVERITIES = ("block", "warn")
BUNDLED_PROFILES = Path(__file__).resolve().parent.parent / "examples" / "_profiles"

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
                "in_group": len(current_group["items"]) + 1,
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


def parse_body(body: str, bindings: list[tuple[str, str, bool]]) -> dict[str, Any]:
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
    for bid, heading, required in bindings:
        label = f"{bid} ({heading})"
        matches = by_key.get(norm_heading(heading), [])
        if not matches:
            present = ", ".join(f"{'#' * h['level']} {h['title']}" for h in heads) or "(no headings at all)"
            if required:
                errors.append(f"binding section not found: {label} — headings present: {present}")
            else:
                warnings.append(
                    f"optional binding section absent: {label} — headings present: {present}"
                )
            out_bindings.append(
                {
                    "id": bid,
                    "heading": heading,
                    "required": required,
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
            where = f"{label} (line {head['line'] + 1})"
            if required:
                errors.append(f"binding section has no list items: {where}")
            else:
                warnings.append(f"optional binding section has no list items: {where}")
        out_bindings.append(
            {
                "id": bid,
                "heading": heading,
                "required": required,
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
        "absent": absent_bindings(out_bindings),
        "sections": sections,
        "warnings": warnings,
        "errors": errors,
    }


def absent_bindings(out_bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Declared bindings the ticket supplies no items for, required or not.

    Every subcommand reports this. An optional section that is simply missing
    from a reconciliation report reads as "nothing to reconcile there", which
    is indistinguishable from "reconciled clean" — the shape that let a
    malformed ticket record pass silently before v0.12.
    """
    return [
        {
            "id": b["id"],
            "heading": b["heading"],
            "required": b["required"],
            "why": "section not found" if not b["found"] else "section has no list items",
        }
        for b in out_bindings
        if not b["found"] or not b["item_count"]
    ]


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
                picked.append({"ordinal": it["ordinal"], "in_group": it["in_group"], "group": it["group"], "text": it["text"]})
    return picked


def compute_drift(
    ticket: dict[str, Any], recorded: str, bindings: list[tuple[str, str, bool]]
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
        "absent": current["absent"],
        "warnings": list(current["warnings"]),
        "errors": [],
    }
    if not result["drift"]:
        result["bindings"] = [
            {"id": b["id"], "heading": b["heading"], "required": b["required"],
             "added": [], "removed": [], "unchanged": b["item_count"]}
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
            {"id": b["id"], "heading": b["heading"], "required": b["required"],
             "added": [], "removed": [], "unchanged": None}
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
            {"id": bid, "heading": b["heading"], "required": b["required"],
             "added": added, "removed": removed, "unchanged": unchanged}
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
    """(binding id, group label, in_group) → item — the ledger's coordinate, as the parser prints it."""
    index: dict[tuple[str, str | None, int], dict[str, Any]] = {}
    for b in parsed["bindings"]:
        for g in b["groups"]:
            for it in g["items"]:
                index[(b["id"], g["label"], it["in_group"])] = {**it, "binding": b["id"]}
    return index


def resolve_declaration(
    index: dict[tuple[str, str | None, int], dict[str, Any]],
    binding: str, group: Any, items: Any, where: str, stale: list[str],
    absent: dict[str, str] | None = None,
) -> list[tuple[str, str | None, int]]:
    """Keys a `covers`/`delegates` entry denotes; stale parts are reported, not guessed.

    `absent` maps a declared binding id the ticket supplies no items for to the
    reason — a claim against one of those is a drift symptom worth naming as
    such, not "that binding does not exist".
    """
    label = None if group is None else norm_text(str(group))
    keys = sorted(k for k in index if k[0] == binding and k[1] == label)
    if not keys:
        known = sorted({k[0] for k in index})
        if binding in (absent or {}):
            stale.append(
                f"{where}: binding {binding!r} is declared but the ticket supplies no items "
                f"for it ({(absent or {})[binding]})"
            )
        elif binding not in known:
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
    ticket: dict[str, Any], bindings: list[tuple[str, str, bool]], pitch_paths: list[str], args: argparse.Namespace
) -> dict[str, Any]:
    parsed = parse_body(ticket["body"], bindings)
    index = item_index(parsed)
    absent = {row["id"]: row["why"] for row in parsed["absent"]}
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
                for key in resolve_declaration(index, str(binding), d.get("group"), d.get("items"), f"{path} covers.{binding}", stale, absent):
                    claims[key].append({"pitch": path, "kind": "covers", "shared": bool(d.get("shared", False))})
                    n_cov += 1
        for d in entry.get("delegates") or []:
            if not isinstance(d, dict) or "binding" not in d or "group" not in d or not str(d.get("to") or "").strip():
                stale.append(f"{path}: delegates entry needs `binding`, `group`, `to`: {d!r}")
                continue
            for key in resolve_declaration(index, str(d["binding"]), d.get("group"), d.get("items"), f"{path} delegates", stale, absent):
                claims[key].append({"pitch": path, "kind": "delegates", "to": str(d["to"]), "shared": bool(d.get("shared", False))})
                n_del += 1
        recorded = str(entry.get("version") or "")
        if recorded != ticket["version"]:
            mismatch.append({"pitch": path, "recorded_version": recorded, "current_version": ticket["version"]})
        pitches_out.append({"path": path, "recorded_version": recorded, "covers": n_cov, "delegates": n_del})

    def describe(key: tuple[str, str | None, int]) -> dict[str, Any]:
        it = index[key]
        return {"binding": key[0], "group": key[1], "in_group": key[2], "ordinal": it["ordinal"], "text": it["text"]}

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
    for row in parsed["absent"]:
        kind = "required" if row["required"] else "optional"
        warnings.append(
            f"reconciled without {kind} binding {row['id']} ({row['heading']}): {row['why']} — "
            f"nothing on the ticket to claim, so its coverage is neither proven nor denied"
        )
    return {
        "schema": SCHEMA,
        "source": None,
        "total": total,
        "covered": total - len(uncovered),
        "absent": parsed["absent"],
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
# lint — binding wording judged against the profile's wording rules
# --------------------------------------------------------------------------


def compile_wording(contract: Any) -> dict[str, Any]:
    """A profile's `requirement_contract` block → its compiled wording rules.

    The ONE reader of the rules. `lint` (ticket items, and drafted corrections
    via `--correction`) and `validate_docs.py` (a pitch's correction bullets)
    both call it, so the authoring skill, a CI lint and the merge gate cannot
    disagree about what a rule says.

    Two sources, in this order:

      * `wording_rules[]` — `{id, category, severity, applies_to, scope?,
        regex, unless?, hint}`. Matched case-insensitively against the text
        after every `wording_strip[]` pattern has blanked the quoted UI
        literals: a 「처리 중…」 label is the screen's copy, not the
        requirement's wording. `unless` is matched against the RAW text,
        because what it looks for — a pinned 「X 전달」 delivery name — is
        itself a quoted literal. `scope` (binding ids) limits a rule to those
        sections; a scoped rule never judges a correction, which has none.
      * `disagreement.deferral_patterns[]` (v0.11–v0.12) — read as rules that
        apply to corrections only: severity `block`, no category, matched
        case-sensitively on the raw text, exactly as v0.12 matched them, so a
        profile that predates `wording_rules` passes and fails the same pitches.

    Returns `{"rules", "strip", "problems"}`. A problem names a rule the
    caller must not trust (invalid regex, unknown category, severity or
    target, duplicate id); that rule is left out of `rules`.
    """
    contract = contract if isinstance(contract, dict) else {}
    problems: list[str] = []
    categories = {
        str(c["id"]) for c in contract.get("categories") or [] if isinstance(c, dict) and c.get("id")
    }

    strip: list[re.Pattern[str]] = []
    for i, pat in enumerate(contract.get("wording_strip") or []):
        try:
            strip.append(re.compile(str(pat)))
        except re.error as exc:
            problems.append(f"wording_strip[{i}] is an invalid regex ({exc})")

    def compile_opt(where: str, field: str, value: Any, flags: int) -> re.Pattern[str] | None:
        try:
            return re.compile(str(value), flags)
        except re.error as exc:
            problems.append(f"{where}.{field} is an invalid regex ({exc})")
            return None

    rules: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, entry in enumerate(contract.get("wording_rules") or []):
        if not isinstance(entry, dict):
            problems.append(f"wording_rules[{i}] must be a mapping")
            continue
        rid = str(entry.get("id") or "")
        where = f"wording_rules[{rid or i}]"
        if not BINDING_ID_RE.match(rid):
            problems.append(f"{where}: id must match [a-z][a-z0-9_]*")
            continue
        if rid in seen:
            problems.append(f"{where}: id given twice")
            continue
        seen.add(rid)
        category = str(entry.get("category") or "")
        if category not in categories:
            problems.append(f"{where}: category {category!r} is not one of requirement_contract.categories {sorted(categories)}")
            continue
        severity = entry.get("severity")
        if severity not in WORDING_SEVERITIES:
            problems.append(f"{where}: severity must be one of {list(WORDING_SEVERITIES)}, got {severity!r}")
            continue
        applies = entry.get("applies_to")
        if not isinstance(applies, list) or not applies or any(a not in WORDING_TARGETS for a in applies):
            problems.append(f"{where}: applies_to must be a non-empty list drawn from {list(WORDING_TARGETS)}, got {applies!r}")
            continue
        scope = entry.get("scope")
        if scope is not None and (not isinstance(scope, list) or not all(isinstance(s, str) and s for s in scope)):
            problems.append(f"{where}: scope must be a list of binding ids, got {scope!r}")
            continue
        if not entry.get("regex"):
            problems.append(f"{where}: regex missing")
            continue
        regex = compile_opt(where, "regex", entry["regex"], re.IGNORECASE)
        unless = compile_opt(where, "unless", entry["unless"], re.IGNORECASE) if entry.get("unless") else None
        if regex is None or (entry.get("unless") and unless is None):
            continue
        rules.append({
            "id": rid, "source": "wording_rules", "category": category, "severity": severity,
            "applies_to": tuple(applies), "scope": tuple(scope) if scope else None,
            "regex": regex, "unless": unless, "hint": str(entry.get("hint") or ""), "strip": True,
        })

    legacy = (contract.get("disagreement") or {}).get("deferral_patterns") or []
    for entry in legacy if isinstance(legacy, list) else []:
        if not isinstance(entry, dict) or not entry.get("regex"):
            continue
        pid = str(entry.get("id") or "deferral")
        regex = compile_opt(f"disagreement.deferral_patterns[{pid}]", "regex", entry["regex"], 0)
        if regex is None:
            continue
        rules.append({
            "id": pid, "source": "deferral_patterns", "category": None, "severity": "block",
            "applies_to": ("correction",), "scope": None,
            "regex": regex, "unless": None, "hint": str(entry.get("hint") or ""), "strip": False,
        })
    return {"rules": rules, "strip": strip, "problems": problems}


def strip_literals(strip: list[re.Pattern[str]], text: str) -> str:
    for pat in strip:
        text = pat.sub(" ", text)
    return norm_text(text)


def wording_hits(compiled: dict[str, Any], text: str, target: str, binding: str | None = None) -> list[dict[str, Any]]:
    """Every rule of `compiled` that applies to `target` and matches `text`,
    in rule order. `binding` is the item's section id (None for a correction)."""
    hits: list[dict[str, Any]] = []
    stripped: str | None = None
    for rule in compiled["rules"]:
        if target not in rule["applies_to"]:
            continue
        if rule["scope"] is not None and binding not in rule["scope"]:
            continue
        if rule["strip"]:
            if stripped is None:
                stripped = strip_literals(compiled["strip"], text)
            subject = stripped
        else:
            subject = text
        m = rule["regex"].search(subject)
        if not m or (rule["unless"] is not None and rule["unless"].search(text)):
            continue
        hits.append({
            "rule": rule["id"], "source": rule["source"], "category": rule["category"],
            "severity": rule["severity"], "match": m.group(0), "hint": rule["hint"],
        })
    return hits


def load_yaml_file(path: Path | str, what: str) -> Any:
    try:
        import yaml  # type: ignore
    except ImportError:
        adapter_fail(f"`lint` needs PyYAML to read the {what} (pip install pyyaml)")
    try:
        return yaml.safe_load(open(path, "rb").read().decode("utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        adapter_fail(f"cannot read the {what} {path}: {exc}")
    except Exception as exc:  # yaml errors and date ValueErrors alike
        adapter_fail(f"the {what} {path} is not valid YAML: {exc}")


def lint_rules(profile_path: str) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Compiled rules for `--profile`, plus the `rules` block and warnings.

    A profile written before `wording_rules` existed lints with the bundled
    default for its `locale` — the same fallback `/immutable:prd` applies to
    any field a team profile lacks — and says so; it never lints with nothing.
    An explicit `wording_rules: []` is the team's choice and is honoured,
    with a warning that no ticket item is checked.
    """
    profile = load_yaml_file(profile_path, "profile")
    if not isinstance(profile, dict):
        adapter_fail(f"the profile {profile_path} is not a mapping")
    contract = profile.get("requirement_contract")
    contract = dict(contract) if isinstance(contract, dict) else {}
    warnings: list[str] = []
    fallback: str | None = None
    if "wording_rules" not in contract:
        locale = str(profile.get("locale") or "ko")
        bundled_path = BUNDLED_PROFILES / f"default-{locale}.yml"
        if not bundled_path.is_file():
            adapter_fail(
                f"the profile {profile_path} has no requirement_contract.wording_rules and there is "
                f"no bundled default-{locale}.yml to fall back to"
            )
        bundled = load_yaml_file(bundled_path, "bundled profile")
        bc = (bundled or {}).get("requirement_contract") or {}
        contract["wording_rules"] = bc.get("wording_rules") or []
        if "wording_strip" not in contract:
            contract["wording_strip"] = bc.get("wording_strip") or []
        known = {c.get("id") for c in contract.get("categories") or [] if isinstance(c, dict)}
        contract["categories"] = list(contract.get("categories") or []) + [
            c for c in bc.get("categories") or [] if isinstance(c, dict) and c.get("id") not in known
        ]
        fallback = str(bundled_path)
        warnings.append(
            f"the profile has no requirement_contract.wording_rules — linting with the bundled "
            f"default-{locale}.yml rules; run /immutable:migrate to adopt them (profile_schema 5)"
        )
    compiled = compile_wording(contract)
    if compiled["problems"]:
        adapter_fail("the profile's wording rules cannot be trusted: " + "; ".join(compiled["problems"]))
    per_target = {t: sum(t in r["applies_to"] for r in compiled["rules"]) for t in WORDING_TARGETS}
    if not per_target["ticket_item"]:
        warnings.append("no wording rule applies to ticket_item — binding items are not checked")
    meta = {"profile": profile_path, "fallback": fallback, **per_target}
    return compiled, meta, warnings


def load_parsed_json(path: str) -> dict[str, Any]:
    try:
        data = json.loads(read_body(path))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        adapter_fail(f"cannot read --from-json {path}: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("bindings"), list):
        adapter_fail(f"--from-json {path} is not the JSON `parse` or `fetch` prints (no `bindings`)")
    if data.get("schema") != SCHEMA:
        adapter_fail(f"--from-json {path} has schema {data.get('schema')!r}; this script reads schema {SCHEMA}")
    return data


def compute_lint(compiled: dict[str, Any], parsed: dict[str, Any] | None, corrections: list[str]) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    warnings: list[str] = []
    items = struck = 0
    blocked: set[tuple[str, int]] = set()

    def add(h: dict[str, Any], key: tuple[str, int], coord: dict[str, Any]) -> None:
        hits.append({**coord, **h})
        if h["severity"] == "block":
            blocked.add(key)

    if parsed is not None:
        declared = {b["id"] for b in parsed["bindings"]}
        for rule in compiled["rules"]:
            unknown = sorted(set(rule["scope"] or ()) - declared)
            if unknown and "ticket_item" in rule["applies_to"]:
                warnings.append(
                    f"wording rule {rule['id']} is scoped to {unknown}, which this run does not declare "
                    f"as bindings {sorted(declared)} — it never fires there"
                )
        for b in parsed["bindings"]:
            for g in b["groups"]:
                for it in g["items"]:
                    if it.get("struck"):
                        struck += 1
                        continue
                    items += 1
                    coord = {
                        "target": "ticket_item", "binding": b["id"], "heading": b["heading"],
                        "group": g["label"], "in_group": it["in_group"], "ordinal": it["ordinal"],
                        "line": it["line"], "text": it["text"],
                    }
                    for h in wording_hits(compiled, it["text"], "ticket_item", b["id"]):
                        add(h, (b["id"], it["ordinal"]), coord)
    for i, sentence in enumerate(corrections, 1):
        items += 1
        text = norm_text(sentence)
        coord = {
            "target": "correction", "binding": None, "heading": None, "group": None,
            "in_group": None, "ordinal": None, "line": None, "text": text,
        }
        for h in wording_hits(compiled, text, "correction"):
            add(h, ("", i), coord)
    return {
        "hits": hits,
        "counts": {
            "items": items,
            "struck_skipped": struck,
            "items_with_block": len(blocked),
            "block": sum(h["severity"] == "block" for h in hits),
            "warn": sum(h["severity"] == "warn" for h in hits),
        },
        "warnings": warnings,
    }


def run_lint(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    # The profile first: a rule set that cannot be trusted stops the run before
    # anything is fetched.
    compiled, meta, rule_warnings = lint_rules(args.profile)
    parsed: dict[str, Any] | None = None
    if args.id is not None:
        bindings = parse_binding_args(parser, args.binding, args.optional_binding)
        validate_ticket_args(parser, args)
        ticket = obtain_ticket(args)
        parsed = parse_body(ticket["body"], bindings)
        parsed["source"] = source_block(args, ticket)
    else:
        if args.binding or args.optional_binding or args.repo or args.fetch_command:
            parser.error(
                "--binding / --optional-binding / --repo / --fetch-command go with --id; "
                "--from-json carries its own bindings and --correction has none"
            )
        if args.from_json:
            parsed = load_parsed_json(args.from_json)
    lint = compute_lint(compiled, parsed, args.correction or [])
    result = {
        "schema": SCHEMA,
        "source": parsed.get("source") if parsed else None,
        "rules": meta,
        "hits": lint["hits"],
        "counts": lint["counts"],
        "absent": parsed.get("absent", []) if parsed else [],
        "warnings": rule_warnings + lint["warnings"] + (list(parsed.get("warnings", [])) if parsed else []),
        "errors": list(parsed.get("errors", [])) if parsed else [],
    }
    emit(result, args.compact)
    return 1 if (result["counts"]["block"] or result["errors"]) else 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_binding_args(
    parser: argparse.ArgumentParser, raw: list[str] | None, optional_raw: list[str] | None = None
) -> list[tuple[str, str, bool]]:
    """`--binding ID=HEADING` in caller order, each tagged required or not.

    Optionality is named by id (`--optional-binding ID`) rather than by a
    second ID=HEADING flag on purpose: two append-lists cannot preserve the
    caller's interleaved order, and that order is the output's contract.
    """
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
    optional: set[str] = set()
    for spec in optional_raw or []:
        bid = spec.strip()
        if bid not in seen:
            parser.error(
                f"--optional-binding names {bid!r}, which is not one of the declared "
                f"--binding ids {sorted(seen)}"
            )
        if bid in optional:
            parser.error(f"--optional-binding id given twice: {bid!r}")
        optional.add(bid)
    return [(bid, heading, bid not in optional) for bid, heading in out]


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
        p.add_argument(
            "--optional-binding", action="append", metavar="ID", dest="optional_binding",
            help="a --binding id the ticket need not supply: absent or empty is a warning and an "
                 "`absent[]` row, never an error (repeatable; the plugin passes these from the "
                 "profile's ticket_sections[].required)",
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

    p_lint = sub.add_parser("lint", help="judge the binding items' wording (or drafted corrections) against the profile's wording rules")
    p_lint.add_argument(
        "--profile", required=True, metavar="PROFILE.yml",
        help="the active profile (the team's, or the bundled default); its requirement_contract block holds the rules",
    )
    src = p_lint.add_mutually_exclusive_group(required=True)
    src.add_argument("--id", metavar="TICKET_ID", help="fetch this ticket, as `fetch` does, and lint its binding items")
    src.add_argument(
        "--from-json", metavar="FETCH.json", dest="from_json",
        help="lint the JSON a prior `parse`/`fetch` printed — exactly what the author read, no second fetch",
    )
    src.add_argument(
        "--correction", action="append", metavar="SENTENCE",
        help="lint a drafted correction sentence instead of a ticket (repeatable)",
    )
    p_lint.add_argument("--repo", metavar="OWNER/NAME", help="with --id: repository the ticket lives in")
    p_lint.add_argument("--tracker", default="github", metavar="NAME", help="with --id: label recorded in `source.tracker`")
    p_lint.add_argument("--fetch-command", metavar="TEMPLATE", help="with --id: adapter command, as for `fetch`")
    add_common(p_lint)

    args = parser.parse_args(argv)
    if args.command == "lint":
        return run_lint(parser, args)
    bindings = parse_binding_args(parser, args.binding, args.optional_binding)

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
