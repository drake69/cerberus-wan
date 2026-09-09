"""DNS lookups: the public address and the autonomous system that announces it.

This module deliberately does not import Home Assistant: it is pure logic that
runs and is tested on its own. It relies on DNS only, so there is no third
party service with a key, a quota or a registration to depend upon.
"""

from __future__ import annotations

import dns.resolver

# myip.opendns.com resolves to the public address of whoever asks, but only
# when the question reaches the OpenDNS resolvers, so they are named here
# explicitly instead of relying on whatever resolver the host is configured
# with.
OPENDNS_RESOLVERS = ("208.67.222.222", "208.67.220.220")
CYMRU_ORIGIN_ZONE = "origin.asn.cymru.com"

DEFAULT_TIMEOUT = 3.0


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


def resolve_public_address(timeout: float = DEFAULT_TIMEOUT) -> str | None:
    """Return the public IPv4 address seen from the outside.

    Args:
        timeout: seconds allowed for the query.

    Returns:
        The dotted quad address, or None when nothing gets out. A None here
        means "disconnected", not "lookup failed": if the query cannot leave
        the network there is no traffic either.
    """
    try:
        answer = _build_resolver(OPENDNS_RESOLVERS, timeout).resolve(
            "myip.opendns.com", "A"
        )
        return answer[0].to_text()
    except Exception:  # noqa: BLE001 - any DNS failure means no answer
        return None


def resolve_announcing_asn(address: str, timeout: float = DEFAULT_TIMEOUT) -> int | None:
    """Return the autonomous system number that announces the given address.

    Queries the Team Cymru DNS service, which answers with a TXT record shaped
    as "ASN | prefix | country | registry | date".

    Args:
        address: the IPv4 address to look up.
        timeout: seconds allowed for the query.

    Returns:
        The autonomous system number, or None when it cannot be determined.
    """
    try:
        reversed_octets = ".".join(reversed(address.split(".")))
        query_name = f"{reversed_octets}.{CYMRU_ORIGIN_ZONE}"
        record = _build_resolver(None, timeout).resolve(query_name, "TXT")
        return int(record[0].to_text().strip('"').split("|")[0].strip())
    except Exception:  # noqa: BLE001 - an unresolved ASN is a known outcome
        return None
