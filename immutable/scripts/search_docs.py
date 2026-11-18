#!/usr/bin/env python3
"""Search active text with ripgrep and show full withholding notices for obsolete inputs."""
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from read_doc import document_scope, read_document


@dataclass
class Search:
    flags: list
    discovery: list
    pattern: str
    targets: list

    @classmethod
    def parse(cls, args):
        """Accept only options whose operand and discovery semantics we know."""
        words = iter(args)
        flags, discovery, operands = [], [], []
        pattern = None
        for word in words:
            if word == "--":
                operands.extend(words)
                break
            if word in ("-g", "--glob", "-e"):
                value = next(words, None)
                if value is None:
                    raise ValueError(f"{word} needs an argument")
                if word == "-e":
                    if pattern is not None:
                        raise ValueError("use a single search expression")
                    pattern = value
                else:
                    discovery.extend(["-g", value])
            elif word.startswith("--glob="):
                discovery.extend(["-g", word.partition("=")[2]])
            elif word == "--hidden":
                discovery.append(word)
            elif word in ("--line-number", "--ignore-case", "--smart-case",
                          "--fixed-strings", "--word-regexp"):
                flags.append(word)
            elif word.startswith("-"):
                if not word[1:] or not set(word[1:]) <= set("niSFw"):
                    raise ValueError(f"unsupported rg argument {word!r}")
                flags.append(word)
            else:
                operands.append(word)
        if pattern is None:
            if not operands:
                raise ValueError("missing search pattern")
            pattern = operands.pop(0)
        if "-" in operands:
            raise ValueError("stdin is outside the file search")
        return cls(flags, discovery, pattern, operands or ["."])

    def files(self, cwd):
        for target in self.targets:
            path = cwd / target
            if not path.is_dir():
                yield path
                continue
            # Only enumerate filenames. Never run the intercepted content search
            # or apply user-configured rg options while deciding whether to deny.
            result = subprocess.run(
                ["rg", "--no-config", "--files", "-0", *self.discovery, "--", target],
                cwd=cwd, stdout=subprocess.PIPE,
            )
            if result.returncode not in (0, 1):
                raise OSError(f"could not enumerate search directory {target!r}")
            for name in result.stdout.split(b"\0"):
                if name:
                    yield cwd / os.fsdecode(name)


def main(args):
    search = Search.parse(args)
    cwd = Path.cwd()
    status = 1
    for path in search.files(cwd):
        source, root = document_scope(path)
        command = ["rg", "--no-config", *search.flags, "-e", search.pattern]
        if root is None:
            result = subprocess.run([*command, "--with-filename", "--", str(path)], stdin=subprocess.DEVNULL)
        else:
            data, withheld = read_document(source, root)
            if withheld:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
                status = 0
                continue
            result = subprocess.run([*command, "--", "-"], input=data, stdout=subprocess.PIPE)
            for line in result.stdout.splitlines(keepends=True):
                sys.stdout.buffer.write(os.fsencode(path) + b":" + line)
            sys.stdout.buffer.flush()
        if result.returncode not in (0, 1):
            return result.returncode
        status = min(status, result.returncode)
    return status


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (OSError, ValueError, ImportError) as exc:
        sys.exit(str(exc))
