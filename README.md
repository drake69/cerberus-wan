# Cerberus WAN

A Home Assistant sensor that tells you **which provider is carrying your traffic
right now**.

Useful when you have more than one internet connection and want to know which
one is actually in use, rather than which one your router believes is primary.

## What it reports

| State | Meaning |
|---|---|
| The provider label you configured | the announcing network matched a row in your table |
| `Disconnected` | nothing gets out |
| `Unknown` | traffic gets out, but the announcing network is not in your table |

`Unknown` is a first class answer, not an error. It is the honest state when the
integration cannot tell, and it is deliberately distinct from `Disconnected`.

Both labels are configurable, so you can phrase them in your own language.

## How it works

Two DNS queries, once a minute:

1. `myip.opendns.com` asked of the OpenDNS resolvers returns the public address
   seen from the outside.
2. The Team Cymru DNS service returns the autonomous system number announcing
   that address.

The number is then looked up in your table.

**There is no third party API.** No key, no quota, no registration, no terms of
service, nothing that can be discontinued or put behind a paywall. If DNS works,
this works.

## Adding a provider you do not know yet

You do not need to research anything. Install the integration with an empty
table, look at the sensor attributes, and read `asn`. That is the number to add.

```
asn: 35612
public_address: 146.241.74.20
```

Then add one line in the options dialog:

```
35612 = Eolo
```

Accepted forms are `35612`, `AS35612` and `as 35612`. Lines that cannot be read
are skipped, so a typo costs one provider rather than a dialog that will not
close.

## Installation

### HACS

Add this repository as a custom repository of type "Integration", then install
Cerberus WAN and restart Home Assistant.

### Manual

Copy `custom_components/cerberus_wan` into your Home Assistant `config`
directory and restart.

Then add the integration from **Settings, Devices and services, Add
integration**.

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
```

The modules holding the logic, `dns_lookup.py` and `provider_table.py`, do not
import Home Assistant, so the test suite runs without it.

## Licence

MIT. See [LICENSE](LICENSE).
