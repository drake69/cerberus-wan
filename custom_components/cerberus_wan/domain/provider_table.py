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

        One provider per row, as "35612 = Eolo;". A row ends at the semicolon
        or at the end of the line, and either alone is enough: the semicolon is
        what keeps the table readable when the field hands back everything on
        one line, and the line break is what keeps it readable when it does
        not. Without the semicolon two providers written on one line would be
        read as one, and the number of the second would end up inside the name
        of the first.

        Blank rows and rows without a usable number are skipped rather than
        rejected, so a typo costs one missing provider instead of a dialog that
        refuses to close.

        Args:
            text: the raw content of the field.

        Returns:
            The table the text describes.
        """
        labels: dict[str, str] = {}
        for line in text.replace(";", "\n").splitlines():
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

        Every row is closed by a semicolon rather than merely separated by one.
        A closed row can be written after without a thought: whoever adds a
        provider at the end of the table cannot join it to the one before by
        forgetting a separator that was never there to forget.

        Returns:
            One closed "ASN = label;" row per provider, ordered by number so
            that 9 comes before 35612 rather than after it.
        """
        rows = sorted(self.labels.items(), key=lambda item: int(item[0]))
        return "\n".join(f"{asn} = {label};" for asn, label in rows)

    def suggestion(self, *seen: Asn | None) -> str:
        """Return the table text with the unnamed networks offered for naming.

        Every network given that has no name yet is appended without a label,
        in the order given, so naming the provider is the only thing left to
        do. The network in use is offered first because it is the one whoever
        opened the dialog is most likely looking for, but the networks seen
        while it was down are offered too: a failover that ended an hour ago
        would otherwise leave nothing to name, and the number that carried the
        traffic would have to be dug out of the sensor history by hand.

        The offered rows are closed like every other row, so the name goes
        between the equals sign and the semicolon.

        A network already named is left alone, and so is the case where
        nothing could be detected: a failed lookup has to open the form, not
        break it.

        Args:
            *seen: the networks to offer, most relevant first. Entries that
                are None are ignored rather than rejected.

        Returns:
            The text to prefill the form with.
        """
        rows = [self.format()]
        offered: set[str] = set()
        for asn in seen:
            if asn is None or self.knows(asn) or asn.key in offered:
                continue
            offered.add(asn.key)
            rows.append(f"{asn} = ;")
        return "\n".join(row for row in rows if row)
