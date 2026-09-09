"""The table that turns a network into the name its owner recognises."""

from __future__ import annotations

from dataclasses import dataclass, field

from .asn import Asn


@dataclass(frozen=True)
class ProviderTable:
    """The mapping from autonomous system number to provider label."""

    labels: dict[str, str] = field(default_factory=dict)

    @classmethod
    def parse(cls, text: str) -> ProviderTable:
        """Read the table as it is written in the dialog.

        One provider per line, as "35612 = Eolo". Blank lines and lines without
        a usable number are skipped rather than rejected, so a typo costs one
        missing provider instead of a dialog that refuses to close.

        Args:
            text: the raw content of the text area.

        Returns:
            The table the text describes.
        """
        labels: dict[str, str] = {}
        for line in text.splitlines():
            number, separator, label = line.partition("=")
            if not separator:
                continue
            asn = Asn.parse(number)
            if asn and label.strip():
                labels[asn.key] = label.strip()
        return cls(labels)

    @classmethod
    def from_mapping(cls, mapping: dict[str, str] | None) -> ProviderTable:
        """Rebuild the table from what a config entry stored.

        Args:
            mapping: the stored mapping, or None when nothing was stored.

        Returns:
            The table, empty when there was nothing to read.
        """
        return cls(dict(mapping or {}))

    def as_mapping(self) -> dict[str, str]:
        """Return the form a config entry can store.

        Returns:
            A copy of the mapping, so the entry and the table cannot drift.
        """
        return dict(self.labels)

    def knows(self, asn: Asn | None) -> bool:
        """Report whether this network already has a name.

        Args:
            asn: the network to look for, or None.

        Returns:
            True when the number is in the table.
        """
        return asn is not None and asn.key in self.labels

    def label_for(self, asn: Asn | None, unknown_label: str) -> str:
        """Turn an announcing network into the label to display.

        An unresolved number and an unmapped one deliberately give the same
        answer: in both cases the honest report is that the provider is not
        known.

        Args:
            asn: the announcing network, or None when it could not be resolved.
            unknown_label: what to answer when the network has no name here.

        Returns:
            The configured label, or the unknown label.
        """
        if asn is None:
            return unknown_label
        return self.labels.get(asn.key, unknown_label)

    @property
    def known_labels(self) -> list[str]:
        """Return the distinct labels this table can produce.

        Returns:
            The labels, in the order they were first written, without repeats.
        """
        return list(dict.fromkeys(self.labels.values()))

    def format(self) -> str:
        """Render the table back into editable text.

        Returns:
            One "ASN = label" line per provider, ordered by number so that 9
            comes before 35612 rather than after it.
        """
        rows = sorted(self.labels.items(), key=lambda item: int(item[0]))
        return "\n".join(f"{asn} = {label}" for asn, label in rows)

    def suggestion(self, asn: Asn | None) -> str:
        """Return the table text with the detected network offered for naming.

        The network in use is appended without a label, so naming the provider
        is the only thing left to do. A network already named is left alone,
        and so is the case where nothing could be detected: a failed lookup has
        to open the form, not break it.

        Args:
            asn: the announcing network, or None.

        Returns:
            The text to prefill the form with.
        """
        text = self.format()
        if asn is None or self.knows(asn):
            return text
        return f"{text}\n{asn} = ".lstrip("\n")
