---
name: image-workflow
description: Create and review images in StyleFork using immutable saved styles, isolated working sessions, turn folders, and explicit style forks. Use for this kit's image creation and style-saving requests, not unrelated image editing or real-world art advice.
---

# Image workflow

Read the repository `AGENTS.md`. Use `python -m stylekit --workspace <data-folder> ...` from the kit checkout. First run `doctor`; inspect `style list` and the session explicitly associated with the current chat. See `docs/TUTORIAL.md` for command examples and `docs/ARCHITECTURE.md` for the data model.

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

## Optional Google Drive

Use `drive-plan --turn <id>` for an image-only synchronization plan. If a Drive connector is available and the user wants synchronization, verify the destination root and create the same concept/turn hierarchy. Reuse verified existing file IDs for updates. Before moves, read current parents; after writes, verify folder placement. Keep documents, model files and credentials local. Do not assume a personal Drive root or a particular Drive CLI.
