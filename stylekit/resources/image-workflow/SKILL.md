---
name: stylefork-project
description: Create and review images in StyleFork using immutable saved styles, isolated working sessions, turn folders, and explicit style forks. Use for this kit's image creation and style-saving requests, not unrelated image editing or real-world art advice.
---

# Image workflow

Use `python .agents/stylefork.py <command...>` from this creation project. The helper selects this project and locates the shared kit through `.stylefork/config.json`. First run `doctor`, then inspect `style list` and the explicit session associated with this chat. Use command `--help` for arguments. The shared kit's AGENTS.md is for development and is not required for image creation.

Keep images in `output/<concept>/<turn>/`, saved styles in `styles/`, and settings, sessions, turns, runs, workflows, snapshots and reviews under `.stylefork/`. A fresh project requires no legacy history, media index, path aliases or migration records. Never use global active-session state.

## Choose a base and isolate work

Use the saved style the user selected. If none is clear, inspect the UI's session or ask for a style preference. Start a separate session for a new chat. Never copy a previous chat's most recent working recipe, prompt, negative prompt, global active research track or tool hints into a fresh session by default.

Keep subject, scene, costume, props and one-off exclusions in `requirements` / `negative_extra`. Translate the user's brief into model-appropriate prompt tokens when needed. Put only intentional changes to line, paint, palette, atmosphere and technical recipe settings into this session's `adjustments`. `session update --patch <file>` requires the current revision. It rebuilds the working recipe from the pinned base.

## Generate and show

Create one `turn --session <id> --title <short_title> --theme <concept>` per image-generating exchange. Reuse that turn ID for all batches in the exchange. `generate --session <id> --turn <id>` invokes the configured ComfyUI server only when explicitly called. Ensure the model and required nodes exist; do not silently switch models or strip unsupported settings.

If using another generator or an external workflow, record the actual image and workflow with `record`, and keep the session recipe aligned with the settings actually used. Treat incomplete external provenance as incomplete, rather than claiming exact reproduction. Model files and reference art are not kit assets.

Create a numbered review with `review create --turn <id> --reference <past_run_or_experiment_ids...>`, using `--labels <json>` for short human-readable names. Include the past references actually needed for this comparison. Give the returned review URL. Do not ask the user to find output files or copy long IDs. The viewer supports enlarging, side-by-side comparisons and fullscreen (F, arrows, bottom-left filmstrip that hides on inactivity).

## Read feedback and fork only on request

Read `review show --id <id> --feedback` when the user reports finishing. A null result means there is no submitted feedback yet; do not treat a draft as a final judgment. Keep the review ID scoped to the chat. General ratings are not permission to save or modify a style.

When the user explicitly asks to save an atmosphere/style, select the relevant session or run. Explain which reusable changes are being saved and which requirements remain specific to the image. Use `session fork` with a new style ID, name and the user's actual request as `--save-intent`. For a particular image, include `--run <run_id>` so later adjustments cannot replace its source recipe.

Never edit saved style JSON, overwrite a style ID, recompute a hash to hide edits, or change another session's base. Saving a fork does not automatically select it elsewhere. A positive review, a favorite image or a successful generation alone does not create a fork.

## Project customization

`init` creates a standard project `AGENTS.md` and this skill if they do not exist, and preserves them on subsequent runs. Projects may customize `AGENTS.md`, add project-specific skills or scripts under `.agents/`, or place an optional local hook at `.stylefork/hooks/on_review_submit.py` (invoked with JSON on stdin when a review submission is saved) while keeping saved styles immutable and session work isolated.
