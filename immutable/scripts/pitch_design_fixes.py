#!/usr/bin/env python3
"""Deliver confirmed design corrections through an opted-in GitHub tracker's workflow.

Run from the spec root. Supply the fetched contract JSON, its pinned design
dump, the written pitch, and a saved JSON list of {key, pin, fact, quote, change}.
The input file is the retry record. A workflow run alone is not a receipt.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from figma_pin_texts import figma_links, scoped_text
from requirement_contract import load_frontmatter_yaml, ticket_records

WORKFLOW = "design-fix.yml"
KEY = re.compile(r"[a-z0-9][a-z0-9-]{0,79}")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
WAIT_SECONDS = 180


def gh(*args, stdin=None):
    return subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True,
                          timeout=60, check=True).stdout.strip()


def rows_for(contract, design, pitch, rows):
    source = contract["source"]
    if pitch.is_absolute() or ".." in pitch.parts or pitch.parts[:1] != ("pitches",):
        raise ValueError("pitch must be a repository-relative pitches/ path")
    frontmatter = load_frontmatter_yaml(str(pitch)) or {}
    if frontmatter.get("deprecated") is True:
        raise ValueError("cannot deliver from a deprecated pitch")
    refs = ticket_records(frontmatter)
    match = ("tracker", "repo", "id", "version")
    if not any(all(str(ref.get(k)) == str(source[k]) for k in match) for ref in refs):
        raise ValueError("the written pitch does not reference this ticket revision")
    text = pitch.read_text(encoding="utf-8").split("---", 2)[-1]
    pins = {p["url"] for p in design["pins"] if not p.get("error") and p.get("screens")}
    bound, _ = figma_links(scoped_text(None, contract["sections"], design.get("section") or []))
    pins.intersection_update(p["url"] for p in bound)
    if not isinstance(rows, list) or not rows:
        raise ValueError("expected a nonempty list of confirmed design fixes")
    items = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"key", "pin", "fact", "quote", "change"}:
            raise ValueError("expected key, pin, fact, quote and change")
        if any(not isinstance(v, str) or not v.strip() or v != v.strip() or
               len(v.splitlines()) != 1 or len(v) > 4000 for v in row.values()):
            raise ValueError("request fields must be single nonempty lines, at most 4000 characters")
        key = row["key"]
        if not KEY.fullmatch(key) or key in items:
            raise ValueError(f"invalid or duplicate item key: {key}")
        if row["pin"] not in pins or row["quote"] not in text:
            raise ValueError(f"{key}: missing readable source pin or literal pitch quotation")
        payload = {k: row[k] for k in ("pin", "fact", "change")}
        payload["pitch"] = f"{pitch.as_posix()} — {row['quote']}"
        if len(payload["pitch"]) > 4000:
            raise ValueError(f"{key}: pitch citation is too long")
        items[key] = payload
    return items


def receipt(repo, issue, key, payload):
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    prefix = f"<!-- design-fix {key} "
    marker = f"{prefix}{digest} {payload['pin']} -->"
    comments = gh("api", "--paginate", f"repos/{repo}/issues/{issue}/comments?per_page=100",
                  "--jq", '.[] | select(.user.type == "Bot" and (.body | startswith("<!-- design-fix "))) | [.body,.html_url] | @json')
    for line in comments.splitlines():
        body, url = json.loads(line)
        header = body.splitlines()[0]
        if header == marker:
            return url
        if header.startswith(prefix):
            raise ValueError(f"{key}: the recorded request has different evidence")
    return None


def deliver(source, items):
    if source["tracker"] != "github":
        return False
    repo, issue = source["repo"], str(source["id"])
    if not REPO.fullmatch(repo) or not re.fullmatch(r"[1-9][0-9]*", issue):
        raise ValueError("invalid bound GitHub repository or issue number")
    states = gh("api", "--paginate", f"repos/{repo}/actions/workflows?per_page=100", "--jq",
                '.workflows[] | select(.path == ".github/workflows/design-fix.yml") | .state')
    if not states:
        return False
    if states != "active":
        raise ValueError(f"{repo}/{WORKFLOW} is {states}")
    for key, payload in items.items():
        url = receipt(repo, issue, key, payload)
        if not url:
            result = gh("workflow", "run", WORKFLOW, "-R", repo, "--json", stdin=json.dumps(
                {"issue": issue, "key": key, "request": json.dumps(payload, ensure_ascii=False)}))
            print(result, flush=True)
            run = re.search(r"/actions/runs/(\d+)\b", result)
            deadline = time.monotonic() + WAIT_SECONDS
            while not url:
                url = receipt(repo, issue, key, payload)
                if url:
                    break
                if run:
                    state = gh("api", f"repos/{repo}/actions/runs/{run[1]}", "--jq", '.conclusion // ""')
                    if state and state != "success":
                        raise ValueError(f"{key}: dispatched run ended with {state}")
                if time.monotonic() >= deadline:
                    raise ValueError(f"{key}: no Epic comment confirmed yet; retry the saved request")
                time.sleep(5)
        print(f"{key} {url}", flush=True)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("contract", "design", "pitch", "requests"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    def read(path):
        return json.loads(path.read_text(encoding="utf-8"))
    contract = read(args.contract)
    rows = rows_for(contract, read(args.design), args.pitch, read(args.requests))
    if not deliver(contract["source"], rows):
        print(f"No tracker receiver installed. Saved handoff: {args.requests}")
        return 3
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.stderr.strip() or str(exc))
    except (KeyError, TypeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        sys.exit(str(exc))
