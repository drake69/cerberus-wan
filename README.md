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

## The entities

| Entity | What it holds |
|---|---|
| the provider sensor | the label of the network in use, with the address and the ASN as attributes |
| one share sensor per label | 100 while that provider is the active one, 0 otherwise, so its long term mean is the percentage of time spent on it |
| `Changes in 24 hours` | how many times the provider changed in the last 24 hours, as a moving window |
| `Changes per hour` | the same window divided by its width: the moving average of switchovers per hour |

The two statistics are recomputed the moment a change happens, and swept once
an hour so that a change leaves the window on time. They are written only when
the number actually moves, so a quiet line costs no state writes at all. The
window is kept across a restart: a statistic that resets whenever Home
Assistant does is a statistic that lies.

Losing the line counts as a change, because it is one.

## Reacting to a change

Two ways, and you can use either or both.

**Pick an automation or a script in the dialog.** The field accepts both, and
several of each. An automation is triggered with its own conditions still in
force, so one that says "only at night" still means it. A script receives what
changed as variables.

**Or trigger on the event.** Every switchover fires
`cerberus_wan_provider_changed`, whether or not anything was hooked to it:

```yaml
trigger:
  - platform: event
    event_type: cerberus_wan_provider_changed
action:
  - service: notify.mobile_app
    data:
      message: "Now on {{ trigger.event.data.label }}, was {{ trigger.event.data.previous_label }}"
```

The event carries `previous_label`, `label`, `public_address`, `asn`,
`changed_at` and `entry_id`. Use it when the automation needs to know where the
traffic went; use the field when it just needs to run.

## How it works

Two DNS queries, asked at very different rates:

1. Every **15 seconds**, `myip.opendns.com` asked of the OpenDNS resolvers
   returns the public address seen from the outside. This is the question that
   detects a switchover, so it is the one asked often.
2. **Only when that address is one it has not seen before**, the Team Cymru DNS
   service is asked which autonomous system announces it.

The answer to the second question is kept in a local table, alongside the date
it was obtained, and reused for **30 days**. An address does not change owner,
so asking again on every cycle would be four identical questions a minute for
an answer that holds for months. A lookup that failed is retried within the
hour instead, so a moment of DNS trouble does not become thirty days of an
unknown provider.

The table lives in the Home Assistant storage directory and survives a restart.
Addresses not seen for 60 days are dropped from it.

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

### Layout

```
domain/          the model: Asn, ProviderTable, Observation, WanMonitor, ports
infrastructure/  the adapters: DNS lookups, the system clock
assembly.py      the composition root: entry in, wired monitor out
sensor.py        Home Assistant entities, thin
config_flow.py   Home Assistant dialogs, thin
```

Nothing under `domain/` imports Home Assistant or a DNS library: it reaches the
outside world only through the protocols in `domain/ports.py`. That is why the
test suite runs the whole model against fakes, with no network and no Home
Assistant installed.

## Licence

MIT. See [LICENSE](LICENSE).
