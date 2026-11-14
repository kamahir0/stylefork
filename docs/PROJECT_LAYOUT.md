# Minimal creation project

A creation project has five root entries:

```text
AGENTS.md
.agents/
output/
styles/
.stylefork/
```

`output/<concept>/<turn>/` contains the images a human reviews. A turn can contain several generation batches. Workflow JSON is stored internally in `.stylefork/workflows/`. `styles/<style_id>.json` contains immutable recipes and their parent lineage. Creating images and evaluating them never edits a saved style.

`.stylefork/` holds configuration, sessions, turns, run provenance, reviews, image snapshots, references, logs and imported historical records. It is hidden on Windows as well as dot-prefixed on other systems. Historical experiments and feedback remain queryable with `history`; they are not automatically used as current session defaults.

The shared kit checkout and ComfyUI installation belong outside creation projects. `kit_home` and optional `comfy_home` in `.stylefork/config.json` can be absolute or project-relative paths. `comfy_url` is the generation endpoint; it is independent of either filesystem location. ComfyUI remains a separately managed service, not a project dependency copied into every workspace.

`init` creates the project instructions and `.agents/stylefork.py`. Run `python .agents/stylefork.py ...` from the project to select that workspace automatically. An existing root AGENTS.md is never overwritten by normal initialization. When moving a project or shared installation, update `kit_home` with the external kit's `init --kit-home ...` command.

The code repository contains its own development files (`tests`, CI, documentation, packaging scripts). Those belong to the shared tool checkout, not the creation project's root. Build environments and release staging files are disposable; models and the actual ComfyUI runtime are not.
