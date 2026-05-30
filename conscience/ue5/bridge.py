"""
The UE5 Remote Control HTTP bridge (Task B5) — the photoreal finale, commit-once.

UE5 exposes a Remote Control HTTP API; this is an `httpx`-based client for it. No
C++ and no running Unreal is needed to develop or test against it: the shape of the
JSON is all the bridge depends on, so a `pytest-httpserver` mock stands in for the
engine (see `tests/test_bridge.py`).

The bridge is a thin transport that delegates ALL coordinate maths to the B1
adapter (`conscience.ue5.adapter`) — it is the only module that knows UE5 is
left-handed, Z-up, centimetres. The bridge never does its own `x100`/negate-X; if
it did, the §17.5 golden round-trip would no longer protect it.

Two operations, mirroring spec §10.2 step 5 and §17.6 point 5:

  * `sync_scene(selector)` — GET the tagged actors, convert each UE5 transform to
    canonical, return `[(actor_id, Transform_canonical), ...]`.
  * `commit(diff, expected_hash)` — the finale. UE5 runs **commit-once**, not a live
    two-way loop (spec §15 demo-safety): one validated PUT. It is guarded by an
    **optimistic-concurrency hash** — before PUTting, it re-reads the scene, hashes
    it, and REFUSES (raises `ConcurrencyError`, PUTs nothing) if the world changed
    under us since `expected_hash` was taken.

`snapshot_hash(actors)` is the stable fingerprint the concurrency guard compares.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import httpx

from conscience.ue5 import adapter
from contracts import Diff, Transform

# Remote Control routes. Real UE5 uses richer paths (e.g.
# /remote/object/property with a preset… body); the demo bridge keeps a single
# stable read route and a single write route, which is all commit-once needs.
SYNC_PATH = "/remote/actors"
COMMIT_PATH = "/remote/object/property"

_DEFAULT_TIMEOUT = 10.0


class ConcurrencyError(RuntimeError):
    """
    Raised by `commit` when the live UE5 scene no longer matches `expected_hash`.

    Optimistic concurrency: the conscience validated against a snapshot of the
    world; if UE5 changed under us between validation and commit, the validated
    transform may no longer be safe, so we refuse to PUT rather than clobber.
    """


@dataclass(frozen=True)
class SyncedActor:
    """One actor as read from UE5 and converted to canonical space."""
    actor_id: str
    transform: Transform


class UE5Bridge:
    """
    `httpx` client for UE5's Remote Control API — coordinate-correct, commit-once.

    All conversions go through the B1 adapter; the bridge only moves JSON. Inject a
    `client` (e.g. a stub) for tests, or let it build a default `httpx.Client`
    against `base_url`.
    """

    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.Client | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(base_url=self.base_url, timeout=timeout)

    # ----------------------------------------------------------------------- #
    # Read: UE5 -> canonical
    # ----------------------------------------------------------------------- #
    def sync_scene(self, selector: str) -> list[tuple[str, Transform]]:
        """
        GET the actors matching `selector` and return them in CANONICAL space.

        Returns `[(actor_id, Transform), ...]`. Every transform has been routed
        through `adapter.ue5_to_canon_*` (x0.01 + negate-X mirror), so the rest of
        the conscience never sees a centimetre or a left-handed axis.
        """
        resp = self._client.get(SYNC_PATH, params={"selector": selector})
        resp.raise_for_status()
        actors = self._actors_from_json(resp.json())
        return [(a.actor_id, a.transform) for a in actors]

    @staticmethod
    def _actors_from_json(payload: dict) -> list[SyncedActor]:
        """Parse a Remote Control 'tagged actors' payload into canonical actors."""
        out: list[SyncedActor] = []
        for raw in payload.get("actors", []):
            loc = raw["location"]
            rot = raw.get("rotation", {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0})
            ue5_pos = [float(loc["x"]), float(loc["y"]), float(loc["z"])]
            ue5_quat = [float(rot["x"]), float(rot["y"]), float(rot["z"]), float(rot["w"])]
            out.append(
                SyncedActor(
                    actor_id=str(raw["actorId"]),
                    transform=Transform(
                        pos=adapter.ue5_to_canon_point(ue5_pos),
                        quat=adapter.ue5_to_canon_quat(ue5_quat),
                    ),
                )
            )
        return out

    # ----------------------------------------------------------------------- #
    # Concurrency fingerprint
    # ----------------------------------------------------------------------- #
    @staticmethod
    def snapshot_hash(actors: list[tuple[str, Transform]] | list[SyncedActor]) -> str:
        """
        A stable hash of the synced actor set, used as the optimistic-concurrency
        token. Sorted by actor id so call order can't perturb the fingerprint;
        positions/orientations are rounded so float noise across a round-trip
        doesn't spuriously trip the guard.
        """
        rows = []
        for entry in actors:
            if isinstance(entry, SyncedActor):
                actor_id, t = entry.actor_id, entry.transform
            else:
                actor_id, t = entry
            rows.append(
                {
                    "id": actor_id,
                    "pos": [round(v, 6) for v in t.pos],
                    "quat": [round(v, 6) for v in t.quat],
                    "scale": [round(v, 6) for v in t.scale],
                }
            )
        rows.sort(key=lambda r: r["id"])
        blob = json.dumps(rows, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    # ----------------------------------------------------------------------- #
    # Write: canonical -> UE5, concurrency-guarded, commit-once
    # ----------------------------------------------------------------------- #
    def commit(self, diff: Diff, expected_hash: str, *, selector: str = "tag:plumb") -> bool:
        """
        Commit a validated `diff` to UE5 — ONE PUT, guarded by `expected_hash`.

        Re-reads the scene (same `selector` that produced `expected_hash`) and
        compares its `snapshot_hash` to `expected_hash`; if they differ the world
        changed under us and we raise `ConcurrencyError` WITHOUT PUTting. Otherwise
        the canonical transform is converted to UE5 space (via the adapter) and PUT
        once. No live two-way loop (spec §15).
        """
        current = self.sync_scene(selector)
        if self.snapshot_hash(current) != expected_hash:
            raise ConcurrencyError(
                "UE5 scene changed since validation; refusing to commit "
                "(optimistic-concurrency guard)."
            )

        ue5_t = adapter.canon_to_ue5_transform(diff.transform)
        body = {
            "actorId": diff.object,
            "location": {"x": ue5_t.pos[0], "y": ue5_t.pos[1], "z": ue5_t.pos[2]},
            "rotation": {
                "x": ue5_t.quat[0],
                "y": ue5_t.quat[1],
                "z": ue5_t.quat[2],
                "w": ue5_t.quat[3],
            },
            "scale": {"x": ue5_t.scale[0], "y": ue5_t.scale[1], "z": ue5_t.scale[2]},
        }
        resp = self._client.put(COMMIT_PATH, json=body)
        resp.raise_for_status()
        return True

    def close(self) -> None:
        """Close the underlying httpx client."""
        self._client.close()

    def __enter__(self) -> "UE5Bridge":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
