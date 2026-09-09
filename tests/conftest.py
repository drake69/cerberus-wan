"""Import the domain as the standalone package it really is.

The domain deliberately does not depend on Home Assistant, but reaching it as
custom_components.cerberus_wan.domain would execute the package __init__, which
does. Putting the component directory on the path imports it on its own, which
is the whole point of keeping the model free of the framework.
"""

from __future__ import annotations

import sys
from pathlib import Path

COMPONENT_DIR = Path(__file__).parents[1] / "custom_components" / "cerberus_wan"
sys.path.insert(0, str(COMPONENT_DIR))
