"""Load the Home Assistant free modules without importing the package.

Importing custom_components.cerberus_wan would execute the package
__init__, which imports Home Assistant. The modules under test deliberately
do not depend on it, so they are loaded straight from their file instead.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

COMPONENT_DIR = Path(__file__).parents[1] / "custom_components" / "cerberus_wan"


def load_pure_module(name: str):
    """Import one module by path, bypassing the package __init__.

    Args:
        name: the module file name, without the extension.

    Returns:
        The imported module object.
    """
    spec = importlib.util.spec_from_file_location(name, COMPONENT_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def provider_table():
    """Return the provider table module.

    Returns:
        The loaded provider_table module.
    """
    return load_pure_module("provider_table")
