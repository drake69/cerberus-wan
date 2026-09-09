"""The two DNS lookups, behind the probe and registry protocols.

Only DNS is used, so there is no third party service with a key, a quota or a
registration to depend upon. The queries block, so each adapter is given a way
to run them off the event loop rather than reaching for one itself: that is
what keeps this module free of Home Assistant.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import dns.resolver

from ..domain.asn import Asn

# myip.opendns.com resolves to the public address of whoever asks, but only
# when the question reaches the OpenDNS resolvers, so they are named here
# explicitly instead of relying on whatever resolver the host is configured
# with.
OPENDNS_RESOLVERS = ("208.67.222.222", "208.67.220.220")
CYMRU_ORIGIN_ZONE = "origin.asn.cymru.com"

DEFAULT_TIMEOUT = 3.0

# A callable that runs a blocking function off the event loop and awaits it,
# which is what hass.async_add_executor_job is.
RunBlocking = Callable[..., Awaitable[Any]]


def _build_resolver(nameservers: tuple[str, ...] | None, timeout: float):
    """Return a resolver bound to the given nameservers, or the system ones.

    Args:
        nameservers: explicit servers to query, or None to use the host
            configuration.
        timeout: seconds allowed for a single query and for the whole attempt.

    Returns:
        A configured dns.resolver.Resolver instance.
    """
    resolver = dns.resolver.Resolver(configure=nameservers is None)
    if nameservers:
        resolver.nameservers = list(nameservers)
    resolver.timeout = resolver.lifetime = timeout
    return resolver


class DnsAddressProbe:
    """Asks the OpenDNS resolvers for the address the outside world sees."""

    def __init__(
        self, run_blocking: RunBlocking, timeout: float = DEFAULT_TIMEOUT
    ) -> None:
        """Bind the probe to an executor and a timeout.

        Args:
            run_blocking: how to run a blocking call off the event loop.
            timeout: seconds allowed for the query.
        """
        self._run = run_blocking
        self._timeout = timeout

    async def public_address(self) -> str | None:
        """Return the public address, or None when nothing gets out.

        Returns:
            The dotted quad address, or None.
        """
        return await self._run(self._lookup)

    def _lookup(self) -> str | None:
        """Run the query, on the executor thread.

        Returns:
            The address, or None on any DNS failure. A failure here means
            disconnected, not "the lookup broke": if the query cannot leave
            the network there is no traffic either.
        """
        try:
            answer = _build_resolver(OPENDNS_RESOLVERS, self._timeout).resolve(
                "myip.opendns.com", "A"
            )
            return answer[0].to_text()
        except Exception:  # noqa: BLE001 - any DNS failure means no answer
            return None


class CymruAsnRegistry:
    """Asks the Team Cymru DNS service who announces an address."""

    def __init__(
        self, run_blocking: RunBlocking, timeout: float = DEFAULT_TIMEOUT
    ) -> None:
        """Bind the registry to an executor and a timeout.

        Args:
            run_blocking: how to run a blocking call off the event loop.
            timeout: seconds allowed for the query.
        """
        self._run = run_blocking
        self._timeout = timeout

    async def announcing_asn(self, address: str) -> Asn | None:
        """Return the network announcing the address, or None.

        Args:
            address: the public address to look up.

        Returns:
            The autonomous system number, or None.
        """
        return await self._run(self._lookup, address)

    def _lookup(self, address: str) -> Asn | None:
        """Run the query, on the executor thread.

        The service answers with a TXT record shaped as
        "ASN | prefix | country | registry | date".

        Args:
            address: the public address to look up.

        Returns:
            The number, or None when it cannot be determined.
        """
        try:
            reversed_octets = ".".join(reversed(address.split(".")))
            query_name = f"{reversed_octets}.{CYMRU_ORIGIN_ZONE}"
            record = _build_resolver(None, self._timeout).resolve(query_name, "TXT")
            return Asn(int(record[0].to_text().strip('"').split("|")[0].strip()))
        except Exception:  # noqa: BLE001 - an unresolved ASN is a known outcome
            return None
