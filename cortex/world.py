"""
cortex/world.py — the world model (Task 1).

Pure state: an in-memory scene graph mapping ``node_id -> WorldNode`` where each
node bundles a baked ``PAP``, its ``Transform``, and an optional ``parent`` id.
NO physics lives here — gates/repair consume this state, they don't mutate it.

``snapshot_hash()`` is the optimistic-concurrency guard for ``commit``: a stable
sha256 over the sorted node ids together with their *rounded* transforms and the
``pap.asset_id`` + ``pap.bake_version``. It is invariant to insertion order and to
sub-rounding transform jitter, and it changes whenever a node is added, removed,
re-baked, or moved past the rounding tolerance.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Optional

from contracts import PAP, Transform

# Decimal places transforms are rounded to before hashing. 1e-6 m = 1 micron,
# far below any placement tolerance we gate on, so sub-tolerance numerical jitter
# never perturbs the snapshot hash.
_HASH_ROUND = 6


@dataclass
class WorldNode:
    """One placed asset: its baked profile, world transform, and optional parent."""

    pap: PAP
    transform: Transform
    parent: Optional[str] = None


class WorldModel:
    """In-memory scene graph of ``{node_id: WorldNode}``. Pure state, no physics."""

    def __init__(self) -> None:
        self._nodes: dict[str, WorldNode] = {}

    def add(
        self,
        node_id: str,
        pap: PAP,
        transform: Transform,
        parent: Optional[str] = None,
    ) -> WorldNode:
        """Insert a new node. Raises ``KeyError`` if ``node_id`` already exists."""
        if node_id in self._nodes:
            raise KeyError(f"node_id already present: {node_id!r}")
        node = WorldNode(pap=pap, transform=transform, parent=parent)
        self._nodes[node_id] = node
        return node

    def get(self, node_id: str) -> WorldNode:
        """Return the node. Raises ``KeyError`` if it is not present."""
        return self._nodes[node_id]

    def update_transform(self, node_id: str, transform: Transform) -> WorldNode:
        """Replace a node's transform. Raises ``KeyError`` if it is not present."""
        node = self._nodes[node_id]
        node.transform = transform
        return node

    def remove(self, node_id: str) -> None:
        """Delete a node. Raises ``KeyError`` if it is not present."""
        del self._nodes[node_id]

    def nodes(self) -> list[str]:
        """Sorted list of node ids currently in the world (stable ordering)."""
        return sorted(self._nodes)

    def snapshot_hash(self) -> str:
        """Stable sha256 hex digest of the world state (the commit guard).

        Deterministic over: sorted node ids, each node's rounded transform
        (pos/quat/scale) and its ``pap.asset_id`` + ``pap.bake_version``.
        Independent of insertion order and of sub-rounding transform jitter.
        """
        payload = [
            [
                node_id,
                self._nodes[node_id].pap.asset_id,
                self._nodes[node_id].pap.bake_version,
                _round(self._nodes[node_id].transform.pos),
                _round(self._nodes[node_id].transform.quat),
                _round(self._nodes[node_id].transform.scale),
            ]
            for node_id in sorted(self._nodes)
        ]
        blob = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _round(vec: list[float]) -> list[float]:
    """Round a vector to the hash tolerance; ``+0.0`` collapses any ``-0.0``."""
    return [round(float(x), _HASH_ROUND) + 0.0 for x in vec]
