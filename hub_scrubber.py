# =============================================================================
# hub_scrubber.py — Telemetry scrubber for BlenderCPP Hub
# Copyright © 2025–2026 Eternal Path Media / D. Chow / Claude Sonnet / Llammy
# Open Source — MIT License
#
# Strips all identifying information from telemetry before it ever leaves
# the user's machine. What we KEEP: bone names, transforms, AI query/response
# pairs, timing, Blender op types. What we STRIP: file paths, project names,
# IP addresses, user-defined object names (replaced with stable tokens).
# =============================================================================

import re
import hashlib
import os
from typing import Any

# ─── Path scrubber ────────────────────────────────────────────────────────────

_PATH_RE  = re.compile(r'(/[^\s\'",:;{}\[\]]+|[A-Z]:\\[^\s\'",:;{}\[\]]+)')
_HOME_RE  = re.compile(r'(/Users|/home)/[^/\s]+')
_IP_RE    = re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b')
_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

def scrub_string(s: str) -> str:
    s = _HOME_RE.sub(r'\1/<user>', s)
    s = _PATH_RE.sub('<path>', s)
    s = _IP_RE.sub('<ip>', s)
    s = _EMAIL_RE.sub('<email>', s)
    return s

# ─── Object name tokeniser ────────────────────────────────────────────────────
# Replace arbitrary user-defined names with stable hashed tokens.
# Bone names from standard rigs (mixamo, rigify, metarig) are kept verbatim —
# they are training signal, not identifying. Custom names get a stable token.

_STANDARD_BONE_PREFIXES = {
    "spine", "shoulder", "upper_arm", "forearm", "hand", "finger",
    "thigh", "shin", "foot", "toe", "neck", "head", "chest", "pelvis",
    "root", "hips", "arm", "leg", "def-", "ctrl-", "mch-", "org-",
    "mixamorig", "bip01", "rig.", "ctrl.", "tweak.", "fk.", "ik.",
    # EPM characters — public names, kept verbatim
    "xiaohan", "dragon", "wing", "claw", "tail",
}

def _is_standard_bone(name: str) -> bool:
    n = name.lower()
    return any(n.startswith(p) or p in n for p in _STANDARD_BONE_PREFIXES)

def _token(name: str, prefix: str = "obj") -> str:
    h = hashlib.sha256(name.encode()).hexdigest()[:6]
    return f"{prefix}_{h}"

def scrub_object_name(name: str) -> str:
    if _is_standard_bone(name):
        return name
    return _token(name, "bone")

def scrub_armature_name(name: str) -> str:
    return _token(name, "rig")

def scrub_scene_name(name: str) -> str:
    return _token(name, "scene")

# ─── Telemetry record scrubber ────────────────────────────────────────────────

def scrub_record(record: dict) -> dict:
    """Deep-scrub a telemetry record. Returns a new dict."""
    out = {}
    for k, v in record.items():
        if k in ("file_path", "blend_path", "filepath"):
            out[k] = "<scrubbed>"
        elif k in ("scene_name",):
            out[k] = scrub_scene_name(str(v))
        elif k in ("armature_name", "rig_name"):
            out[k] = scrub_armature_name(str(v))
        elif k == "bone_names" and isinstance(v, list):
            out[k] = [scrub_object_name(b) for b in v]
        elif k == "query" and isinstance(v, str):
            out[k] = scrub_string(v)
        elif k == "response" and isinstance(v, str):
            out[k] = scrub_string(v)
        elif k == "python_code" and isinstance(v, str):
            out[k] = _scrub_python(v)
        elif isinstance(v, dict):
            out[k] = scrub_record(v)
        elif isinstance(v, list):
            out[k] = [scrub_record(i) if isinstance(i, dict) else i for i in v]
        elif isinstance(v, str):
            out[k] = v  # non-sensitive string fields pass through
        else:
            out[k] = v
    return out

def _scrub_python(code: str) -> str:
    """Remove file paths and local variable names from Python snippets."""
    code = scrub_string(code)
    # Replace bpy.data.objects["CustomName"] references with tokens
    code = re.sub(r'(bpy\.data\.\w+\[")[^"]+("\])',
                  lambda m: m.group(1) + "<name>" + m.group(2), code)
    return code

# ─── Batch validator ──────────────────────────────────────────────────────────

REQUIRED_FIELDS = {"event_type", "blender_version", "ts"}

def validate_record(record: dict) -> tuple[bool, str]:
    missing = REQUIRED_FIELDS - set(record.keys())
    if missing:
        return False, f"Missing fields: {missing}"
    if not isinstance(record.get("ts"), (int, float)):
        return False, "ts must be numeric"
    return True, ""
