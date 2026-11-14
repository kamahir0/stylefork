# Existing research workspace

For a workspace that already uses `.research/state.json` and `ai/output/`:

```sh
python -m stylekit --workspace <existing-project> init --import-legacy
python -m stylekit --workspace <existing-project> serve
```

This creates immutable library copies of `style_presets` in `.stylekit/styles/`. Existing presets, images, research evaluations and Champion records are not rewritten. Repeating the import skips identical recipes and rejects a changed recipe under the same ID.

The catalog also reads existing research images and preserved snapshots. Existing `.research/reviews/<id>` review URLs remain readable. When the workspace has `.research/state.json`, new image outputs use `ai/output/` as their canonical output root; fresh workspaces use `output/`.

Ordinary image creation should then use the StyleFork session workflow. Research tracking and its Champions can remain as optional tools for deliberate experiments. Their global “active track” or latest findings must not implicitly select or change an ordinary session's style.

Review feedback remains separate from style saving. Existing historical styles without reliable parent records are imported as roots with legacy provenance; the kit does not fabricate ancestry or infer save intent from old praise.
