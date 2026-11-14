# Existing research workspace

## Upgrade to the compact layout (0.2)

With writers and generation jobs stopped, run the shared kit against the project:

```sh
python /path/to/StyleFork/run.py --workspace /path/to/project migrate
python /path/to/StyleFork/run.py --workspace /path/to/project migrate --apply
```

The first command reports a plan. The second copies and verifies data into `output/`, `styles/` and hidden `.stylefork/`. Image content is deduplicated by SHA-256. Style record bytes, user feedback, workflows, review IDs and historical experiments are preserved. Source paths resolve through `.stylefork/path_aliases.json`. `history --experiment <id>` resolves old artifact locations.

The migration command does **not** delete source directories or relocate external tools. Verify all targets and the new UI before retiring old copies. Preserve all unique data. Retire only verified duplicates, obsolete implementation code and regenerable caches, using a recoverable location when available. Do not move or delete model files as part of data deduplication.

Once verified, the creation project's active root is the five-entry layout described in [PROJECT_LAYOUT.md](PROJECT_LAYOUT.md). Source directories from the previous system can then be removed from the active project. Store the shared kit and ComfyUI outside it and update their paths in the hidden configuration.

## Initial import compatibility

For a workspace that already uses `.research/state.json` and `ai/output/`:

```sh
python -m stylekit --workspace <existing-project> init --import-legacy
python -m stylekit --workspace <existing-project> serve
```

This creates immutable library copies of `style_presets`. New projects keep them in `styles/`; un-migrated 0.1 projects retain their previous location until the compact migration is run. Existing presets, images, research evaluations and Champion records are not rewritten. Repeating the import skips identical recipes and rejects a changed recipe under the same ID.

The catalog also reads existing research images and preserved snapshots. Existing `.research/reviews/<id>` review URLs remain readable. Un-migrated 0.1 workspaces can retain `ai/output/` temporarily. Fresh and compact-migrated projects always use `output/`.

Ordinary image creation should then use the StyleFork session workflow. Research tracking and its Champions can remain as optional tools for deliberate experiments. Their global “active track” or latest findings must not implicitly select or change an ordinary session's style.

Review feedback remains separate from style saving. Existing historical styles without reliable parent records are imported as roots with legacy provenance; the kit does not fabricate ancestry or infer save intent from old praise.
