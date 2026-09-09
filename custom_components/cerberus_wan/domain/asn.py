"""The autonomous system number: the network that announces an address."""

from __future__ import annotations

from dataclasses import dataclass

# Hurricane Electric renders a number as the name of the organisation behind
# it. The link is offered to whoever reads the dialog, never fetched by this
# integration: if the site disappears the only loss is a convenience. The rule
# about depending on no third party service is about runtime, not hyperlinks.
DIRECTORY_URL = "https://bgp.he.net/AS{number}"


@dataclass(frozen=True, slots=True)
class Asn:
    """One autonomous system number, compared and rendered by value."""

    number: int

    @classmethod
    def parse(cls, raw: str) -> Asn | None:
        """Read the forms people actually type.

        Accepts "35612", "AS35612" and "as 35612", which are the same number
        written by three different people.

        Args:
            raw: the text to read.

        Returns:
            The number, or None when the text does not hold one.
        """
        text = raw.strip()
        if text[:2].lower() == "as":
            text = text[2:].strip()
        return cls(int(text)) if text.isdigit() else None

    @property
    def key(self) -> str:
        """Return the form used to key the provider table.

        Returns:
            The number as text, which is how it survives a config entry.
        """
        return str(self.number)

    @property
    def directory_url(self) -> str:
        """Return where a human can read who this network belongs to.

        Returns:
            The directory link for this number.
        """
        return DIRECTORY_URL.format(number=self.number)

    def __str__(self) -> str:
        """Return the number as text.

        Returns:
            The number, without the AS prefix.
        """
        return self.key
