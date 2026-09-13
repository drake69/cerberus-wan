"""The layer boundaries, checked by a test instead of by discipline.

The whole point of keeping `domain/` free of Home Assistant is that the rules
about which provider is carrying traffic can be read, and tested, without
booting anything. That property is easy to lose: one convenient import of
`homeassistant.util.dt` inside a domain module and the layer is gone, with
nothing failing to announce it. So it fails here.

The direction of the dependencies is the whole rule:

    adapters (sensor, config_flow, announcer, assembly)
        -> infrastructure -> domain
        -> domain

Nothing ever points back up.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "cerberus_wan"

ADAPTER_MODULES = {"announcer", "assembly", "config_flow", "sensor"}


def _modules(layer: str) -> list[Path]:
    return sorted((COMPONENT / layer).rglob("*.py"))


def _imported_names(path: Path) -> set[str]:
    """Every module a file imports, absolute names and relative ones alike.

    A relative import is reported with as many leading dots as it was written
    with, so `from ..infrastructure.dns import X` comes back as
    `..infrastructure.dns` and can be matched without guessing the package.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add("." * node.level + (node.module or ""))
    return names


@pytest.mark.parametrize("path", _modules("domain"), ids=lambda p: p.name)
def test_the_domain_never_imports_home_assistant(path: Path) -> None:
    offenders = {n for n in _imported_names(path) if n.split(".")[0] == "homeassistant"}
    assert not offenders, (
        f"{path.name} imports {sorted(offenders)}. The domain layer has to stay "
        "runnable without Home Assistant."
    )


@pytest.mark.parametrize("path", _modules("domain"), ids=lambda p: p.name)
def test_the_domain_never_reaches_outwards(path: Path) -> None:
    offenders = {
        name
        for name in _imported_names(path)
        if name.lstrip(".").split(".")[0] in {"infrastructure", *ADAPTER_MODULES}
    }
    assert not offenders, (
        f"{path.name} imports {sorted(offenders)}. The domain defines the ports; "
        "the outer layers implement them, never the other way round."
    )


@pytest.mark.parametrize("path", _modules("infrastructure"), ids=lambda p: p.name)
def test_infrastructure_never_imports_home_assistant(path: Path) -> None:
    offenders = {n for n in _imported_names(path) if n.split(".")[0] == "homeassistant"}
    assert not offenders, (
        f"{path.name} imports {sorted(offenders)}. Home Assistant belongs to the "
        "adapters; the infrastructure layer talks to DNS, the clock and storage."
    )


def test_the_layers_actually_exist() -> None:
    """Guard against the parametrised tests passing because they found nothing."""
    assert _modules("domain"), "no domain modules found, the checks above are empty"
    assert _modules("infrastructure"), "no infrastructure modules found"
