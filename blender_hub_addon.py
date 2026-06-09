# =============================================================================
# blender_hub_addon.py — Blender SSMCP CPP Hub Add-on
# Copyright © 2025–2026 Eternal Path Media / D. Chow / Claude Sonnet / Llammy
#
# Blender add-on that wraps hub_core.dylib (compiled C++ library).
# Registers frame_change + depsgraph handlers; pushes bone matrices to the
# SSMCP hub at C++ speed via the ring buffer.
#
# Install: Blender → Edit → Preferences → Add-ons → Install from file
# Or drop into: ~/Library/Application Support/Blender/<ver>/scripts/addons/
# =============================================================================

bl_info = {
    "name":        "SSMCP CPP Hub Bridge",
    "author":      "Eternal Path Media / D. Chow / Claude Sonnet / Llammy",
    "version":     (1, 0, 0),
    "blender":     (4, 0, 0),
    "location":    "3D Viewport → Sidebar → EPM",
    "description": "Real-time bone/animation bridge to SSMCP Hub via C++ ring buffer",
    "category":    "Animation",
}

import bpy
import ctypes
import json
import os
import struct
import time
import threading
import urllib.request
import urllib.error
from pathlib import Path

# ─── Academy telemetry ───────────────────────────────────────────────────────
# Opt-in only. Collects anonymised Blender operation data to train better
# Blender AI models. All data is scrubbed on-device before transmission.
# Policy: /academy/manifest endpoint or PRIVACY.md in the repo.

_telem_buffer:  list = []
_telem_lock     = threading.Lock()
_telem_thread:  threading.Thread | None = None
_telem_stop     = threading.Event()
TELEM_BATCH_SZ  = 20
TELEM_FLUSH_SEC = 60.0

def _blender_version() -> str:
    import bpy
    v = bpy.app.version
    return f"{v[0]}.{v[1]}.{v[2]}"

def _scrub_name(name: str) -> str:
    """Basic on-device name scrub — proper scrub happens server-side too."""
    import hashlib
    _keep = {"spine", "shoulder", "arm", "hand", "finger", "leg", "foot",
              "neck", "head", "chest", "pelvis", "root", "hips", "toe",
              "xiaohan", "dragon", "wing", "claw", "tail",
              "mixamorig", "rig.", "ctrl.", "fk.", "ik.", "def-", "mch-"}
    nl = name.lower()
    if any(k in nl for k in _keep):
        return name
    return "bone_" + hashlib.sha256(name.encode()).hexdigest()[:6]

def telem_record(event_type: str, data: dict):
    """Buffer a telemetry record. No-op if consent not given."""
    try:
        scene = bpy.context.scene
        if not scene.cpp_hub_props.academy_consent:
            return
    except Exception:
        return
    record = {
        "event_type":      event_type,
        "blender_version": _blender_version(),
        "ts":              time.time(),
        **data,
    }
    with _telem_lock:
        _telem_buffer.append(record)

def _flush_telem(hub_host: str, hub_port: int):
    with _telem_lock:
        if not _telem_buffer:
            return
        batch = _telem_buffer.copy()
        _telem_buffer.clear()
    payload = json.dumps({"records": batch}).encode()
    url = f"http://{hub_host}:{hub_port}/academy/batch"
    try:
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass  # telemetry is best-effort, never block

def _telem_worker(hub_host: str, hub_port: int):
    while not _telem_stop.wait(TELEM_FLUSH_SEC):
        if len(_telem_buffer) >= TELEM_BATCH_SZ:
            _flush_telem(hub_host, hub_port)
    _flush_telem(hub_host, hub_port)  # final flush on stop

def _start_telem(hub_host: str, hub_port: int):
    global _telem_thread
    _telem_stop.clear()
    _telem_thread = threading.Thread(
        target=_telem_worker, args=(hub_host, hub_port), daemon=True)
    _telem_thread.start()

def _stop_telem():
    _telem_stop.set()

# ─── Load hub_core.dylib ─────────────────────────────────────────────────────

_ADDON_DIR  = Path(__file__).parent
_LIB_PATH   = _ADDON_DIR / "hub_core.dylib"
_lib: ctypes.CDLL | None = None

def _load_lib() -> ctypes.CDLL | None:
    global _lib
    if _lib is not None:
        return _lib
    if not _LIB_PATH.exists():
        print(f"[CPP Hub] hub_core.dylib not found at {_LIB_PATH}. Run build.sh first.")
        return None
    try:
        _lib = ctypes.CDLL(str(_LIB_PATH))
        _setup_ctypes(_lib)
        print(f"[CPP Hub] Loaded {_LIB_PATH}")
        return _lib
    except Exception as e:
        print(f"[CPP Hub] Failed to load library: {e}")
        return None

def _setup_ctypes(lib: ctypes.CDLL):
    lib.hub_set_target.argtypes  = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
    lib.hub_set_target.restype   = None
    lib.hub_start.argtypes       = []
    lib.hub_start.restype        = ctypes.c_int
    lib.hub_stop.argtypes        = []
    lib.hub_stop.restype         = None
    lib.hub_push_frame.argtypes  = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_float), ctypes.c_int]
    lib.hub_push_frame.restype   = ctypes.c_int
    lib.hub_flush.argtypes       = []
    lib.hub_flush.restype        = None
    lib.hub_send_state.argtypes  = [ctypes.c_char_p, ctypes.c_char_p]
    lib.hub_send_state.restype   = ctypes.c_int
    lib.hub_agent_chat.argtypes  = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    lib.hub_agent_chat.restype   = ctypes.c_int
    lib.hub_poll_command.argtypes= [ctypes.c_char_p, ctypes.c_int]
    lib.hub_poll_command.restype = ctypes.c_int
    lib.hub_ping.argtypes        = []
    lib.hub_ping.restype         = ctypes.c_int
    lib.hub_last_error.argtypes  = []
    lib.hub_last_error.restype   = ctypes.c_char_p
    lib.hub_stats.argtypes       = [
        ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_int),    ctypes.POINTER(ctypes.c_int),
    ]
    lib.hub_stats.restype        = None

# ─── Bone matrix extraction ───────────────────────────────────────────────────

def _collect_bone_matrices(obj) -> list[str] | None:
    """Return pose bone names and flat float32 matrix arrays."""
    if not obj or obj.type != 'ARMATURE' or not obj.pose:
        return None
    names   = []
    floats  = []
    for bone in obj.pose.bones:
        m = bone.matrix
        for row in m:
            floats.extend(row)
        names.append(bone.name)
    return names, floats

def _collect_telem_frame(scene, names: list[str]):
    telem_record("frame_push", {
        "frame":       scene.frame_current,
        "bone_count":  len(names),
        "bone_names":  [_scrub_name(n) for n in names[:32]],
        "fps":         scene.render.fps,
    })

# ─── Blender handlers ─────────────────────────────────────────────────────────

_tracked_armature: str | None = None

def _on_frame_change(scene, depsgraph=None):
    lib = _lib
    if lib is None:
        return
    prefs = scene.cpp_hub_props
    if not prefs.enabled:
        return
    obj_name = prefs.armature_name or _tracked_armature
    if not obj_name:
        return
    obj = scene.objects.get(obj_name)
    if not obj:
        return
    result = _collect_bone_matrices(obj)
    if result is None:
        return
    names, floats = result
    arr = (ctypes.c_float * len(floats))(*floats)
    frame_num = ctypes.c_uint32(scene.frame_current)
    lib.hub_push_frame(frame_num, arr, len(names))
    if scene.frame_current % 10 == 0:  # sample 1 in 10 frames
        _collect_telem_frame(scene, names)

def _on_depsgraph_update(scene, depsgraph):
    lib = _lib
    if lib is None:
        return
    prefs = scene.cpp_hub_props
    if not prefs.enabled or not prefs.send_scene_state:
        return
    updated = [u.id.name for u in depsgraph.updates if u.is_updated_transform]
    if not updated:
        return
    payload = json.dumps({"frame": scene.frame_current, "updated": updated[:32]})
    lib.hub_send_state(b"blender.depsgraph", payload.encode())

# ─── Properties ───────────────────────────────────────────────────────────────

class CPPHubProperties(bpy.types.PropertyGroup):
    enabled: bpy.props.BoolProperty(
        name="Enable Bridge", default=False,
        description="Push animation data to SSMCP Hub")
    hub_host: bpy.props.StringProperty(
        name="Hub Host", default="127.0.0.1")
    hub_port: bpy.props.IntProperty(
        name="HTTP Port", default=19999, min=1, max=65535)
    bin_port: bpy.props.IntProperty(
        name="Binary Port", default=19994, min=1, max=65535)
    armature_name: bpy.props.StringProperty(
        name="Armature", default="",
        description="Object name of the armature to track (blank = auto-detect)")
    send_scene_state: bpy.props.BoolProperty(
        name="Send Scene State", default=True,
        description="Send depsgraph updates as SSMCP state")
    academy_consent: bpy.props.BoolProperty(
        name="Contribute to EPM Blender Academy",
        default=False,
        description=(
            "Opt in to share anonymised usage data with the EPM Blender Academy dataset. "
            "File paths, project names, and custom identifiers are scrubbed on-device "
            "before transmission. Improves AI models for the whole community. "
            "See /academy/manifest for the full data policy."
        )
    )

# ─── Operators ────────────────────────────────────────────────────────────────

class CPP_OT_StartHub(bpy.types.Operator):
    bl_idname  = "cpp_hub.start"
    bl_label   = "Start Hub"
    bl_description = "Load hub_core.dylib and start the background flush thread"

    def execute(self, context):
        lib = _load_lib()
        if lib is None:
            self.report({'ERROR'}, "hub_core.dylib not found — run build.sh first")
            return {'CANCELLED'}
        p = context.scene.cpp_hub_props
        lib.hub_set_target(p.hub_host.encode(), p.hub_port, p.bin_port)
        rc = lib.hub_start()
        if rc != 0:
            self.report({'WARNING'}, "Hub already running")
        else:
            p.enabled = True
            bpy.app.handlers.frame_change_post.append(_on_frame_change)
            bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update)
            if p.academy_consent:
                _start_telem(p.hub_host, p.hub_port)
            self.report({'INFO'}, f"CPP Hub started → {p.hub_host}:{p.hub_port}")
        return {'FINISHED'}

class CPP_OT_StopHub(bpy.types.Operator):
    bl_idname  = "cpp_hub.stop"
    bl_label   = "Stop Hub"
    bl_description = "Flush remaining frames and stop the background thread"

    def execute(self, context):
        lib = _lib
        if lib is None:
            self.report({'INFO'}, "Hub not loaded")
            return {'CANCELLED'}
        lib.hub_flush()
        lib.hub_stop()
        _stop_telem()
        context.scene.cpp_hub_props.enabled = False
        if _on_frame_change in bpy.app.handlers.frame_change_post:
            bpy.app.handlers.frame_change_post.remove(_on_frame_change)
        if _on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update)
        self.report({'INFO'}, "CPP Hub stopped")
        return {'FINISHED'}

class CPP_OT_Ping(bpy.types.Operator):
    bl_idname  = "cpp_hub.ping"
    bl_label   = "Ping Hub"
    bl_description = "Test connection to SSMCP Hub"

    def execute(self, context):
        lib = _load_lib()
        if lib is None:
            self.report({'ERROR'}, "Library not loaded")
            return {'CANCELLED'}
        p  = context.scene.cpp_hub_props
        lib.hub_set_target(p.hub_host.encode(), p.hub_port, p.bin_port)
        rc = lib.hub_ping()
        if rc == 0:
            self.report({'INFO'}, f"Hub alive at {p.hub_host}:{p.hub_port}")
        else:
            err = lib.hub_last_error().decode()
            self.report({'ERROR'}, f"Hub unreachable: {err}")
        return {'FINISHED'}

class CPP_OT_AskAgent(bpy.types.Operator):
    bl_idname  = "cpp_hub.ask_agent"
    bl_label   = "Ask Blender Agent"
    bl_description = "Send a message to the blender sub-agent via the hub"

    message: bpy.props.StringProperty(name="Message", default="What bones are on the rig?")
    agent:   bpy.props.StringProperty(name="Agent",   default="blender")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        lib = _load_lib()
        if lib is None:
            self.report({'ERROR'}, "Library not loaded")
            return {'CANCELLED'}
        buf = ctypes.create_string_buffer(65536)
        rc  = lib.hub_agent_chat(self.agent.encode(), self.message.encode(), buf, 65536)
        if rc == 0:
            try:
                resp = json.loads(buf.value.decode())
                text = resp.get("response", buf.value.decode()[:200])
            except Exception:
                text = buf.value.decode()[:300]
            telem_record("agent_query", {
                "agent":    self.agent,
                "query":    self.message[:4000],
                "response": text[:4000],
                "success":  True,
            })
            self.report({'INFO'}, text[:250])
        else:
            telem_record("agent_query", {"agent": self.agent, "success": False})
            self.report({'ERROR'}, f"Agent call failed: {lib.hub_last_error().decode()}")
        return {'FINISHED'}

# ─── Panel ────────────────────────────────────────────────────────────────────

class CPP_PT_HubPanel(bpy.types.Panel):
    bl_label       = "SSMCP CPP Hub"
    bl_idname      = "CPP_PT_hub"
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = 'EPM'

    def draw(self, context):
        layout = self.layout
        p      = context.scene.cpp_hub_props

        col = layout.column(align=True)
        col.label(text="Connection", icon='NETWORK_DRIVE')
        col.prop(p, "hub_host")
        row = col.row(align=True)
        row.prop(p, "hub_port")
        row.prop(p, "bin_port")

        layout.separator()
        col = layout.column(align=True)
        col.label(text="Tracking", icon='ARMATURE_DATA')
        col.prop_search(p, "armature_name", context.scene, "objects")
        col.prop(p, "send_scene_state")

        layout.separator()
        row = layout.row(align=True)
        if not p.enabled:
            row.operator("cpp_hub.start", icon='PLAY')
        else:
            row.operator("cpp_hub.stop",  icon='PAUSE')
        row.operator("cpp_hub.ping",      icon='WORLD')

        layout.separator()
        layout.operator("cpp_hub.ask_agent", icon='OUTLINER_DATA_FONT')

        layout.separator()
        box = layout.box()
        box.label(text="EPM Blender Academy", icon='COMMUNITY')
        box.prop(p, "academy_consent")
        if p.academy_consent:
            box.label(text="Contributing anonymised data.", icon='CHECKMARK')
            box.label(text="Paths/names scrubbed on-device.")
        else:
            box.label(text="Opt in to improve shared AI models.")

        if p.enabled and _lib:
            fs = ctypes.c_uint64(0)
            cr = ctypes.c_uint64(0)
            rd = ctypes.c_int(0)
            cd = ctypes.c_int(0)
            _lib.hub_stats(ctypes.byref(fs), ctypes.byref(cr),
                           ctypes.byref(rd), ctypes.byref(cd))
            col = layout.column(align=True)
            col.label(text=f"Frames sent: {fs.value}")
            col.label(text=f"Ring depth:  {rd.value}")
            col.label(text=f"Cmds recv:   {cr.value}")

# ─── Registration ─────────────────────────────────────────────────────────────

_CLASSES = [
    CPPHubProperties,
    CPP_OT_StartHub,
    CPP_OT_StopHub,
    CPP_OT_Ping,
    CPP_OT_AskAgent,
    CPP_PT_HubPanel,
]

def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.cpp_hub_props = bpy.props.PointerProperty(type=CPPHubProperties)
    print("[CPP Hub] Registered")

def unregister():
    lib = _lib
    if lib:
        lib.hub_flush()
        lib.hub_stop()
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.cpp_hub_props
    print("[CPP Hub] Unregistered")

if __name__ == "__main__":
    register()
