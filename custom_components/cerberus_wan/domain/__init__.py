"""The domain model: what a provider is, and what changes about it.

Nothing under this package imports Home Assistant, and nothing imports a DNS
library. The model reaches the outside world only through the protocols in
ports.py, which the infrastructure package implements. That is what lets the
rules be tested without a running Home Assistant and without a network.
"""

from .asn import Asn
from .monitor import MonitorSettings, WanMonitor
from .observation import Observation
from .ports import AddressProbe, AsnRegistry, Clock
from .provider_table import ProviderTable

__all__ = [
    "AddressProbe",
    "Asn",
    "AsnRegistry",
    "Clock",
    "MonitorSettings",
    "Observation",
    "ProviderTable",
    "WanMonitor",
]
