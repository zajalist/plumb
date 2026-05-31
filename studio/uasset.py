"""
studio/uasset.py — headless Unreal → glTF conversion for the bake.

Unreal cooks meshes into ``.uasset`` (proprietary binary) that trimesh can't read.
This module drives ``UnrealEditor-Cmd.exe`` headlessly to export dropped
``.uasset`` static meshes to ``.glb`` (which the bake reads natively). One editor
boot exports a whole batch, so a folder of assets pays the ~30s startup once.

How it loads a loose asset: UE addresses content by *package path* (``/Game/...``),
not file path, so we copy each uploaded ``.uasset`` into the configured project's
``Content/PlumbImport/`` (where UE's boot scan registers it), export, then remove
the copy. Only mesh *geometry* is needed — material/texture references that don't
resolve in the host project just fall back to default, which the bake re-guesses.

Config (graceful: absent => callers degrade to "import .obj/.glb/.stl"):
  PLUMB_UE_CMD      path to UnrealEditor-Cmd.exe (auto-detected if unset)
  PLUMB_UE_PROJECT  path to a host .uproject whose Content we stage imports into
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

IMPORT_FOLDER = "PlumbImport"  # staged under <project>/Content/<IMPORT_FOLDER>/

_UE_CMD_CANDIDATES = [
    r"C:/Program Files/Epic Games/UE_5.6/Engine/Binaries/Win64/UnrealEditor-Cmd.exe",
    r"C:/Program Files/Epic Games/UE_5.7/Engine/Binaries/Win64/UnrealEditor-Cmd.exe",
    r"C:/Program Files/Epic Games/UE_5.5/Engine/Binaries/Win64/UnrealEditor-Cmd.exe",
]


def ue_cmd() -> str | None:
    """Path to UnrealEditor-Cmd.exe (env override, then common install dirs)."""
    env = os.environ.get("PLUMB_UE_CMD")
    if env and os.path.exists(env):
        return env
    return next((c for c in _UE_CMD_CANDIDATES if os.path.exists(c)), None)


def ue_project() -> str | None:
    """Path to the host .uproject we stage imports into (env ``PLUMB_UE_PROJECT``)."""
    env = os.environ.get("PLUMB_UE_PROJECT")
    return env if (env and os.path.exists(env)) else None


def ue_status() -> dict:
    """Whether headless conversion is wired up (for /health + the UI)."""
    cmd, proj = ue_cmd(), ue_project()
    return {"available": bool(cmd and proj), "cmd": bool(cmd), "project": bool(proj)}


def is_uasset(filename: str) -> bool:
    return filename.lower().endswith(".uasset")


def _stem(name: str) -> str:
    base = os.path.basename(name)
    return base[: -len(".uasset")] if is_uasset(base) else base


def _export_script(stems: list[str], out_dir: str) -> str:
    """Generate the in-editor Python that exports each staged mesh to ``.glb``."""
    out = out_dir.replace("\\", "/")
    folder = "/Game/" + IMPORT_FOLDER
    return (
        "import os, unreal\n"
        f"OUT = r'{out}'\n"
        f"STEMS = {stems!r}\n"
        f"FOLDER = '{folder}'\n"
        "os.makedirs(OUT, exist_ok=True)\n"
        "for stem in STEMS:\n"
        "    obj = '%s/%s.%s' % (FOLDER, stem, stem)\n"
        "    mesh = unreal.load_asset(obj)\n"
        "    if mesh is None:\n"
        "        unreal.log_warning('PLUMB missing ' + obj); continue\n"
        "    task = unreal.AssetExportTask()\n"
        "    task.set_editor_property('object', mesh)\n"
        "    task.set_editor_property('filename', os.path.join(OUT, stem + '.glb'))\n"
        "    task.set_editor_property('automated', True)\n"
        "    task.set_editor_property('prompt', False)\n"
        "    task.set_editor_property('replace_identical', True)\n"
        "    ok = unreal.Exporter.run_asset_export_task(task)\n"
        "    unreal.log('PLUMB exported %s ok=%s' % (stem, ok))\n"
        "unreal.log('PLUMB DONE')\n"
    )


def convert_uassets(assets: dict[str, str], timeout: int = 600) -> dict[str, str | None]:
    """Convert ``{display_name: local_uasset_path}`` to ``{display_name: glb_path|None}``.

    Stages every asset into the host project, runs **one** headless UE export for the
    batch, then cleans up the staged copies. A name maps to ``None`` if UE produced no
    ``.glb`` for it (missing asset, non-static-mesh, or export error) — the caller
    surfaces that per file rather than failing the whole batch.
    """
    cmd, proj = ue_cmd(), ue_project()
    if not (cmd and proj):
        raise RuntimeError("Unreal not configured (set PLUMB_UE_CMD and PLUMB_UE_PROJECT)")

    project_dir = os.path.dirname(proj)
    staging = os.path.join(project_dir, "Content", IMPORT_FOLDER)
    os.makedirs(staging, exist_ok=True)
    out_dir = tempfile.mkdtemp(prefix="plumb_glb_")

    staged: list[str] = []
    stems: list[str] = []
    try:
        for name, src in assets.items():
            stem = _stem(name)
            dst = os.path.join(staging, stem + ".uasset")
            shutil.copyfile(src, dst)
            staged.append(dst)
            stems.append(stem)

        script_path = os.path.join(out_dir, "_plumb_export.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(_export_script(stems, out_dir))

        subprocess.run(
            [cmd, proj, "-run=pythonscript", f"-script={script_path}",
             "-nullrhi", "-unattended", "-nopause", "-nosplash", "-stdout"],
            capture_output=True, text=True, timeout=timeout,
        )

        result: dict[str, str | None] = {}
        for name in assets:
            glb = os.path.join(out_dir, _stem(name) + ".glb")
            result[name] = glb if os.path.exists(glb) else None
        return result
    finally:
        for d in staged:
            try:
                os.remove(d)
            except OSError:
                pass


def convert_uasset(name: str, path: str, timeout: int = 600) -> str | None:
    """Convert a single ``.uasset`` → ``.glb`` path (or ``None`` on failure)."""
    return convert_uassets({name: path}, timeout=timeout)[name]
