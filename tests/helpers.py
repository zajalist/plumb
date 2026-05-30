"""
Shared test aids for the Conscience suite. Headless only — no GPU, no Unreal.

Deliberately minimal: the `.wdf` sample text is authored by the wdf task from the
spec (so it matches whatever grammar that task defines); here we only provide stable,
cross-task aids — temp paths and an illustrative UE5 Remote Control payload for the
mock HTTP server.
"""

from __future__ import annotations

import tempfile


def tmp_path(suffix: str) -> str:
    """A throwaway temp file path (e.g. ".rrd" recordings, ".wdf" docs)."""
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.close()
    return f.name


# Illustrative UE5 Remote Control response for ONE tagged actor.
# UE5 space: left-handed, Z-up, centimetres. The adapter must convert to canonical
# (right-handed, metres). Shape is representative — the bridge task may refine it,
# but the mock server should serve something like this so parsing is exercised.
def mock_ue5_actor(
    actor_id: str = "/Game/Maps/Gallery.Gallery:PersistentLevel.BronzeFigure_3",
    location_cm=(-100.0, 200.0, 300.0),     # UE5 cm, LH
    rotation_quat=(0.0, 0.0, 0.0, 1.0),     # [x, y, z, w]
    extent_cm=(15.0, 15.0, 75.0),           # half-extents in cm
) -> dict:
    return {
        "actorId": actor_id,
        "location": {"x": location_cm[0], "y": location_cm[1], "z": location_cm[2]},
        "rotation": {"x": rotation_quat[0], "y": rotation_quat[1],
                     "z": rotation_quat[2], "w": rotation_quat[3]},
        "boundsExtent": {"x": extent_cm[0], "y": extent_cm[1], "z": extent_cm[2]},
        "tags": ["plumb"],
    }


def mock_ue5_scene(n: int = 1) -> dict:
    """A Remote Control 'get tagged actors' style response with `n` actors."""
    return {"actors": [mock_ue5_actor(actor_id=f"Actor_{i}") for i in range(n)]}
