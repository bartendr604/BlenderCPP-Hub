# Privacy Policy — EPM Blender Academy

*Eternal Path Media / BlenderCPP Hub*  
*Effective: June 2026*

---

## What we collect (opt-in only)

Participation in the EPM Blender Academy dataset is **entirely opt-in**.  
The checkbox in the add-on panel is **off by default**.

When enabled, the following anonymised data is sent to the Academy endpoint:

### Collected
- **Bone names** — standard rig names (Mixamo, Rigify, Metarig) are kept verbatim as they are training signal. Custom names are replaced with stable hashed tokens (e.g. `bone_a3f8c1`).
- **AI query/response pairs** — the question you asked the Blender agent and the response you received. File paths and object names are scrubbed before transmission.
- **Animation frame patterns** — bone count, frame number, FPS. No actual geometry or vertex data.
- **Blender version and platform architecture** — e.g. `4.2.0`, `arm64`.
- **Rig topology hints** — constraint types, bone hierarchy depth.

### Not collected — ever
- File paths, project names, or `.blend` file names
- IP addresses or any network identifier
- User account information or email addresses
- Scene geometry, mesh data, or render output
- Images, textures, or any visual content
- Any data from scenes where the hub bridge is disabled

---

## How scrubbing works

Every telemetry record passes through `hub_scrubber.py` **on your local machine** before it is transmitted. The scrubber source code is in this repository — you can read and audit it yourself.

The scrubber:
- Strips all file paths matching common path patterns (`/Users/...`, `C:\...`)
- Replaces email addresses with `<email>`
- Replaces IP addresses with `<ip>`
- Hashes custom object and armature names with SHA-256 (first 6 hex chars)
- Keeps standard bone names (they are the training signal, not identifiers)

---

## Where data goes

Scrubbed records are stored in JSONL batch files and periodically added to the public dataset:

**[huggingface.co/datasets/bartendr604/llammy-blender-python-dataset](https://huggingface.co/datasets/bartendr604/llammy-blender-python-dataset)**

This dataset is public. Records contributed under the free tier become part of the commons. Studio tier subscribers can opt out of dataset contribution entirely (private data mode).

---

## Opting out

Uncheck **"Contribute to EPM Blender Academy"** in the add-on panel at any time.  
No data is collected when unchecked. No data is stored or transmitted retroactively.

---

## Contact

d.thebartender@gmail.com  
Eternal Path Media
