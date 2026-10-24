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
  gate      the spec repo's merge gate: for every ticket an ACTIVE pitch
            cites, every `block` lint hit must be contested by a disagreement
            entry in a citing pitch or acknowledged in the repo's ledger
  lint      judge the WORDING of every binding item — or of drafted
            correction sentences — against the profile's wording rules: a
            completion condition nobody can judge (「필요 시」), one deferring to
            the very pitch that must follow it, a design made the oracle
            (pinned or not, on tickets created since v0.16's `design_oracle`).
            Deterministic, no LLM; the skill and CI run the same rules

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

Ticket-input JSON (what an adapter prints; `history` and `created_at` are
optional):

  {"id": "3755", "title": "…", "url": "…", "body": "<markdown>",
   "version": "2026-09-08T05:25:01Z", "state": "OPEN",
   "labels": ["ux"], "milestone": "v2.3.1",
   "created_at": "2026-09-01T02:10:00Z",
   "history": [{"version": "…", "body": "<markdown at that version>"}, …]}

`created_at` (v0.16+) is when the ticket was created — an ISO 8601 timestamp
with an offset or `Z`, or a bare `YYYY-MM-DD`. A wording rule with `since`
judges only tickets created on or after that day; an adapter that cannot say
leaves the field out, and then every such rule applies (fail-closed) with a
warning naming the ticket.

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
               milestone, version, created_at (null when the adapter gave
               none), fetched_at, read_at

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
`parse`/`fetch` printed — what the author actually read), or `--from-body
FILE` (v0.16+: a local markdown body — a draft about to be filed, or the
ticket template — with `--binding` flags and no tracker), or the input is
`--correction SENTENCE` (repeatable) instead of a ticket. A rule's `since`
is compared with the ticket's creation day in the profile's
`since_utc_offset`: from `source.created_at` for `--id` / `--from-json`, from
`--created-at` for `--correction` / `--from-body` — a body defaults to today,
a correction without it applies every rule and warns. Output: `rules`
(profile, fallback, rule counts per target, `since` per gated rule,
`since_utc_offset`), `ticket_created` (the day the gating used, or null),
`hits[]`, `counts` (with `since_withheld`), `since_skipped[]` (every rule
`since` withheld — `rule`, `since`, `ticket_created`, `withheld_hits`), plus
`source`, `absent`, `warnings`, `errors` as `fetch` prints them. A hit carries
the item's ledger coordinate — `binding`, `group`, `in_group` — with
`ordinal`, `line`, `text`, and the rule's `rule` (id), `source`
(`wording_rules` | `deferral_patterns`), `category`, `severity`
(`block` | `warn`), `match`, `hint`; `target` says `ticket_item` or
`correction` (a correction hit has no coordinate). Struck items are withdrawn
requirements and are not linted (`counts.struck_skipped`).

`gate` (v0.15+) takes the pitch files (deprecated ones are skipped), the
profile, `--ledger` and the binding flags; it lints every ticket the active
pitches cite and subtracts (1) hits whose item a citing pitch contests in its
disagreement section — the `### <tracker> <repo>#<id> · <heading> · [<group>
]<n>` header — and (2) hits the ledger acknowledges by exact coordinate and
rule. A `delegates` declaration resolves nothing: it says who owns a literal,
not that a defective item may bind. Each ticket is judged by the rules in
force on its creation day (`since`, as `lint`). Output: `verdict`, `tickets[]`
(per-ticket counts, `created`, `since_skipped`), `since_skipped[]` (every
withheld rule per ticket, with its would-be hits), `remaining[]`, `stale[]` (ledger entries whose hit is gone — the
ticket was edited, the rule changed, or no active pitch cites the ticket any
more, so an exemption cannot outlive its cause), `resolved[]`,
`unmatched_disagreements[]`, `ledger.problems[]`. The ledger format is
`ledger_entries`'s docstring.

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
  gate         off: 0, nothing fetched · warn: 0 always (stderr says what would
               fail) · on: 0 nothing unresolved · 1 a remaining hit, a stale or
               malformed acknowledgement, or a cited ticket missing a required
               section · 2 a cited ticket could not be fetched, or a usage or
               profile error
  lint         0 no `block` hit · 1 a `block` hit, or a required binding
               section missing (as `fetch`) · 2 usage, adapter or profile
               error — a rule the profile states but the script cannot
               compile is an error, never a silently weaker lint

Requires python3; `coverage`, `lint` and `gate` also need PyYAML (they read YAML —
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
# Every key a `wording_rules[]` entry may carry. Anything else is a problem:
# an engine that ignored an unknown key would read a newer rule's `since` as
# nothing and apply that rule to every ticket, retroactively and silently.
WORDING_RULE_KEYS = ("id", "category", "severity", "applies_to", "scope", "regex", "unless", "hint", "since")
UTC_OFFSET_RE = re.compile(r"^([+-])(\d{2}):(\d{2})$")
DEFAULT_SINCE_UTC_OFFSET = "+00:00"
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


class ContractError(Exception):
    """A failure `main` reports as `error: <msg>` on stderr with exit 2.

    Raised rather than exiting on the spot so `gate`, which fetches many
    tickets, can record one ticket's adapter failure and carry on — the other
    subcommands still end at the first one.
    """


def adapter_fail(msg: str) -> None:
    raise ContractError(msg)


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
        "created_at": issue.get("createdAt"),
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
    created = data.get("created_at")
    return {
        "id": str(data.get("id") or ticket_id),
        "title": data.get("title"),
        "url": data.get("url"),
        "body": data["body"],
        "version": version.strip(),
        # Optional in the contract: an adapter that cannot say when the ticket
        # was created leaves it out, and every since-gated rule then applies.
        "created_at": created.strip() if isinstance(created, str) and created.strip() else None,
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
        "created_at": ticket.get("created_at"),
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
        regex, unless?, hint, since?}`. Matched case-insensitively against the text
        after every `wording_strip[]` pattern has blanked the quoted UI
        literals: a 「처리 중…」 label is the screen's copy, not the
        requirement's wording. `unless` is matched against the RAW text,
        because what it looks for — a pinned 「X 전달」 delivery name — is
        itself a quoted literal. `scope` (binding ids) limits a rule to those
        sections; a scoped rule never judges a correction, which has none.
        `since` (v0.16+, a date) makes a rule prospective: it judges only
        tickets created on or after that date, read in the contract's
        `since_utc_offset` (`rules_in_force`). Any other key is a problem —
        an engine that skipped unknown keys would read `since` as nothing.
      * `disagreement.deferral_patterns[]` (v0.11–v0.12) — read as rules that
        apply to corrections only: severity `block`, no category, matched
        case-sensitively on the raw text, exactly as v0.12 matched them, so a
        profile that predates `wording_rules` passes and fails the same pitches.

    Returns `{"rules", "strip", "utc_offset", "problems"}`. A problem names a
    rule the caller must not trust (unknown key, invalid regex, unknown
    category, severity or target, duplicate id, a `since` that is not a date);
    that rule is left out of `rules`. A malformed `since_utc_offset` is a
    problem too, and the default (UTC) stands in for it.
    """
    contract = contract if isinstance(contract, dict) else {}
    problems: list[str] = []
    categories = {
        str(c["id"]) for c in contract.get("categories") or [] if isinstance(c, dict) and c.get("id")
    }
    raw_offset = contract.get("since_utc_offset")
    raw_offset = DEFAULT_SINCE_UTC_OFFSET if raw_offset is None else raw_offset
    utc_offset = parse_utc_offset(raw_offset)
    if utc_offset is None:
        problems.append(f"since_utc_offset must be ±HH:MM, got {raw_offset!r}")
        utc_offset = parse_utc_offset(DEFAULT_SINCE_UTC_OFFSET)

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
        unknown = sorted(str(k) for k in set(entry) - set(WORDING_RULE_KEYS))
        if unknown:
            problems.append(f"{where}: unknown key(s) {unknown} — allowed: {list(WORDING_RULE_KEYS)}")
            continue
        since: _dt.date | None = None
        if entry.get("since") is not None:
            since = parse_date(entry["since"])
            if since is None:
                problems.append(f"{where}: since must be a date (YYYY-MM-DD), got {entry['since']!r}")
                continue
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
            "since": since,
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
            "since": None,
        })
    return {"rules": rules, "strip": strip, "utc_offset": utc_offset, "problems": problems}


def parse_utc_offset(value: Any) -> _dt.timezone | None:
    """`±HH:MM` → a fixed-offset timezone, else None."""
    m = UTC_OFFSET_RE.match(str(value).strip()) if isinstance(value, str) else None
    if not m or int(m.group(2)) > 23 or int(m.group(3)) > 59:
        return None
    delta = _dt.timedelta(hours=int(m.group(2)), minutes=int(m.group(3)))
    return _dt.timezone(-delta if m.group(1) == "-" else delta)


def parse_date(value: Any) -> _dt.date | None:
    """A calendar date — a YAML date or a `YYYY-MM-DD` string — else None.
    A YAML timestamp is refused: `since` names a day, not an instant."""
    if isinstance(value, _dt.datetime):
        return None
    if isinstance(value, _dt.date):
        return value
    try:
        return _dt.date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def created_date(value: Any, tz: _dt.timezone) -> _dt.date | None:
    """The calendar day, in `tz`, a ticket was created on — or None.

    Accepts what adapters print and what a pitch's ticket record holds: an ISO
    8601 timestamp with an offset or `Z` (converted into `tz`), a bare
    `YYYY-MM-DD` (already a day, taken as is), or the YAML date / datetime
    those parse into (a naive YAML datetime is UTC — PyYAML's own reading).
    A timestamp with no offset is ambiguous by an up-to-a-day margin and is
    refused (None), which the callers treat as "creation date unknown".
    """
    if isinstance(value, _dt.datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=_dt.timezone.utc)
        return aware.astimezone(tz).date()
    if isinstance(value, _dt.date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    if len(s) == 10:
        return parse_date(s)
    try:
        # Python < 3.11 reads no `Z` suffix.
        stamp = _dt.datetime.fromisoformat(s[:-1] + "+00:00" if s[-1:] in ("Z", "z") else s)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        return None
    return stamp.astimezone(tz).date()


def rules_in_force(compiled: dict[str, Any], created: _dt.date | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """`compiled` cut down to the rules that judge a ticket created on
    `created`, plus the rules `since` withholds from it.

    `created` None means the creation date is unknown — every rule is in
    force (fail-closed), and the caller says so out loud. A rule without
    `since` is always in force.
    """
    if created is None:
        return compiled, []
    keep: list[dict[str, Any]] = []
    withheld: list[dict[str, Any]] = []
    for rule in compiled["rules"]:
        (withheld if rule.get("since") is not None and created < rule["since"] else keep).append(rule)
    return {**compiled, "rules": keep}, withheld


def has_since(compiled: dict[str, Any], target: str | None = None) -> bool:
    """Whether any rule (applying to `target`, when given) carries `since`."""
    return any(
        r.get("since") is not None and (target is None or target in r["applies_to"])
        for r in compiled["rules"]
    )


def earliest_since(compiled: dict[str, Any]) -> _dt.date | None:
    dates = [r["since"] for r in compiled["rules"] if r.get("since") is not None]
    return min(dates) if dates else None


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
        if "since_utc_offset" not in contract and "since_utc_offset" in bc:
            contract["since_utc_offset"] = bc["since_utc_offset"]
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
    meta = {
        "profile": profile_path, "fallback": fallback, **per_target,
        "since": {r["id"]: r["since"].isoformat() for r in compiled["rules"] if r.get("since") is not None},
        "since_utc_offset": offset_label(compiled["utc_offset"]),
    }
    return compiled, meta, warnings


def offset_label(tz: _dt.timezone) -> str:
    minutes = int(tz.utcoffset(None).total_seconds() // 60)
    sign = "-" if minutes < 0 else "+"
    return f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


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


def lint_subjects(parsed: dict[str, Any] | None, corrections: list[str]) -> tuple[list[tuple[dict[str, Any], tuple[str, int]]], int]:
    """Everything a lint judges, as (coordinate, block key) pairs, plus the
    number of struck items skipped — struck items are withdrawn requirements."""
    subjects: list[tuple[dict[str, Any], tuple[str, int]]] = []
    struck = 0
    for b in (parsed or {}).get("bindings", []):
        for g in b["groups"]:
            for it in g["items"]:
                if it.get("struck"):
                    struck += 1
                    continue
                subjects.append(({
                    "target": "ticket_item", "binding": b["id"], "heading": b["heading"],
                    "group": g["label"], "in_group": it["in_group"], "ordinal": it["ordinal"],
                    "line": it["line"], "text": it["text"],
                }, (b["id"], it["ordinal"])))
    for i, sentence in enumerate(corrections, 1):
        subjects.append(({
            "target": "correction", "binding": None, "heading": None, "group": None,
            "in_group": None, "ordinal": None, "line": None, "text": norm_text(sentence),
        }, ("", i)))
    return subjects, struck


def compute_lint(
    compiled: dict[str, Any], parsed: dict[str, Any] | None, corrections: list[str],
    created_at: Any = None, what: str = "the ticket",
) -> dict[str, Any]:
    """Lint `parsed`'s binding items and/or `corrections`.

    `created_at` is when the ticket was created (any form `created_date`
    reads; None = unknown) and `what` names it in warnings. A rule whose
    `since` falls after that day is withheld — reported in `since_skipped`
    with the hits it would have produced, never dropped silently. With the
    date unknown, every rule applies and a warning says so (fail-closed).
    """
    warnings: list[str] = []
    subjects, struck = lint_subjects(parsed, corrections)
    targets = {coord["target"] for coord, _ in subjects}
    created = created_date(created_at, compiled["utc_offset"])
    if created_at not in (None, "") and created is None:
        warnings.append(
            f"{what}: creation date {str(created_at)!r} is neither YYYY-MM-DD nor a timestamp "
            f"with an offset — read as unknown"
        )
    gated = [r["id"] for r in compiled["rules"] if r.get("since") is not None and targets & set(r["applies_to"])]
    if gated and created is None:
        warnings.append(
            f"{what} has no creation date — since-gated rule(s) {gated} applied anyway (fail-closed)"
        )
    active, withheld = rules_in_force(compiled, created)

    if parsed is not None:
        declared = {b["id"] for b in parsed["bindings"]}
        for rule in compiled["rules"]:
            unknown = sorted(set(rule["scope"] or ()) - declared)
            if unknown and "ticket_item" in rule["applies_to"]:
                warnings.append(
                    f"wording rule {rule['id']} is scoped to {unknown}, which this run does not declare "
                    f"as bindings {sorted(declared)} — it never fires there"
                )

    def judge(rules: dict[str, Any]) -> list[tuple[dict[str, Any], tuple[str, int]]]:
        out: list[tuple[dict[str, Any], tuple[str, int]]] = []
        for coord, key in subjects:
            for h in wording_hits(rules, coord["text"], coord["target"], coord["binding"]):
                out.append(({**coord, **h}, key))
        return out

    judged = judge(active)
    hits = [h for h, _ in judged]
    since_skipped = [
        {
            "rule": r["id"], "since": r["since"].isoformat(), "ticket_created": created.isoformat(),
            "withheld_hits": len(judge({**compiled, "rules": [r]})),
        }
        for r in withheld
        if targets & set(r["applies_to"])
    ] if created is not None else []
    return {
        "hits": hits,
        "counts": {
            "items": len(subjects),
            "struck_skipped": struck,
            "items_with_block": len({key for h, key in judged if h["severity"] == "block"}),
            "block": sum(h["severity"] == "block" for h in hits),
            "warn": sum(h["severity"] == "warn" for h in hits),
            "since_withheld": sum(row["withheld_hits"] for row in since_skipped),
        },
        "ticket_created": created.isoformat() if created is not None else None,
        "since_skipped": since_skipped,
        "warnings": warnings,
    }


def run_lint(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    # The profile first: a rule set that cannot be trusted stops the run before
    # anything is fetched.
    compiled, meta, rule_warnings = lint_rules(args.profile)
    if args.created_at is not None and not (args.correction or args.from_body):
        parser.error("--created-at goes with --correction or --from-body; a fetched ticket carries its own")
    if args.created_at is not None and created_date(args.created_at, compiled["utc_offset"]) is None:
        parser.error(f"--created-at must be YYYY-MM-DD or a timestamp with an offset, got {args.created_at!r}")
    parsed: dict[str, Any] | None = None
    created_at: Any = args.created_at
    what = "the corrections (no --created-at)"
    if args.id is not None or args.from_body:
        bindings = parse_binding_args(parser, args.binding, args.optional_binding)
        if args.from_body:
            if args.repo or args.fetch_command:
                parser.error("--repo / --fetch-command go with --id; --from-body reads a local file")
            try:
                parsed = parse_body(read_body(args.from_body), bindings)
            except (OSError, UnicodeDecodeError) as exc:
                parser.error(f"cannot read --from-body {args.from_body}: {exc}")
            # A local body is a draft about to be filed, or the template new
            # tickets are made from: unless told otherwise it is created today,
            # so every rule in force today judges it.
            if created_at is None:
                created_at = _dt.datetime.now(compiled["utc_offset"]).date().isoformat()
            what = f"--from-body {args.from_body}"
        else:
            validate_ticket_args(parser, args)
            ticket = obtain_ticket(args)
            parsed = parse_body(ticket["body"], bindings)
            parsed["source"] = source_block(args, ticket)
            created_at = ticket.get("created_at")
            what = f"ticket {args.repo + '#' if args.repo else ''}{ticket['id']}"
    else:
        if args.binding or args.optional_binding or args.repo or args.fetch_command:
            parser.error(
                "--binding / --optional-binding / --repo / --fetch-command go with --id; "
                "--from-json carries its own bindings and --correction has none"
            )
        if args.from_json:
            parsed = load_parsed_json(args.from_json)
            src = parsed.get("source") if isinstance(parsed.get("source"), dict) else {}
            created_at = src.get("created_at")
            what = f"--from-json {args.from_json}" + (
                f" (ticket {src.get('repo') + '#' if src.get('repo') else ''}{src.get('id')})" if src.get("id") else ""
            )
    lint = compute_lint(compiled, parsed, args.correction or [], created_at, what)
    result = {
        "schema": SCHEMA,
        "source": parsed.get("source") if parsed else None,
        "rules": meta,
        "ticket_created": lint["ticket_created"],
        "hits": lint["hits"],
        "counts": lint["counts"],
        "since_skipped": lint["since_skipped"],
        "absent": parsed.get("absent", []) if parsed else [],
        "warnings": rule_warnings + lint["warnings"] + (list(parsed.get("warnings", [])) if parsed else []),
        "errors": list(parsed.get("errors", [])) if parsed else [],
    }
    emit(result, args.compact)
    return 1 if (result["counts"]["block"] or result["errors"]) else 0


# --------------------------------------------------------------------------
# gate — the spec repo's merge gate over every ticket an active pitch cites
# --------------------------------------------------------------------------

LEDGER_FILENAME = "contract-acknowledgements.yml"
LEDGER_SCHEMA = 1
LEDGER_KINDS = ("accepted_violation", "false_positive")
LEDGER_KEYS = ("tracker", "repo", "id", "binding", "group", "in_group", "rule", "kind", "reason", "decided_by", "date")
LEDGER_REQUIRED = tuple(k for k in LEDGER_KEYS if k != "repo")
GATE_MODES = ("off", "warn", "on")
# `### <tracker> <repo>#<id> · <binding heading> · [<group> ]<in_group>` — the
# disagreement entry header /immutable:prd writes; an ungrouped item has no
# group label, only the number (「… · 완료 조건 · 2」).
DISAGREEMENT_TITLE_RE = re.compile(
    r"^(?P<tracker>\S+)\s+(?P<repo>[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*)?"
    r"#(?P<id>[A-Za-z0-9][A-Za-z0-9._-]*)\s*·\s*(?P<heading>.+?)\s*·\s*"
    r"(?:(?P<group>.*?\S)\s+)?(?P<n>\d+)\s*$"
)


def ledger_entries(data: Any, default_repo: str | None) -> tuple[list[dict[str, Any]], list[str]]:
    """The acknowledgement ledger (v0.15+) → normalised entries + problems.

    The ledger is a repo-level file, not pitch frontmatter: pitches are
    append-only, so a pitch merged before a rule existed can never gain a
    field. Each entry names ONE block hit by its coordinate — tracker, repo,
    id, binding, group, in_group, rule — and says why it may stand: `kind`
    `accepted_violation` (a pitch was bound to the item before the rule could
    be raised) or `false_positive` (the rule is wrong in context), with
    `reason`, `decided_by`, `date`. `repo` may be omitted for the config's
    default repository, as in a pitch's ticket record.

    The ONE reader of the file: `gate` subtracts the entries from the live
    block hits, `validate_docs.py` checks the shape offline. Strict on
    purpose — an unknown key is a problem, because a typo in a coordinate key
    would otherwise drop the coordinate and silently widen the exemption.
    """
    if data is None:
        return [], []
    if not isinstance(data, dict):
        return [], ["the ledger must be a mapping with `schema` and `acknowledgements`"]
    problems: list[str] = []
    if data.get("schema") != LEDGER_SCHEMA:
        problems.append(f"`schema` must be {LEDGER_SCHEMA}, got {data.get('schema')!r}")
    unknown_top = sorted(str(k) for k in set(data) - {"schema", "acknowledgements"})
    if unknown_top:
        problems.append(f"unknown top-level key(s) {unknown_top}")
    raw = data.get("acknowledgements")
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        return [], problems + ["`acknowledgements` must be a list"]

    def text(v: Any) -> bool:
        return isinstance(v, str) and bool(v.strip())

    entries: list[dict[str, Any]] = []
    seen: dict[tuple[Any, ...], int] = {}
    for i, e in enumerate(raw, 1):
        where = f"acknowledgements[{i}]"
        if not isinstance(e, dict):
            problems.append(f"{where} must be a mapping")
            continue
        bad: list[str] = []
        unknown = sorted(str(k) for k in set(e) - set(LEDGER_KEYS))
        if unknown:
            bad.append(f"unknown key(s) {unknown}")
        missing = [k for k in LEDGER_REQUIRED if k not in e]
        if missing:
            bad.append(f"missing {missing}")
        if "tracker" in e and not text(e["tracker"]):
            bad.append("`tracker` must be a non-empty string")
        repo = e.get("repo")
        if repo is not None and not (isinstance(repo, str) and REPO_RE.match(repo)):
            bad.append(f"`repo` must be OWNER/NAME, got {repo!r}")
        tid = e.get("id")
        tid = str(tid) if isinstance(tid, (str, int)) and not isinstance(tid, bool) else None
        if "id" in e and not (tid and TICKET_ID_RE.match(tid)):
            bad.append(f"`id` must be the bare ticket id, got {e.get('id')!r}")
        for key in ("binding", "rule"):
            if key in e and not (isinstance(e[key], str) and BINDING_ID_RE.match(e[key])):
                bad.append(f"`{key}` must match [a-z][a-z0-9_]*, got {e[key]!r}")
        group = e.get("group")
        if group is not None and not text(group):
            bad.append("`group` must be the ticket's group label, or null for an ungrouped item")
        n = e.get("in_group")
        if "in_group" in e and not (isinstance(n, int) and not isinstance(n, bool) and n > 0):
            bad.append(f"`in_group` must be a positive integer, got {n!r}")
        if "kind" in e and e["kind"] not in LEDGER_KINDS:
            bad.append(f"`kind` must be one of {list(LEDGER_KINDS)}, got {e['kind']!r}")
        for key in ("reason", "decided_by"):
            if key in e and not text(e[key]):
                bad.append(f"`{key}` must be a non-empty string")
        date = e.get("date")
        if "date" in e:
            try:
                date = date if isinstance(date, _dt.date) else _dt.date.fromisoformat(str(date))
            except ValueError:
                bad.append(f"`date` must be YYYY-MM-DD, got {e['date']!r}")
        if bad:
            problems.append(f"{where}: " + "; ".join(bad))
            continue
        entry = {
            "index": i, "tracker": e["tracker"].strip(), "repo": repo or default_repo, "id": tid,
            "binding": e["binding"], "group": None if group is None else norm_text(group),
            "in_group": n, "rule": e["rule"], "kind": e["kind"], "reason": e["reason"].strip(),
            "decided_by": e["decided_by"].strip(), "date": date.isoformat(),
        }
        key = ledger_key(entry)
        if key in seen:
            problems.append(f"{where}: same coordinate and rule as acknowledgements[{seen[key]}]")
            continue
        seen[key] = i
        entries.append(entry)
    return entries, problems


def ledger_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (row["tracker"], row["repo"], row["id"], row["binding"], row["group"], row["in_group"], row["rule"])


def disagreement_titles(text: str, heading: str) -> list[str]:
    """`### ` titles under the body's `## <heading>` section (fences ignored)."""
    m = FRONTMATTER_RE.match(text)
    lines = preprocess(text[m.end():] if m else text)
    fenced = fenced_lines(lines)
    titles: list[str] = []
    inside = False
    for i, ln in enumerate(lines):
        if i in fenced:
            continue
        hm = HEADING_RE.match(ln)
        if not hm:
            continue
        level, title = len(hm.group(1)), norm_text(hm.group(2))
        if level <= 2:
            inside = level == 2 and title == norm_text(heading)
        elif inside and level == 3:
            titles.append(title)
    return titles


def disagreement_coordinate(
    title: str, bindings: list[tuple[str, str, bool]], default_repo: str | None
) -> dict[str, Any] | None:
    """The item a disagreement entry contests, from its header — or None when
    the header does not name a ticket item this run declares."""
    m = DISAGREEMENT_TITLE_RE.match(title)
    if not m:
        return None
    key = norm_heading(m.group("heading"))
    binding = next((bid for bid, heading, _ in bindings if norm_heading(heading) == key), None)
    if binding is None:
        return None
    group = m.group("group")
    return {
        "tracker": m.group("tracker"), "repo": m.group("repo") or default_repo, "id": m.group("id"),
        "binding": binding, "group": None if group is None else norm_text(group), "in_group": int(m.group("n")),
    }


def gate_ticket(args: argparse.Namespace, repo: str | None, ticket_id: str) -> dict[str, Any]:
    if args.fetch_command:
        raw = command_fetch(args.fetch_command, repo, ticket_id)
    else:
        if not repo:
            adapter_fail(f"ticket {ticket_id} names no repo and --repo gives no default")
        raw = github_fetch(repo, ticket_id)
    return normalize_ticket(raw, ticket_id)


def compute_gate(parser: argparse.ArgumentParser, args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    bindings = parse_binding_args(parser, args.binding, args.optional_binding)
    compiled, meta, warnings = lint_rules(args.profile)
    profile = load_yaml_file(args.profile, "profile") or {}
    heading = next(
        (str(s.get("heading") or "").strip() for s in profile.get("sections") or []
         if isinstance(s, dict) and s.get("id") == "requirement_disagreement"),
        "",
    )
    if not heading:
        warnings.append(
            "the profile has no sections[id=requirement_disagreement] heading — no disagreement "
            "entry is read, so no block hit is resolved by one"
        )

    ledger_info: dict[str, Any] = {"path": args.ledger, "found": False, "entries": 0}
    entries: list[dict[str, Any]] = []
    problems: list[str] = []
    if args.ledger:
        if Path(args.ledger).is_file():
            ledger_info["found"] = True
            entries, problems = ledger_entries(load_yaml_file(args.ledger, "ledger"), args.repo)
            ledger_info["entries"] = len(entries)
        else:
            warnings.append(f"ledger {args.ledger} not found — no hit is acknowledged")
    ledger = {ledger_key(e): e for e in entries}

    # The set: active pitches (not `deprecated: true`) and the tickets they cite.
    cited: dict[tuple[str, str | None, str], list[str]] = {}
    contested: dict[tuple[Any, ...], list[str]] = {}
    unmatched: list[dict[str, str]] = []
    for path in args.pitches:
        fm = load_frontmatter_yaml(path)
        if fm is None:
            warnings.append(f"{path}: no readable frontmatter; skipped")
            continue
        if fm.get("deprecated") is True:
            continue
        refs = fm.get("references") or {}
        own: set[tuple[str, str | None, str]] = set()
        for entry in (refs.get("tickets") or []) if isinstance(refs, dict) else []:
            if not isinstance(entry, dict) or entry.get("id") is None:
                continue
            tracker = str(entry.get("tracker") or "github")
            if tracker != args.tracker:
                warnings.append(f"{path}: cites a {tracker} ticket; this gate checks {args.tracker} tickets only")
                continue
            key = (tracker, str(entry.get("repo") or args.repo or "") or None, str(entry["id"]))
            cited.setdefault(key, []).append(path)
            own.add(key)
        if not heading or not own:
            continue
        body = open(path, "rb").read().decode("utf-8")
        for title in disagreement_titles(body, heading):
            coord = disagreement_coordinate(title, bindings, args.repo)
            if coord is None or (coord["tracker"], coord["repo"], coord["id"]) not in own:
                unmatched.append({"pitch": path, "title": title, "why": (
                    "header names no binding item this run declares" if coord is None
                    else "header names a ticket this pitch does not cite"
                )})
                continue
            contested.setdefault(ledger_key({**coord, "rule": None})[:6], []).append(path)

    tickets_out: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = []
    since_skipped: list[dict[str, Any]] = []
    errors: list[str] = []
    fetch_failed = False
    live_block: set[tuple[Any, ...]] = set()
    checked: set[tuple[str, str | None, str]] = set()
    for key in sorted(cited, key=lambda k: (k[0], k[1] or "", k[2])):
        tracker, repo, tid = key
        row: dict[str, Any] = {
            "tracker": tracker, "repo": repo, "id": tid, "cited_by": cited[key], "version": None,
            "created": None, "block_hits": 0, "by_disagreement": 0, "by_ledger": 0, "remaining": 0,
            "since_skipped": [], "errors": [],
        }
        tickets_out.append(row)
        try:
            ticket = gate_ticket(args, repo, tid)
        except ContractError as exc:
            fetch_failed = True
            row["errors"].append(f"could not fetch: {exc}")
            errors.append(f"{tracker} {repo}#{tid}: could not fetch: {exc}")
            continue
        checked.add(key)
        row["version"] = ticket["version"]
        parsed = parse_body(ticket["body"], bindings)
        for e in parsed["errors"]:
            row["errors"].append(e)
            errors.append(f"{tracker} {repo}#{tid}: {e} — the ticket cannot be shown clean")
        lint = compute_lint(compiled, parsed, [], ticket.get("created_at"), f"{tracker} {repo}#{tid}")
        warnings.extend(w for w in lint["warnings"] if w not in warnings)
        row["created"] = lint["ticket_created"]
        row["since_skipped"] = lint["since_skipped"]
        for s in lint["since_skipped"]:
            since_skipped.append({"tracker": tracker, "repo": repo, "id": tid, **s})
        for h in lint["hits"]:
            if h["severity"] != "block":
                continue
            row["block_hits"] += 1
            coord = {"tracker": tracker, "repo": repo, "id": tid, "binding": h["binding"],
                     "group": h["group"], "in_group": h["in_group"], "rule": h["rule"]}
            live_block.add(ledger_key(coord))
            hit = {**coord, "ordinal": h["ordinal"], "line": h["line"], "text": h["text"],
                   "category": h["category"], "match": h["match"], "hint": h["hint"]}
            by_pitch = contested.get(ledger_key(coord)[:6])
            ack = ledger.get(ledger_key(coord))
            if by_pitch:
                row["by_disagreement"] += 1
                resolved.append({**hit, "by": "disagreement", "where": by_pitch})
                if ack:
                    warnings.append(
                        f"acknowledgements[{ack['index']}] is redundant: a disagreement entry in "
                        f"{', '.join(by_pitch)} already contests that item"
                    )
            elif ack:
                row["by_ledger"] += 1
                resolved.append({**hit, "by": "ledger", "where": f"acknowledgements[{ack['index']}]", "kind": ack["kind"]})
            else:
                row["remaining"] += 1
                remaining.append({**hit, "cited_by": cited[key]})

    # Eviction: an acknowledgement stands only while its hit does.
    stale: list[dict[str, Any]] = []
    for e in entries:
        tkey = (e["tracker"], e["repo"], e["id"])
        if tkey not in cited:
            why = "no active pitch cites that ticket"
        elif tkey not in checked:
            continue  # the fetch failed; reported as an error, not judged stale
        elif ledger_key(e) not in live_block:
            why = "the live ticket has no block hit with that coordinate and rule (ticket edited, or rule changed)"
        else:
            continue
        stale.append({k: e[k] for k in ("index", *LEDGER_KEYS)} | {"why": why})

    failing = bool(remaining or stale or problems or errors)
    result = {
        "schema": SCHEMA,
        "mode": args.mode,
        "verdict": ("fail" if args.mode == "on" else "warn") if failing else "pass",
        "rules": meta,
        "ledger": {**ledger_info, "problems": problems},
        "tickets": tickets_out,
        "remaining": remaining,
        "stale": stale,
        "resolved": resolved,
        "since_skipped": since_skipped,
        "unmatched_disagreements": unmatched,
        "warnings": warnings,
        "errors": errors,
    }
    if args.mode == "warn" or not failing:
        return result, 0
    return result, 2 if fetch_failed else 1


def run_gate(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    if args.mode == "off":
        # Switched off: nothing is fetched, so the switch costs nothing in CI.
        emit({"schema": SCHEMA, "mode": "off", "verdict": "off"}, args.compact)
        return 0
    if args.repo is not None and not REPO_RE.match(args.repo):
        parser.error(f"--repo must be OWNER/NAME, got {args.repo!r}")
    result, code = compute_gate(parser, args)
    emit(result, args.compact)
    withheld = [s for s in result["since_skipped"] if s["withheld_hits"]]
    if withheld:
        sys.stderr.write(
            f"note: contract gate: since-gated rule(s) withheld {sum(s['withheld_hits'] for s in withheld)} "
            f"hit(s) on {len({(s['tracker'], s['repo'], s['id']) for s in withheld})} ticket(s) created "
            f"before the rule's since date — listed in since_skipped[]\n"
        )
    if result["verdict"] == "warn":
        sys.stderr.write(
            f"warning: contract gate (warn mode): {len(result['remaining'])} unresolved block hit(s), "
            f"{len(result['stale'])} stale acknowledgement(s), {len(result['ledger']['problems'])} ledger "
            f"problem(s), {len(result['errors'])} error(s) — would fail with --mode on\n"
        )
    return code


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
    try:
        return run(argv)
    except ContractError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2


def run(argv: list[str] | None = None) -> int:
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
    src.add_argument(
        "--from-body", metavar="BODY.md", dest="from_body",
        help="lint the binding sections of a local markdown body (a draft about to be filed, or a "
             "ticket template) — no tracker; needs --binding like --id",
    )
    p_lint.add_argument(
        "--created-at", metavar="DATE", dest="created_at",
        help="with --correction or --from-body: the ticket's creation date (YYYY-MM-DD, or a "
             "timestamp with an offset) that since-gated rules compare against. --from-body "
             "defaults to today; --correction without it applies every rule and warns",
    )
    p_lint.add_argument("--repo", metavar="OWNER/NAME", help="with --id: repository the ticket lives in")
    p_lint.add_argument("--tracker", default="github", metavar="NAME", help="with --id: label recorded in `source.tracker`")
    p_lint.add_argument("--fetch-command", metavar="TEMPLATE", help="with --id: adapter command, as for `fetch`")
    add_common(p_lint)

    p_gate = sub.add_parser(
        "gate", help="the merge gate: every block hit on a ticket an active pitch cites must be contested or acknowledged",
    )
    p_gate.add_argument("--mode", required=True, choices=GATE_MODES, help="off: no-op · warn: report, exit 0 · on: fail on anything unresolved")
    p_gate.add_argument("--profile", required=True, metavar="PROFILE.yml", help="the active profile (wording rules + disagreement heading)")
    p_gate.add_argument(
        "--ledger", metavar="LEDGER.yml",
        help=f"the acknowledgement ledger (conventionally .immutable-prd/{LEDGER_FILENAME}); absent = no acknowledgements",
    )
    p_gate.add_argument("--repo", metavar="OWNER/NAME", help="default repository for a ticket record or ledger entry without `repo`")
    p_gate.add_argument("--tracker", default="github", metavar="NAME", help="the tracker whose tickets this gate checks (default: github)")
    p_gate.add_argument("--fetch-command", metavar="TEMPLATE", help="adapter command, as for `fetch`")
    p_gate.add_argument("pitches", nargs="*", metavar="PITCH.md", help="pitch files; the active ones (not deprecated) form the set")
    add_common(p_gate)

    args = parser.parse_args(argv)
    if args.command == "lint":
        return run_lint(parser, args)
    if args.command == "gate":
        return run_gate(parser, args)
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
