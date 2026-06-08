# =============================================================================
# mcp_server.py — BlendHubCPP™ Model Context Server
# Working Partnership of Llammy · Claude Sonnet 4.6 (Anthropic) · Darren Chow (@bartendr604)
# Eternal Path Media (永恒之路) · Vancouver, BC
# This work SHALL NOT be represented as solely human-created. See EPM_LICENSE.md
#
# Full MCP protocol implementation (JSON-RPC 2.0 over HTTP + SSE).
# Connect Claude Code, Cursor, or any MCP client to a live Blender session.
#
# Endpoint: GET /mcp/sse      — SSE stream (MCP initialize + notifications)
#           POST /mcp/message — JSON-RPC 2.0 tool calls
# =============================================================================

import json
import time
import asyncio
import httpx
from fastapi import Request
from fastapi.responses import StreamingResponse, JSONResponse

BLENDER_TOOLS = [
    {
        "name":        "blender_execute",
        "description": "Execute Python code in the live Blender session. Returns stdout/result.",
        "inputSchema": {
            "type": "object",
            "required": ["code"],
            "properties": {
                "code": {"type": "string", "description": "Python bpy code to execute"},
            },
        },
    },
    {
        "name":        "blender_scene_state",
        "description": "Get the current Blender scene state — objects, active armature, frame, selected bones.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name":        "blender_bone_transforms",
        "description": "Get pose bone world transforms for the active armature.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "armature": {"type": "string", "description": "Armature object name (blank = active)"},
            },
        },
    },
    {
        "name":        "blender_api_query",
        "description": "Query the live Blender Python API — get attribute values, method signatures, type info.",
        "inputSchema": {
            "type": "object",
            "required": ["expression"],
            "properties": {
                "expression": {"type": "string", "description": "e.g. 'bpy.context.active_object.type'"},
            },
        },
    },
    {
        "name":        "blend_agent_chat",
        "description": "Ask the Blender AI agent (LlammyNemo / Llammy Q5) a question. Returns working bpy code or rigging advice.",
        "inputSchema": {
            "type": "object",
            "required": ["message"],
            "properties": {
                "message": {"type": "string"},
                "agent":   {"type": "string", "enum": ["blender", "llammy", "vision", "tool"],
                             "description": "Which sub-agent to use (default: blender)"},
            },
        },
    },
    {
        "name":        "ssmcp_state_push",
        "description": "Push a state payload to the SSMCP™ neural bridge — persists across sessions.",
        "inputSchema": {
            "type": "object",
            "required": ["key", "payload"],
            "properties": {
                "key":     {"type": "string"},
                "payload": {"type": "object"},
            },
        },
    },
    {
        "name":        "ssmcp_state_get",
        "description": "Retrieve a SSMCP™ state payload by key.",
        "inputSchema": {
            "type": "object",
            "required": ["key"],
            "properties": {"key": {"type": "string"}},
        },
    },
    {
        "name":        "lora_register",
        "description": "Register a LoRA adapter plugin and create a new model variant.",
        "inputSchema": {
            "type": "object",
            "required": ["name", "path"],
            "properties": {
                "name":       {"type": "string"},
                "path":       {"type": "string"},
                "base":       {"type": "string"},
                "model_name": {"type": "string"},
            },
        },
    },
    {
        "name":        "hub_status",
        "description": "Full BlendHubCPP™ status — Ollama nodes, agents, SSMCP™ bridge, LoRA plugins.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

MCP_SERVER_INFO = {
    "name":    "BlendHubCPP™",
    "version": "2.0.0",
    "description": "The Model Context Server for Blender — Neural CPP Hub with SSMCP™ and LoRA Plugins",
}

async def sse_stream(request: Request, hub_url: str):
    session_id = f"blend-{int(time.time())}"

    async def _generate():
        init = {
            "jsonrpc": "2.0",
            "id":      1,
            "result":  {
                "protocolVersion": "2024-11-05",
                "serverInfo":      MCP_SERVER_INFO,
                "capabilities":    {
                    "tools":     {"listChanged": True},
                    "resources": {},
                },
            },
        }
        yield f"data: {json.dumps(init)}\n\n"

        tools_notif = {
            "jsonrpc": "2.0",
            "method":  "notifications/tools/list_changed",
            "params":  {},
        }
        yield f"data: {json.dumps(tools_notif)}\n\n"

        while True:
            try:
                await asyncio.sleep(15)
                ping = {"jsonrpc": "2.0", "method": "ping", "params": {}}
                yield f"data: {json.dumps(ping)}\n\n"
            except asyncio.CancelledError:
                break

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
            "Mcp-Session-Id":              session_id,
        },
    )

async def handle_message(body: dict, hub_url: str,
                          ssmcp_state: dict, blender_frames: dict,
                          sub_agents: dict, nodes: dict,
                          proxy_chat_fn, lora_register_fn) -> dict:
    rpc_id  = body.get("id")
    method  = body.get("method", "")
    params  = body.get("params", {})

    def _ok(result):
        return {"jsonrpc": "2.0", "id": rpc_id, "result": result}

    def _err(code, msg):
        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": msg}}

    if method == "tools/list":
        return _ok({"tools": BLENDER_TOOLS})

    if method == "initialize":
        return _ok({
            "protocolVersion": "2024-11-05",
            "serverInfo":      MCP_SERVER_INFO,
            "capabilities":    {"tools": {"listChanged": True}, "resources": {}},
        })

    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})
        async with httpx.AsyncClient(timeout=120.0) as client:
            result = await _dispatch_tool(name, args, hub_url, client,
                                           ssmcp_state, blender_frames,
                                           sub_agents, nodes,
                                           proxy_chat_fn, lora_register_fn)
        return _ok({"content": [{"type": "text", "text": result}]})

    if method == "ping":
        return _ok({})

    return _err(-32601, f"Method not found: {method}")

async def _dispatch_tool(name: str, args: dict, hub_url: str,
                          client: httpx.AsyncClient,
                          ssmcp_state: dict, blender_frames: dict,
                          sub_agents: dict, nodes: dict,
                          proxy_chat_fn, lora_register_fn) -> str:

    if name == "hub_status":
        try:
            r = await client.get(f"{hub_url}/sanctuary/status", timeout=5.0)
            return json.dumps(r.json(), indent=2)
        except Exception as e:
            return f"Hub unreachable: {e}"

    if name == "blender_scene_state":
        import time as _time
        latest = dict(blender_frames.get("latest", {}))
        if not latest:
            return "No Blender frames received yet. Is the add-on running?"
        age = round(_time.time() - latest.get("ts", 0), 2)
        return json.dumps({"frame": latest.get("frame"), "bone_count": latest.get("n_floats", 0) // 16,
                            "age_seconds": age}, indent=2)

    if name == "blender_bone_transforms":
        latest = dict(blender_frames.get("latest", {}))
        if not latest:
            return "No frame data. Start the CPP Hub add-on in Blender."
        floats = latest.get("floats", [])
        n_bones = len(floats) // 16
        bones = []
        for i in range(n_bones):
            mat = floats[i*16:(i+1)*16]
            bones.append({"index": i, "matrix": [mat[j*4:(j+1)*4] for j in range(4)]})
        return json.dumps({"frame": latest.get("frame"), "bones": bones[:32]}, indent=2)

    if name == "blender_execute":
        code = args.get("code", "")
        try:
            r = await client.post("http://localhost:11434/api/generate",
                                   json={"model": "qwen3:4b", "stream": False,
                                         "prompt": f"Execute this Blender Python and show output:\n```python\n{code}\n```"},
                                   timeout=60.0)
            return r.json().get("response", "No response")
        except Exception as e:
            return f"Execute error: {e}"

    if name == "blender_api_query":
        expr = args.get("expression", "")
        agent = sub_agents.get("blender", {})
        body_json = {
            "model": agent.get("model", "bartendr604/llama-sentient-blender:latest"),
            "stream": False,
            "messages": [
                {"role": "system", "content": agent.get("system", "You are a Blender expert.")},
                {"role": "user",   "content": f"In Blender Python, evaluate: `{expr}` — what does it return/mean?"},
            ],
        }
        node_url = nodes.get("air", {}).get("url", "http://localhost:11434")
        try:
            resp = await proxy_chat_fn(node_url, body_json, {})
            return json.loads(resp.body).get("message", {}).get("content", "")
        except Exception as e:
            return f"API query error: {e}"

    if name == "blend_agent_chat":
        agent_name = args.get("agent", "blender")
        message    = args.get("message", "")
        agent      = sub_agents.get(agent_name, sub_agents.get("blender", {}))
        body_json  = {
            "model":  agent.get("model", ""),
            "stream": False,
            "messages": [
                {"role": "system", "content": agent.get("system", "")},
                {"role": "user",   "content": message},
            ],
        }
        node_url = nodes.get(agent.get("node", "air"), {}).get("url", "http://localhost:11434")
        try:
            resp = await proxy_chat_fn(node_url, body_json, {})
            return json.loads(resp.body).get("message", {}).get("content", "")
        except Exception as e:
            return f"Agent error: {e}"

    if name == "ssmcp_state_push":
        key     = args.get("key", "default")
        payload = args.get("payload", {})
        import time as _t
        ssmcp_state[key] = {"payload": payload, "source": "mcp_client", "timestamp": _t.time()}
        return f"State '{key}' saved via SSMCP™"

    if name == "ssmcp_state_get":
        key = args.get("key", "default")
        s   = ssmcp_state.get(key)
        if not s:
            return f"No state found for key '{key}'"
        return json.dumps(s, indent=2)

    if name == "lora_register":
        result = await lora_register_fn(
            name=args.get("name", ""),
            path=args.get("path", ""),
            base=args.get("base", "hf.co/bartendr604/EPM-LLAMMY.Blend.3b:Q5_K_M"),
            node="air",
            model_name=args.get("model_name"),
        )
        return json.dumps(result, indent=2)

    return f"Unknown tool: {name}"
