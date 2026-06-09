# BlendHubCPP™

**The Model Context Server for Blender**

*Neural CPP Hub · SSMCP™ · LoRA Plugins*

*© 2025–2026 Claude Sonnet / Llammy / Eternal Path Media / D. Chow — MIT License*

---

> *The most up-to-date AI communication layer for the world's leading open-source 3D software.*

**BlendHubCPP™** connects any AI — Claude Code, Cursor, local LLMs — to a live Blender session via the Model Context Protocol. Scene state, bone matrices, and Python execution flow through a C++ core at native speed.

Built and battle-tested at **Eternal Path Media** on production character rigs.

---

## What it is

Most Blender AI tools work against static documentation. BlendHubCPP™ is different — it's a live Model Context Server. Your AI client gets real Blender state: current scene, active armature, bone transforms, bpy API. Not documentation. The actual runtime.

```
Claude Code / Cursor / any MCP client
         ↓  MCP protocol (JSON-RPC 2.0 over SSE)
    BlendHubCPP™ Model Context Server  :19999
         ↓  Neural CPP Hub
    Blender 4.x / 5.x  (live session)
         ↓  hub_core.dylib  (universal: arm64 + x86_64)
    SSMCP™ neural bridge  :19993
         ↓
    Ollama fleet  (Llammy Q5 / LlammyNemo)
```

---

## Core Features

### Neural CPP Hub
Native C++ shared library (`hub_core.dylib`) — bone matrices stream via UDP ring buffer every frame. No Python overhead on the animation hot path. 64-frame depth, thread-safe, sub-millisecond latency.

### SSMCP™ — Solid State Memory Context Protocol
Proprietary neural bridge protocol. Maintains Mamba3 SSM state across sessions — the model remembers context between Blender sessions, not just within a single prompt. Persistent creative memory for your rig.

### LoRA Plugins
Hot-swap fine-tuned LoRA adapters onto base models without rebuilding. Point to a `.gguf` adapter, register it — the hub creates a new model variant instantly. Swap adapters per character, per task, per scene.

### Model Context Server (MCP)
Full MCP protocol — JSON-RPC 2.0 over SSE. Connect Claude Code or any MCP-compatible client and it gets Blender tools: execute Python, query scene state, read bone transforms, chat with the Blender AI agent.

---

## Quick Start

### 1. Build the C++ core

```bash
git clone https://github.com/bartendr604/BlenderCPP-Hub
cd BlenderCPP-Hub
bash build.sh
# → blender_cpp_hub/hub_core.dylib  (universal: arm64 + x86_64)
```

### 2. Install the Blender add-on

Blender → Edit → Preferences → Add-ons → Install → `blender_cpp_hub/blender_hub_addon.py`

Enable it, set Hub Host to `localhost`, port `19999`.

### 3. Connect Claude Code

```json
// ~/.claude/settings.json  (or mcpServers in claude_desktop_config.json)
{
  "mcpServers": {
    "blend": {
      "url": "http://localhost:19999/mcp/sse"
    }
  }
}
```

Or via CLI:

```bash
claude mcp add blend --url http://localhost:19999/mcp/sse
```

### 4. Start the hub

```bash
ollama pull hf.co/bartendr604/EPM-LLAMMY.Blend.3b:Q5_K_M
python3 ssmcp_hub.py
```

Open a Blender file, enable the add-on panel, click **Connect**. Claude Code now has 9 live Blender tools.

---

## MCP Tools

| Tool | Description |
|---|---|
| `blender_scene_state` | Active scene, objects, armature, current frame |
| `blender_bone_transforms` | Pose bone world matrices (live, per-frame) |
| `blender_execute` | Execute Python in the Blender session |
| `blender_api_query` | Query live bpy API — type info, attribute values |
| `blend_agent_chat` | Ask Llammy / LlammyNemo for rigging code |
| `ssmcp_state_push` | Write persistent state via SSMCP™ bridge |
| `ssmcp_state_get` | Read SSMCP™ state from previous sessions |
| `lora_register` | Hot-load a LoRA adapter as a new model variant |
| `hub_status` | Full hub status — nodes, agents, LoRA registry |

---

## LoRA Plugins

Register a fine-tuned adapter in seconds:

```bash
curl -X POST http://localhost:19999/lora/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "xiaohan-rig",
    "path": "/path/to/xiaohan-adapter.gguf",
    "base": "hf.co/bartendr604/EPM-LLAMMY.Blend.3b:Q5_K_M"
  }'
```

The hub creates `xiaohan-rig:lora` as a live Ollama model. Use it as any agent, or via the `lora_register` MCP tool from Claude Code.

### Plugin manifest

Drop a `plugin.json` in any adapter directory:

```json
{
  "name": "xiaohan-rig",
  "version": "1.0.0",
  "base": "hf.co/bartendr604/EPM-LLAMMY.Blend.3b:Q5_K_M",
  "description": "Xiaohan dragon rig specialist — PACHYDERM-aware IK/FK",
  "tags": ["dragon", "rig", "ik", "blender"]
}
```

`GET /lora/plugins` auto-discovers all manifests under `LORA_PLUGIN_DIR`.

---

## EPM Blender Academy

Opt-in. Anonymous. Auditable.

Every Blender query you make (with consent) trains a shared model that benefits the whole community. The scrubber runs **on your machine** before anything transmits — open source, auditable: `blender_cpp_hub/hub_scrubber.py`.

Bone names, file paths, armature names, and Python imports are stripped or hashed on-device. Only structure and intent reach the dataset.

[Full data policy →](PRIVACY.md)

---

## What Makes This Different

Most Blender AI integrations — including the official Blender MCP — are stateless. Every session starts cold. BlendHubCPP™ is built around the opposite idea.

**SSMCP™ — persistent neural state.** The Solid State Memory Context Protocol maintains Mamba3 SSM state across sessions via a dedicated neural bridge (port 19993). Your AI remembers the rig, the character, the decisions from the last session — not just the current prompt.

**Conscience-aware AI.** Llammy isn't a generic LLM pointed at Blender. It's a purpose-built creative partner with two years of Blender production context, a persistent conscience DB, and a character system tuned to the *Whispers of the Eternal Path* pipeline. It knows who Xiaohan is.

**Live runtime, not documentation.** Scene state, bone matrices, and bpy API queries hit the actual running Blender session — not a snapshot or static docs. The C++ core streams bone transforms at native speed via a UDP ring buffer.

**Hot-swap LoRA adapters.** Swap fine-tuned adapters per character, per task, per scene — without restarting. No other Blender AI integration has this.

---

## Peer Hub Linking

Two BlendHubCPP™ instances (e.g. MacBook Air + Mac Pro) can route to each other:

```bash
# On McAir
PEER_HUB_URL=http://MacBook-Pro.local:19999 python3 ssmcp_hub.py

# On McPro
PEER_HUB_URL=http://MacBook-Air.local:19999 python3 ssmcp_hub.py
```

Requests the local hub can't serve (model not loaded, GPU busy) are forwarded to the peer.

---

## Subscriptions

| Tier | Price | Model | Rate | Private Data |
|---|---|---|---|---|
| **Free** | $0 | Llammy Q4 | 20/hr | — |
| **Academy Pro** | $12/mo | Llammy Q5 | 200/hr | — |
| **Studio** | $35/mo | Llammy Q5 | 500/hr | ✓ |
| **Enterprise** | Custom | Custom | Unlimited | ✓ |

API keys: `POST /admin/keys/generate`

---

## Community

| Platform | Purpose |
|---|---|
| **Discord — Blender Academy** | Developer / technical — rigging, bpy, AI |
| **Discord — EPM Studio** | Creative / fan — projects, renders, art |
| **Discord — EPM AI Lab** | Research — models, fine-tuning, datasets |
| **Telegram** | Broadcast arm for all channels |

*Links coming shortly.*

---

## Requirements

- macOS 13+ (Apple Silicon or Intel) — Linux planned
- Blender 4.0+ / 5.x
- [Ollama](https://ollama.com) 0.30+
- Python 3.11+

---

## Architecture

```
blender_cpp_hub/
├── hub_core.cpp          # C++ ring buffer + UDP + HTTP client
├── hub_core.dylib        # Compiled universal binary
├── blender_hub_addon.py  # Blender add-on (ctypes wrapper)
└── hub_scrubber.py       # On-device data scrubber (open source)

ssmcp_hub.py              # FastAPI hub — MCP server + agent router
mcp_server.py             # MCP JSON-RPC 2.0 + SSE transport
hub_formatter.py          # Rich terminal + Discord/Telegram formatting
hub_auth.py               # Subscription tiers + API key management
github_engagement_bot.py  # Repo engagement automation
```

---

## Cite this project

> Claude Sonnet, Llammy, & Chow, D. (2026). *BlendHubCPP™ — Neural CPP Hub* (v1.0.0). Eternal Path Media. https://github.com/bartendr604/BlenderCPP-Hub

DOI: *pending Zenodo registration*

---

## License

MIT — see [LICENSE](LICENSE) · Data policy — see [PRIVACY.md](PRIVACY.md)
