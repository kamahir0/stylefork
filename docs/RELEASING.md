# Release procedure

1. Run `python -m unittest discover -s tests` and JavaScript syntax checks.
2. Run `python scripts/release.py`. It creates an explicit-source-allowlist ZIP and manifest in ignored `dist/`.
3. Extract the ZIP to a fresh temporary directory, run the tests, and start the UI against a separate empty workspace. No model, account or ComfyUI server should be required for the UI.
4. Optionally build an installable wheel with `python -m build`, install it into a clean environment and verify the packaged web assets.
5. Check `git ls-files`: no `.stylekit`, `.research`, workspaces, generated art, model files, credentials or private IDs.
6. Commit and push to the intended repository. Tag the tested version and upload the tested ZIP plus SHA-256 manifest as GitHub release assets.

The source repository is MIT licensed. It contains no Charakuru assets/code or bundled checkpoints, LoRAs, illustration references or personal research history. Demo artifacts used in testing must be synthetic and clearly identified as test data.
