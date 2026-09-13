"""Fail when a file contains a character that is not on the keyboard.

Em dash, en dash, curly quotes, the one character ellipsis and the non
breaking space all replace an ASCII character that already exists, and each
one breaks grep, diff and sed for whoever comes after. They arrive by
autocorrect or by paste, never by typing, so the cheapest place to stop them
is before the commit.

Run over the files given as arguments. Prints one line per offence and exits
non zero if there was any.
"""

from __future__ import annotations

import sys
import unicodedata

FORBIDDEN = {
    "—": "em dash, use a colon, a comma, a full stop or ' - '",
    "–": "en dash, use '-' or 'from X to Y'",
    "“": "curly quote, use '\"'",
    "”": "curly quote, use '\"'",
    "‘": 'curly quote, use "\'"',
    "’": 'curly quote, use "\'"',
    "…": "ellipsis, use '...'",
    " ": "non breaking space, use a normal space",
}


def offences(path: str) -> list[str]:
    """Report every forbidden character in one file.

    Args:
        path: the file to read. Anything undecodable is skipped, on the
            grounds that a binary file has no typography.

    Returns:
        One message per offending line, empty when the file is clean.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.readlines()
    except (UnicodeDecodeError, OSError):
        return []

    found = []
    for number, line in enumerate(lines, start=1):
        for char, advice in FORBIDDEN.items():
            column = line.find(char)
            if column >= 0:
                name = unicodedata.name(char, "unnamed")
                found.append(f"{path}:{number}:{column + 1}: {name} ({advice})")
    return found


def main(paths: list[str]) -> int:
    """Check every path and report.

    Args:
        paths: the files to check.

    Returns:
        1 when at least one offence was found, 0 otherwise.
    """
    found = [message for path in paths for message in offences(path)]
    for message in found:
        print(message)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
