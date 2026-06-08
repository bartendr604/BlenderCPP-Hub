# BlenderCPP Hub

**Real-time C++ AI bridge for Blender — EPM Blender Academy**

*© 2025–2026 Eternal Path Media / D. Chow / Claude Sonnet / Llammy — MIT License*

---

BlenderCPP Hub connects Blender directly to local AI models at C++ speed.  
Bone matrices, rig queries, and animation data flow through a native shared library — no Python bottleneck on the hot path.

Built and used in production at **Eternal Path Media** for rigging and animating the EPM character roster.

---

## What it does

- **Real-time bone streaming** — C++ ring buffer pushes bone matrices every frame via UDP, zero Python overhead in the frame callback
- **In-Blender AI assistant** — ask the Blender agent about IK, rigging, GeoNodes, bpy — get working code back
- **SSMCP bridge** — Solid State Memory Context Protocol, connects to your local Ollama fleet via the hub
- **EPM Blender Academy** — opt-in anonymous usage data trains better Blender AI models. Your queries improve the shared model for everyone.

---

## Quick start

### 1. Build the C++ library

```bash
git clone https://github.com/bartendr604/BlenderCPP-Hub
cd BlenderCPP-Hub
bash build.sh
# → hub_core.dylib (macOS universal: arm64 + x86_64)
```

### 2. Install the Blender add-on

Blender → Edit → Preferences → Add-ons → Install from file → `blender_hub_addon.py`

### 3. Start Ollama + the SSMCP Hub

```bash
ollama serve
# pull a model
ollama pull hf.co/bartendr604/EPM-LLAMMY.Blend.3b:Q5_K_M
```

### 4. Enable in Blender

3D Viewport → Sidebar (N) → EPM → SSMCP CPP Hub → **Start Hub**

---

## EPM Blender Academy

The Academy is a shared AI commons for Blender artists and riggers.

When you opt in (`Contribute to EPM Blender Academy` checkbox), anonymised usage data is collected:

| Collected | NOT collected |
|---|---|
| Bone names (standard rigs kept verbatim) | File paths or project names |
| AI query / response pairs (paths scrubbed) | IP addresses or user identity |
| Animation frame patterns | Scene geometry or render output |
| Blender version, platform arch | Any personally identifiable info |

All records pass `hub_scrubber.py` **on your machine** before transmission. The scrubber is open source — you can audit exactly what gets stripped.

Dataset: [huggingface.co/datasets/bartendr604/llammy-blender-python-dataset](https://huggingface.co/datasets/bartendr604/llammy-blender-python-dataset)

---

## Community

| | |
|---|---|
| Discord — Blender Academy | *Coming soon* |
| Discord — EPM Studio | *Coming soon* |
| Telegram | *Coming soon* |

---

## Subscriptions

| Tier | Price | What you get |
|---|---|---|
| **Free** | $0 | Add-on, community models, Academy Discord |
| **Academy Pro** | $12/mo | Q5 priority inference, early model access, Pro role |
| **Studio** | $35/mo | Private data mode, commercial license, custom system prompt |
| **Enterprise** | Custom | Self-hosted, SLA, custom fine-tune on your characters |

---

## Requirements

- macOS (Apple Silicon or Intel) — Linux support planned
- Blender 4.0+
- [Ollama](https://ollama.com) running locally
- Python 3.11+

---

## License

MIT — see [LICENSE](LICENSE)  
Data policy — see [PRIVACY.md](PRIVACY.md)
