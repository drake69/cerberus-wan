"""Translation between the edited provider text and the stored mapping.

Kept apart from the configuration dialog, and free of Home Assistant imports,
so the parsing rules can be tested on their own.
"""

from __future__ import annotations


def _normalise_asn(raw: str) -> str | None:
    """Reduce an autonomous system number to its digits.

    Accepts the forms people actually type: "35612", "AS35612", "as 35612".

    Args:
        raw: the text written on the left of the separator.

    Returns:
        The digits alone, or None when the text is not a number.
    """
    digits = raw.strip().removeprefix("AS").removeprefix("as").strip()
    return digits if digits.isdigit() else None


def parse_provider_table(text: str) -> dict[str, str]:
    """Turn the edited text into a mapping from ASN to provider label.

    One provider per line, written as "35612 = Eolo". Blank lines and lines
    without a usable number are skipped rather than rejected, so a typo costs
    one missing provider instead of a dialog that refuses to close.

    Args:
        text: the raw content of the text area.

    Returns:
        A mapping keyed by the autonomous system number, as a string.
    """
    table: dict[str, str] = {}
    for line in text.splitlines():
        number, separator, label = line.partition("=")
        if not separator:
            continue
        asn = _normalise_asn(number)
        if asn and label.strip():
            table[asn] = label.strip()
    return table


def resolve_label(
    providers: dict[str, str],
    asn: int | None,
    unknown_label: str,
) -> str:
    """Turn an announcing network into the label to display.

    Args:
        providers: the mapping from autonomous system number to label.
        asn: the announcing number, or None when it could not be resolved.
        unknown_label: what to answer when the number is not in the mapping.

    Returns:
        The configured label, or the unknown label. An unresolved number and an
        unmapped one deliberately give the same answer: in both cases the
        honest report is that the provider is not known.
    """
    if asn is None:
        return unknown_label
    return providers.get(str(asn), unknown_label)


def suggest_table(existing: dict[str, str], asn: int | None) -> str:
    """Return the table text with the detected network offered for naming.

    The network currently in use is appended without a label, so naming the
    provider is the only thing left to do. A network already mapped is left
    alone, and so is the case where nothing could be detected.

    Args:
        existing: the mapping already stored.
        asn: the announcing autonomous system number, or None.

    Returns:
        The text to prefill the form with.
    """
    text = format_provider_table(existing)
    if asn is None or str(asn) in existing:
        return text
    return f"{text}\n{asn} = ".lstrip("\n")


def format_provider_table(table: dict[str, str]) -> str:
    """Render the stored mapping back into editable text.

    Args:
        table: the stored mapping from ASN to provider label.

    Returns:
        One "ASN = label" line per provider, ordered by number.
    """
    return "\n".join(
        f"{asn} = {label}" for asn, label in sorted(table.items(), key=lambda kv: int(kv[0]))
    )
