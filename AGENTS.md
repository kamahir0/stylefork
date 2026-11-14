# StyleFork agent entry point

Read `.agents/skills/image-workflow/SKILL.md` when creating images, reviewing results, or saving a style. The human owns visual judgments and the decision to save a new style; the agent handles tools, generation settings, provenance and review preparation.

Run `python -m stylekit --help` from this repository. Always pass `--workspace <data-folder>` BEFORE the subcommand when the user's images live elsewhere. Do not assume the source checkout is the data workspace. Start with `doctor`, then list saved styles and the relevant session. Use explicit session and turn IDs, not global “latest” state, in concurrent chats.

- Saved styles are immutable. Never edit their JSON, recompute their hashes to hide edits, overwrite an existing ID, or change another session's base.
- Requirements and one-off exclusions stay in the session. Only intentional style changes go into `adjustments`; do not infer saved style changes from praise, review scores, or generation alone.
- Create a fork ONLY after the user explicitly requests saving a new style. Preserve the request in `save_intent`, choose a new ID and retain its parent. Do not automatically select the new fork for other sessions.
- Record every generated image with the exact effective recipe, requirements, seed, workflow and session revision. When saving the atmosphere of a particular image, fork with `--run <run_id>` so later changes cannot replace its source recipe.
- Bundle the current turn's candidates and requested historical references into one numbered review. The UI supports fullscreen, arrows, enlarging and side-by-side comparisons. Read submitted feedback, not unfinished drafts.
- Keep model files, accounts, credentials, private images, workspaces and generated outputs out of the source repository and release archives.

Use `python -m unittest discover -s tests` for the kit and `python scripts/release.py` to build an allowlisted source ZIP. See `docs/ARCHITECTURE.md`, `docs/TUTORIAL.md` and `docs/RELEASING.md`.
