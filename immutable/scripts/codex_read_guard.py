#!/usr/bin/env python3
"""PreToolUse(Bash): deny a supported raw document read and print a standalone retry."""
import json
import re
import shlex
import sys
from pathlib import Path

from read_doc import document_scope, line_range
from search_docs import Search

SCRIPTS = Path(__file__).resolve().parent
# Recognize ordinary shell words and separators, retaining quotes until AFTER
# splitting commands. A quoted '; cat ...' is always one argument. Do not
# evaluate substitutions, patterns, redirections, groups or shell programs.
WORD = r"""(?:[^\s'"\\;&|<>()]+|'[^']*'|"(?:\\.|[^"\\])*"|\\.)+"""
TOKEN = re.compile(r"(?P<space>[ \t]+)|(?P<comment>\#[^\n]*)|(?P<op>&&|\|\||[;|\n])|(?P<word>" + WORD + ")")


def commands(command):
    """Split a flat list/pipeline into (preceding operator, argv, next operator)."""
    result = []
    argv = []
    before = ""
    pos = 0
    while pos < len(command):
        token = TOKEN.match(command, pos)
        if not token:
            return []  # unsupported syntax, e.g. a here-document
        pos = token.end()
        if token.lastgroup == "word":
            word, = shlex.split(token.group())
            argv.append(word)
        elif token.lastgroup == "op":
            after = token.group()
            if argv:
                result.append((before, argv, after))
                argv = []
                before = after
            elif after != "\n":
                before = after
    if argv:
        result.append((before, argv, ""))
    return result


def in_scope(path):
    if path.suffix != ".md" and not path.is_symlink():
        return False
    return path.is_file() and document_scope(path)[1] is not None


def retry_for(argv, cwd, piped):
    name, *args = argv
    reader = ["python3", "-B", str(SCRIPTS / "read_doc.py")]
    if name == "rg":
        try:
            search = Search.parse(args)
        except ValueError:
            return None
        if piped and not search.targets:
            return None
        retry = "cd " + shlex.quote(str(cwd)) + " && " + shlex.join(
            ["python3", "-B", str(SCRIPTS / "search_docs.py"), *args]
        )
        try:
            guarded = any(in_scope(path) for path in search.files(cwd, markdown_only=True))
        except OSError:
            # The retry reports enumeration errors without running a raw search.
            return retry
        return retry if guarded else None
    if name == "sed" and args[:1] == ["-n"]:
        args = args[1:]
        if args[:1] == ["-e"]:
            args = args[1:]
        if not args or not args[0].endswith("p"):
            return None
        try:
            line_range(args[0][:-1])
        except ValueError:
            return None
        reader.extend(["--lines", args[0][:-1]])
        args = args[1:]
    elif name != "cat":
        return None

    if args[:1] == ["--"]:
        args = args[1:]
    elif any(word.startswith("-") for word in args):
        return None
    if "-" in args or (name == "sed" and len(args) != 1):
        return None
    paths = [cwd / word for word in args]
    if any(in_scope(path) for path in paths):
        return shlex.join([*reader, "--", *map(str, paths)])
    return None


def protected_retry(command, cwd):
    for before, argv, after in commands(command):
        if argv[0] == "cd":
            args = argv[1:]
            if args[:1] == ["--"]:
                args = args[1:]
            if before == "|" or after != "&&" or len(args) != 1 or args[0] == "-":
                return None
            cwd = (cwd / args[0]).resolve()
            if not cwd.is_dir():
                return None
            continue
        retry = retry_for(argv, cwd, before == "|")
        if retry:
            return retry
    return None


def main():
    event = json.load(sys.stdin)
    if event.get("hook_event_name") != "PreToolUse" or event.get("tool_name") != "Bash":
        return
    command = event["tool_input"]["command"]
    retry = protected_retry(command, Path(event["cwd"]))
    if retry:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "Immutable SDD read. Retry this read separately with the protected command:\n" + retry
            ),
        }}))


if __name__ == "__main__":
    main()
