"""
cortex/masks — the extensible mask system (design spec).

Core (model, store, registry) is import-cheap and provider-free. Registering the starter
catalog is an explicit ``import cortex.masks.providers`` (the studio + cortex servers do
this on startup) so the core stays testable in isolation and free of trimesh/network deps.
"""

from __future__ import annotations

from typing import Optional

from . import registry, store
from .model import Mask, derive_legend, role_for
from .registry import Asset, MaskProvider, all_providers, catalog, compute, get_provider, register

__all__ = [
    "Mask", "role_for", "derive_legend",
    "store", "registry",
    "Asset", "MaskProvider", "catalog", "compute", "get_provider", "all_providers", "register",
    "load_providers", "compute_for",
]


def load_providers() -> None:
    """Import the provider package so every starter provider self-registers."""
    from . import providers as _providers  # noqa: F401


def compute_for(asset_id: str, provider_key: str, pap=None,
                parts: Optional[list[dict]] = None, images: Optional[list[bytes]] = None) -> Mask:
    """Convenience used by the servers: build an Asset and run a provider."""
    load_providers()
    return compute(Asset(asset_id, pap=pap, parts=parts, images=images), provider_key)
