# Domain model

The domain of Cerberus WAN, written down: the words, the objects, and the rules
that have to hold. The code under `custom_components/cerberus_wan/domain/` is
the implementation of this document, not a second source of truth. When the two
disagree, one of them is a bug.

## The question the domain answers

*Which provider is carrying the traffic right now, and how has that changed over
the last day?*

Everything below exists to answer that without asking Home Assistant, without a
cloud account, and without trusting anything the integration cannot see for
itself: the public address of the connection, and the registry that says which
network announces it.

## Ubiquitous language

The same words in this document, in the code, in the entity names and in the
user interface. No silent translation between layers.

| Term | Meaning | Do not call it |
|---|---|---|
| Provider | The connection actually carrying traffic, as its owner thinks of it: "Fibre", "4G backup" | ISP, carrier, WAN |
| Label | The name of a provider. It **is** the provider's identity in this model | Name, description |
| ASN | Autonomous system number: the network announcing the public address | AS, network id |
| Provider table | The mapping the user types, from ASN to label | Config, mapping, dictionary |
| Observation | One complete reading of the network at one moment | Sample, poll, state |
| Change | A transition from one label to another | Failover, flap, switch |
| Window | The trailing period the statistics cover, one day | History, buffer |
| Timeline | How long each label carried the traffic inside the window | Log, history |
| Share | The fraction of covered time one label carried | Uptime, percentage |
| Covered time | The part of the window the integration actually observed | Elapsed time |
| Unknown label | What an ASN outside the table is called | Default, fallback |
| Disconnected label | What nothing-gets-out is called | Offline, error |

## The decision the whole model rests on

**A provider is identified by its label, not by its address and not by its ASN.**

Everything else follows:

- A provider that renews its public address has not changed. The address is
  evidence, not identity.
- Two ASNs mapped to the same label are one provider. An operator announcing
  from several networks is still one line in the bill, so it is one provider
  here.
- A change is a label transition. This is what makes the change count worth
  looking at: it counts switchovers, not DHCP leases.

## Value objects

Immutable, compared by value, no identity of their own.

| Value object | Composition | Constraints |
|---|---|---|
| `Asn` | `number: int` | Parsed from "35612", "AS35612", "as 35612", which are one number written by three people. Unparseable text yields nothing, never a wrong number |
| `Observation` | `moment`, `address`, `asn`, `label` | Complete on its own: it carries the label it resolved to, so it stays meaningful after the table changes. `address is None` means **disconnected**, never "the lookup failed" |
| `ProviderTable` | `labels: dict[str, str]` | Keyed by the canonical form of an ASN, so the three spellings above collide onto one entry |
| `CacheEntry` | `asn`, `checked_at` | Knows whether it is still fresh; it never decides *what* fresh means, the caller passes the moment |
| `MonitorSettings` | `table`, `disconnected_label`, `unknown_label` | The complete set of what the user configured. The monitor holds nothing else from the outside |

## Aggregate

### `WanMonitor` - the root, and the only way in

Everything that has to stay consistent lives behind it: no other object may be
mutated from outside.

- **Identity**: one monitor per config entry, one config entry per Home
  Assistant instance. There is one connection to observe.
- **Contains**: the current `Observation`, the `AsnCache`, the `ChangeWindow`,
  the `LabelTimeline`, and the `MonitorSettings` it was configured with.
- **Invariants**:
  - The first observation is never a change. It is the beginning of the record,
    and counting it would report a switchover that never happened.
  - A change is recorded only when the label moves. Same label, new address:
    nothing recorded.
  - No address resolved implies the disconnected label, whatever the cache and
    the table say.
  - An ASN absent from the table implies the unknown label. It is never left
    blank, and never shown as a bare number.
  - Window and timeline never hold anything older than the window. Expiry is
    driven by the clock passed in, never by wall time read directly.
  - Share is a fraction of **covered** time, not of the window. An integration
    started twenty minutes ago reports shares of those twenty minutes, and says
    so through covered time, instead of pretending to know the other twenty-three
    hours.

### `AsnCache` - what is already known

Inside the aggregate, but with a rule of its own worth stating: an entry answers
only while it is fresh. Beyond that it is not deleted eagerly, it simply stops
answering, and expiry removes it later. Nothing outside the aggregate is allowed
to read a stale entry and decide for itself whether to trust it.

### `ChangeWindow` and `LabelTimeline` - the last day

Two views of the same day, kept apart because they answer different questions.
The window counts *how often* the provider changed; the timeline records *how
long* each provider carried. The timeline collapses consecutive identical
labels, so a provider that stays up is one stretch and not a thousand samples.

Both survive a restart: they are persisted and adopted back, because a change
count that resets every time Home Assistant restarts would measure restarts.

## Ports

The only places the domain touches anything it does not own. Each is
implemented twice: once against the real world in `infrastructure/`, once
against a dictionary in the tests. This is what keeps the layer testable
without booting anything.

| Port | Question it answers |
|---|---|
| `AddressProbe` | What is the public address of this network? |
| `AsnRegistry` | Which network announces this address? |
| `CacheStore` | Keep this table across a restart |
| `ChangeListener` | The provider changed, do whatever you do |
| `Clock` | What time is it? |

`ChangeListener` is the outbound one, and the reason the domain never imports
Home Assistant: firing an event and running an automation is somebody else's
job. The domain says a change happened.

## Relationships

- One `WanMonitor` holds exactly one current `Observation`, or none before the
  first reading.
- One `WanMonitor` holds one `ProviderTable`, replaced wholesale when the user
  edits the options. It is never mutated in place.
- One `AsnCache` holds many `CacheEntry`, keyed by address.
- One `LabelTimeline` holds many stretches, each pointing at a label by value.
  A label is a string, not a reference: the timeline stays readable after the
  table stops mapping that ASN.

## Bounded context

One context. The integration does one thing, and the Home Assistant adapters
are a delivery mechanism, not a second model.
