# StyleFork development

This repository is the shared kit source, not a creation project. User-facing instructions are packaged in `stylekit/resources/image-workflow/SKILL.md` and installed into creation projects by `init`.

Read `docs/ARCHITECTURE.md` and `docs/PROJECT_LAYOUT.md` before changing data formats. Keep private images, credentials, models and workspaces out of source control and releases. Use an explicit external `--workspace` when exercising the CLI with project data.

Preserve product contracts: saved styles are immutable; session adjustments are isolated; only explicit save intent creates a fork; runs record effective recipes and workflows; submitted feedback is distinct from drafts. Do not invent provenance for imported images.

Run `python -B -m unittest discover -s tests` and syntax checks for changed JavaScript. Include focused regression coverage for changed behavior. Build allowlisted ZIPs with `python -B scripts/release.py` and verify both fresh ZIP and installed wheel initialization. See `docs/RELEASING.md` before publishing.
