# Data model and invariants

The Python standard library serves a buildless HTML/CSS/JavaScript app on loopback. It does not invoke a language model. A coding agent uses the CLI against an explicit workspace.

## Saved style

An immutable JSON record holds `style_id`, a reusable `recipe`, its canonical SHA-256, a record hash, optional parent ID/hash, and source provenance. Exclusive creation rejects repeated IDs. Reads verify integrity. Generating, reviewing and editing sessions never write this file.

A recipe consists of `style_config` (checkpoint, LoRAs, CLIP, sampler, resolution, hires/detailer configuration) and `prompt_template` (style expressions and style-side negatives). Explicit atmosphere expressions can be part of the recipe. Scene, subject, costume and prop tokens belong in requirements. Token checks are conservative guardrails, not a complete semantic classifier; the agent must still separate these concepts correctly.

## Session

A session pins a saved style ID and hash. It owns mutable `requirements`, `negative_extra`, explicit `adjustments` and an effective `working_recipe`. Updating it rebuilds from the pinned base, never a global most-recent recipe. A revision check protects against stale browser tabs. There is no global selected style or active session.

## Turn and run

A turn owns one concept/thread directory and groups all batches produced for that exchange. A run records its session revision, base hash, effective recipe, requirements, one-off negatives, seed, actual workflow, image paths and immutable image snapshots. External registration must supply the actual workflow when available; an assembled recipe is not proof that an external generator used it.

Forking a session creates another immutable style. Forking with a run ID takes that run's recipe, even if the session has since changed. Requirements and one-off negatives are never copied. A save intent is required and recorded. This is an audit field; the agent must obtain the intent from the user rather than invent it.

## Review

A review pins a numbered image set. Adding references appends numbers. Drafts are separate from explicit submissions; each submission is retained. General good/bad verdicts do not imply a style save, an attribute ranking or a Champion promotion. Existing legacy review sets and research archives are supported through a read adapter.

## Boundaries

- UI and runtime data require no third-party Python packages.
- Host and Origin checks restrict local writes; image routes serve only allowlisted, workspace-contained files.
- The UI contains no arbitrary command execution endpoint. Copying a request does not run an agent. If a creation project defines `.stylefork/hooks/on_review_submit.py`, submitting a review runs that local script with submission metadata on stdin after persisting `feedback.json`.
- ComfyUI executes generation only through an explicit CLI action. The built-in graph targets standard SD/SDXL-style models; other architectures need their own adapter.
- External storage or cloud synchronization is outside the kit's scope and belongs to project-specific agent instructions.
- The release allowlist excludes runtime data, models, secrets and images. The source ZIP and installed wheel are tested independently.
