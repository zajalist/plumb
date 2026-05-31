"""
cortex/masks/registry.py — provider registry + the Asset adapter (design spec §5).

A provider knows how to *compute one mask* for an asset. Registering a provider is the
only thing needed to add a new mask to the whole system — it then appears in the rail
catalog, is computable over HTTP, and (for server-side ones) over MCP. The ``Asset``
adapter is the uniform view a provider gets: the PAP, the convex parts (centroids +
geometry), the loadable mesh, and — for image-based providers — client renders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

import numpy as np

from . import store
from .model import Mask, role_for

ComputeFn = Callable[["Asset", Optional[list[bytes]]], dict]


@dataclass
class MaskProvider:
    key: str
    name: str
    source: str            # geometry | hf | gemini | mcp
    category: str          # material | physics | artistic | affordance | custom
    archetype: str         # categorical | scalar | vector | markers
    needs_images: bool
    available: Callable[[], bool]
    compute: ComputeFn

    @property
    def role(self) -> str:
        return role_for(self.archetype)


_REGISTRY: dict[str, MaskProvider] = {}


def register(provider: MaskProvider) -> MaskProvider:
    _REGISTRY[provider.key] = provider
    return provider


def get_provider(key: str) -> MaskProvider | None:
    return _REGISTRY.get(key)


def all_providers() -> list[MaskProvider]:
    return list(_REGISTRY.values())


def catalog() -> list[dict]:
    """Metadata the rail renders from — includes live ``available`` per provider."""
    out = []
    for p in _REGISTRY.values():
        try:
            avail = bool(p.available())
        except Exception:
            avail = False
        out.append({
            "key": p.key, "name": p.name, "source": p.source, "category": p.category,
            "archetype": p.archetype, "role": p.role, "needs_images": p.needs_images,
            "available": avail,
        })
    return out


class Asset:
    """Everything a provider may need, assembled once per compute."""

    def __init__(self, asset_id: str, pap: Any = None,
                 parts: Optional[list[dict]] = None, images: Optional[list[bytes]] = None,
                 mask_params: Optional[dict] = None):
        self.asset_id = asset_id
        self.pap = pap
        self.parts = parts if parts is not None else store.load_parts(asset_id)
        self.images = images or []
        # Optional per-compute knobs a provider may read (e.g. the text-mask `prompt`).
        self.mask_params = mask_params or {}
        self._mesh = None

    def mesh(self):
        """Loaded trimesh of the original mesh, or one assembled from convex parts."""
        if self._mesh is not None:
            return self._mesh
        import trimesh
        p = store.mesh_path(self.asset_id)
        if p is not None:
            try:
                loaded = trimesh.load(str(p), force="mesh")
                if isinstance(loaded, trimesh.Trimesh) and len(loaded.faces):
                    self._mesh = loaded
                    return self._mesh
            except Exception:
                pass
        # fall back to the union of convex parts
        meshes = []
        for pt in self.parts:
            v, f = pt.get("verts"), pt.get("tris")
            if v and f:
                meshes.append(trimesh.Trimesh(vertices=np.asarray(v, float),
                                              faces=np.asarray(f, int), process=False))
        self._mesh = trimesh.util.concatenate(meshes) if meshes else None
        return self._mesh

    def part_centroids(self) -> dict[str, np.ndarray]:
        return {pt["id"]: np.asarray(pt.get("centroid", [0, 0, 0]), float) for pt in self.parts}


def compute(asset: Asset, provider_key: str) -> Mask:
    """Run a provider for an asset, wrap the result in a Mask, and store it."""
    p = get_provider(provider_key)
    if p is None:
        raise KeyError(f"unknown mask provider: {provider_key}")
    if not p.available():
        raise RuntimeError(f"mask provider unavailable: {provider_key}")
    if p.needs_images and not asset.images:
        raise ValueError(f"provider {provider_key} needs rendered images")
    data = p.compute(asset, asset.images)
    confidence = data.pop("confidence", None) if isinstance(data, dict) else None
    mask = Mask(
        id=provider_key, asset_id=asset.asset_id, name=p.name, source=p.source,
        category=p.category, archetype=p.archetype, role=p.role, data=data,
        confidence=confidence, provider_key=provider_key,
    )
    return store.upsert(mask)
