"""
studio/semantics.py — the AI semantic bake (architecture §3, "AI bakes the model").

Renders of an asset go to Gemini, which infers what it *is*: object class, canonical
up/front, the material of each visible region, and affordances (what an agent can do
with it). This is the semantic layer the geometric/physical bake can't produce on its
own — "the agent's first encounter with an asset is to study it, not place it."

Free to run: get a key at https://aistudio.google.com (AI Studio) and set
``GEMINI_API_KEY`` (or ``GOOGLE_API_KEY``). Uses the ``google-genai`` SDK + the current
``gemini-3.5-flash`` (fast, multimodal, generous free tier). Degrades gracefully — if
no key/SDK, the caller surfaces a clear message and the rest of the bake is unaffected.
"""

from __future__ import annotations

import json
import os

MODEL = "gemini-3.5-flash"

_PROMPT = (
    "You are PLUMB's semantic asset bake. These are renders of ONE 3D asset. Infer its "
    "physical semantics and respond with ONLY compact JSON, no prose:\n"
    '{"class":"<noun>","up":[x,y,z],"front":[x,y,z],'
    '"materials":[{"region":"<short name>","material":"<wood|metal|stone|glass|plastic|fabric|foliage|water|default>"}],'
    '"affordances":["<verb phrase>"],"confidence":0.0}\n'
    "Rules: up/front are unit vectors in a Z-up right-handed frame. materials lists the "
    "visibly-distinct regions. affordances are concrete agent actions (e.g. \"sit\", "
    "\"place_on_surface\", \"grasp_handle\", \"hangs_from_branch\"). Keep it concise."
)


# Repo-root fallback file (gitignored). Lets the key be found regardless of which
# shell launched uvicorn — env var still wins if set.
_KEY_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".gemini_key")


def _key() -> str | None:
    env = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if env:
        return env
    try:
        with open(_KEY_FILE, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def gemini_status() -> dict:
    """Whether the AI semantic bake can run (for /health + the UI)."""
    try:
        from google import genai  # noqa: F401
    except Exception:
        return {"available": False, "sdk": False, "key": bool(_key())}
    return {"available": bool(_key()), "sdk": True, "key": bool(_key())}


def semantic_bake(images: list[bytes], hint: str = "") -> dict:
    """Send PNG renders + the prompt to Gemini; return the parsed semantics dict.

    Raises ``RuntimeError`` if unconfigured, or the SDK error on a call failure.
    """
    if not _key():
        raise RuntimeError("Gemini not configured (set GEMINI_API_KEY)")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_key())
    contents: list = [types.Part.from_bytes(data=img, mime_type="image/png") for img in images]
    contents.append(_PROMPT + (f"\nHint about the asset: {hint}" if hint else ""))
    resp = client.models.generate_content(model=MODEL, contents=contents)

    return _parse_json(resp.text)


def _parse_json(text: str | None) -> dict:
    text = (text or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return {"raw": text}


_MASKS_PROMPT = (
    "You are PLUMB's mask author. These are renders of ONE 3D asset. Reason about it and "
    "respond with ONLY compact JSON, no prose:\n"
    '{"affordances":[{"verb":"<agent action e.g. sit/grasp/place_on>","where":"top|middle|base|side|center"}],'
    '"fragility":[{"band":"top|middle|bottom","score":0.0}],'
    '"graspability":[{"band":"top|middle|bottom","score":0.0}],'
    '"wear":[{"band":"top|middle|bottom","score":0.0}],'
    '"load_bearing":[{"band":"top|middle|bottom","score":0.0}],'
    '"value":[{"band":"top|middle|bottom","score":0.0}],'
    '"attach_load":[{"band":"top|middle|bottom","score":0.0}],'
    '"confidence":0.0}\n'
    "Each *_band array must give ALL THREE bands (top/middle/bottom vertical thirds), each "
    "score 0..1:\n"
    "- fragility: 0 sturdy, 1 very delicate.\n"
    "- graspability: 0 impossible to grip, 1 an ideal handle/grip.\n"
    "- wear: 0 pristine, 1 heavily worn / weathered / damaged.\n"
    "- load_bearing: 0 decorative, 1 carries the asset's own structural load.\n"
    "- value: 0 cheap/common, 1 precious/valuable.\n"
    "- attach_load: 0 holds nothing, 1 can bear heavy weight if you mount or hang an object there.\n"
    "affordances are concrete actions with a coarse location. Keep it concise."
)


def semantic_masks(images: list[bytes], hint: str = "") -> dict:
    """Ask Gemini for mask-able semantics: located affordances + per-band fragility.

    Returns ``{"affordances":[...], "fragility":[...], "confidence":float}``. Raises
    ``RuntimeError`` if unconfigured. Shares the client/key logic with ``semantic_bake``.
    """
    if not _key():
        raise RuntimeError("Gemini not configured (set GEMINI_API_KEY)")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_key())
    contents: list = [types.Part.from_bytes(data=img, mime_type="image/png") for img in images]
    contents.append(_MASKS_PROMPT + (f"\nHint about the asset: {hint}" if hint else ""))
    resp = client.models.generate_content(model=MODEL, contents=contents)
    return _parse_json(resp.text)
