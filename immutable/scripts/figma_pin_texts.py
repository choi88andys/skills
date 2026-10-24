#!/usr/bin/env python3
"""figma_pin_texts.py — dump what every design a ticket PINS shows, screen by screen.

`/immutable:prd` Stage 1.6 compares a ticket's binding items with the designs
the ticket links. The Figma MCP tools read only a file's current state, never a
pinned version, so a design pinned by `version-id=` (the only kind a ticket can
cite and still mean one thing) is read here through the REST API:

  GET https://api.figma.com/v1/files/<file_key>/nodes?ids=<node:id>&version=<version-id>
  header X-Figma-Token: $FIGMA_TOKEN

For each pinned link it prints the linked node's screens in reading order, each
screen's texts in reading order, and each screen's own child frames in order —
enough to compare presence, order and states with the binding items (on the
measured case, an Epic whose home toasts were stacked 광고성 → 마케팅 → 야간 in
the pinned design while an acceptance item listed another order). The script
judges nothing; the skill compares, and a difference becomes a candidate the
user resolves.

Input — exactly one of:
  --body FILE          a ticket body (markdown); `-` = stdin
  --from-json FILE     the JSON `requirement_contract.py parse|fetch` printed —
                       its `sections[]` carry each section's raw text
Narrow with `--section HEADING` (repeatable; matched like a binding heading —
「」, a trailing colon, case and whitespace ignored), conventionally the
ticket's design section (「기획 / 디자인」). Without it every link in the body
counts. HTML comments are ignored, as the parser ignores them.

A link counts as pinned when it is a figma.com design/file/proto URL carrying
`version-id` and `node-id`. A Figma link without a version-id is reported in
`unpinned[]` and not fetched — what it shows today is not what the ticket saw.

Output (`schema: 1`, JSON on stdout):
  pins[]      url, label (the markdown link text, or null), file_key, node_id
              (`123:456`), version_id, name / type of the linked node, and
              screens[] — for a linked SECTION or page, its direct FRAME /
              COMPONENT / COMPONENT_SET / INSTANCE / SECTION / GROUP children;
              for any other node (a frame), the node itself — each with
              `order`, `id`, `name`, `type`, `box`
              (absoluteBoundingBox x, y, w, h), `texts[]` (every visible TEXT
              descendant: `order`, `name`, `text` — `characters` with Figma's
              U+2028 soft breaks turned into newlines) and `frames[]` (the
              screen's own container children: `order`, `id`, `name`). Order is
              top-to-bottom, then left-to-right, by absoluteBoundingBox; the
              boxes are printed so a reader can re-read a row layout. Hidden
              nodes (`visible: false`) are skipped. A pin that could not be read
              carries `error` and no screens.
  unpinned[]  url, label
  errors[]    one line per pin that could not be read

Exit codes: 0 every pinned link read (none found is 0, and `pins` is empty) ·
1 at least one pinned link could not be read · 2 usage error, unreadable
input, or FIGMA_TOKEN unset when a fetch is needed.

`--from-response DIR` reads saved API responses instead of calling the API —
`DIR/<file_key>_<node-id with : as ->_<version_id>.json` — for tests and for
re-reading a response without spending the token's rate limit. No token is
needed then.

Requires python3 only (urllib). The token is a Figma personal access token
with read access to the file; it is read from the environment and never
printed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import requirement_contract as _contract  # noqa: E402

SCHEMA = 1
API_BASE = "https://api.figma.com/v1"
TOKEN_ENV = "FIGMA_TOKEN"
TIMEOUT_SECONDS = 60
FIGMA_URL_RE = re.compile(
    r"https?://(?:www\.)?figma\.com/(?:design|file|proto)/(?P<key>[A-Za-z0-9]+)[^\s)\]>\"'`]*"
)
MD_LINK_RE = re.compile(r"\[(?P<label>[^\]]*)\]\((?P<url>[^)\s]+)\)")
CONTAINER_TYPES = ("FRAME", "COMPONENT", "COMPONENT_SET", "INSTANCE", "SECTION", "GROUP")
# A linked node of these types is a board of screens; any other linked node
# (a FRAME, an INSTANCE, …) is one screen, whose child frames are its parts.
BOARD_TYPES = ("SECTION", "CANVAS")
SOFT_BREAK = " "


def fail(msg: str) -> None:
    sys.stderr.write(f"error: {msg}\n")
    sys.exit(2)


def scoped_text(body: str | None, sections: list[dict[str, Any]] | None, wanted: list[str]) -> str:
    """The text the links are taken from: the whole body, or only the named
    sections. `body` comes from --body, `sections` from --from-json."""
    keys = {_contract.norm_heading(h) for h in wanted}
    if sections is not None:
        return "\n".join(
            str(s.get("text") or "") for s in sections
            if not keys or _contract.norm_heading(str(s.get("heading") or "")) in keys
        )
    lines = _contract.preprocess(body or "")
    if not keys:
        return "\n".join(lines)
    heads = _contract.outline(lines, _contract.fenced_lines(lines))
    return "\n".join(
        "\n".join(lines[h["line"] + 1 : h["end"]])
        for h in heads if _contract.norm_heading(h["title"]) in keys
    )


def figma_links(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(pinned, unpinned) Figma links in `text`, first occurrence order, deduplicated."""
    labels: dict[str, str] = {}
    for m in MD_LINK_RE.finditer(text):
        labels.setdefault(m.group("url"), m.group("label").strip())
    pinned: list[dict[str, Any]] = []
    unpinned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in FIGMA_URL_RE.finditer(text):
        url = m.group(0)
        if url in seen:
            continue
        seen.add(url)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        version = (query.get("version-id") or [None])[0]
        node = (query.get("node-id") or [None])[0]
        row = {"url": url, "label": labels.get(url) or None}
        if not version or not node:
            unpinned.append(row)
            continue
        pinned.append({**row, "file_key": m.group("key"), "node_id": node.replace("-", ":"), "version_id": version})
    return pinned, unpinned


def response_path(directory: str, pin: dict[str, Any]) -> Path:
    return Path(directory) / f"{pin['file_key']}_{pin['node_id'].replace(':', '-')}_{pin['version_id']}.json"


def fetch_nodes(pin: dict[str, Any], token: str | None, saved: str | None) -> dict[str, Any]:
    """The API's nodes response for one pin. Raises ValueError with a reason."""
    if saved:
        path = response_path(saved, pin)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read saved response {path}: {exc}") from None
    query = urllib.parse.urlencode({"ids": pin["node_id"], "version": pin["version_id"]})
    req = urllib.request.Request(
        f"{API_BASE}/files/{pin['file_key']}/nodes?{query}", headers={"X-Figma-Token": token or ""}
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200].strip()
        raise ValueError(f"Figma API answered {exc.code}: {detail or exc.reason}") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError(f"Figma API request failed: {exc}") from None


def reading_key(node: dict[str, Any]) -> tuple[float, float]:
    box = node.get("absoluteBoundingBox") or {}
    return (float(box.get("y") or 0), float(box.get("x") or 0))


def visible(node: dict[str, Any]) -> bool:
    return node.get("visible", True) is not False


def box_of(node: dict[str, Any]) -> dict[str, Any] | None:
    box = node.get("absoluteBoundingBox")
    if not isinstance(box, dict):
        return None
    return {"x": box.get("x"), "y": box.get("y"), "w": box.get("width"), "h": box.get("height")}


def containers(node: dict[str, Any]) -> list[dict[str, Any]]:
    kids = [c for c in node.get("children") or [] if isinstance(c, dict) and visible(c) and c.get("type") in CONTAINER_TYPES]
    return sorted(kids, key=reading_key)


def text_nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    stack = [node]
    while stack:
        n = stack.pop()
        if not visible(n):
            continue
        if n.get("type") == "TEXT":
            out.append(n)
        stack.extend(c for c in n.get("children") or [] if isinstance(c, dict))
    return sorted(out, key=reading_key)


def screens_of(root: dict[str, Any]) -> list[dict[str, Any]]:
    """The linked node's screens: a section's or page's container children,
    else the node itself."""
    boards = containers(root) if root.get("type") in BOARD_TYPES else []
    rows: list[dict[str, Any]] = []
    for i, screen in enumerate(boards or [root], 1):
        rows.append({
            "order": i, "id": screen.get("id"), "name": screen.get("name"), "type": screen.get("type"),
            "box": box_of(screen),
            "texts": [
                {"order": j, "name": t.get("name"), "text": str(t.get("characters") or "").replace(SOFT_BREAK, "\n")}
                for j, t in enumerate(text_nodes(screen), 1)
            ],
            "frames": [{"order": j, "id": f.get("id"), "name": f.get("name")} for j, f in enumerate(containers(screen), 1)],
        })
    return rows


def read_pin(pin: dict[str, Any], token: str | None, saved: str | None) -> dict[str, Any]:
    try:
        data = fetch_nodes(pin, token, saved)
    except ValueError as exc:
        return {**pin, "name": None, "type": None, "screens": [], "error": str(exc)}
    node = ((data or {}).get("nodes") or {}).get(pin["node_id"]) if isinstance(data, dict) else None
    doc = node.get("document") if isinstance(node, dict) else None
    if not isinstance(doc, dict):
        why = (data or {}).get("err") if isinstance(data, dict) else None
        return {**pin, "name": None, "type": None, "screens": [],
                "error": f"node {pin['node_id']} not in the response at version {pin['version_id']}"
                         + (f" ({why})" if why else "")}
    return {**pin, "name": doc.get("name"), "type": doc.get("type"), "screens": screens_of(doc)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="figma_pin_texts.py", description="Dump the texts and frame order of every design a ticket pins (see module docstring).",
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--body", metavar="FILE", help="a ticket body in markdown (`-` = stdin)")
    src.add_argument("--from-json", metavar="FILE", dest="from_json", help="the JSON requirement_contract.py parse|fetch printed")
    parser.add_argument("--section", action="append", default=[], metavar="HEADING",
                        help="only links under this heading (repeatable), e.g. \"기획 / 디자인\"")
    parser.add_argument("--from-response", metavar="DIR", dest="from_response",
                        help="read saved nodes responses from DIR instead of calling the API (no token needed)")
    parser.add_argument("--compact", action="store_true", help="single-line JSON")
    args = parser.parse_args(argv)

    body: str | None = None
    sections: list[dict[str, Any]] | None = None
    try:
        if args.body is not None:
            body = _contract.read_body(args.body)
        else:
            data = json.loads(_contract.read_body(args.from_json))
            if not isinstance(data, dict) or not isinstance(data.get("sections"), list):
                fail(f"--from-json {args.from_json} is not the JSON `parse` or `fetch` prints (no `sections`)")
            sections = data["sections"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"cannot read the input: {exc}")

    pinned, unpinned = figma_links(scoped_text(body, sections, args.section))
    token = os.environ.get(TOKEN_ENV, "").strip() or None
    if pinned and not args.from_response and not token:
        fail(
            f"{TOKEN_ENV} is not set — {len(pinned)} pinned design link(s) need the Figma REST API "
            f"(a personal access token with read access to the file); the MCP tools cannot read a "
            f"pinned version"
        )
    pins = [read_pin(p, token, args.from_response) for p in pinned]
    errors = [f"{p['url']}: {p['error']}" for p in pins if p.get("error")]
    result = {"schema": SCHEMA, "section": args.section or None, "pins": pins, "unpinned": unpinned, "errors": errors}
    sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False, indent=None if args.compact else 2) + "\n").encode("utf-8"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
