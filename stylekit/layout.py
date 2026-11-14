"""Project layout: human-facing output/styles; implementation state stays in one directory."""
from pathlib import Path
from .storage import atomic_write_text, atomic_write_json

def paths(root):
    root=Path(root).resolve()
    modern=(root/'.stylefork/config.json').exists() or not (root/'.stylekit/config.json').exists()
    data=root/('.stylefork' if modern else '.stylekit')
    output=root/('output' if modern or not (root/'.research/state.json').exists() else 'ai/output')
    styles=root/'styles' if modern else data/'styles'
    return data,output,styles

def scaffold(root,config):
    root=Path(root);agents=root/'.agents';agents.mkdir(parents=True,exist_ok=True)
    import os
    if os.name=='nt':
        import ctypes
        state=root/'.stylefork'
        attributes=ctypes.windll.kernel32.GetFileAttributesW(str(state))
        if attributes!=-1:ctypes.windll.kernel32.SetFileAttributesW(str(state),attributes|2)
    text='''# StyleFork project

This is a creation project, not the kit source checkout. Use `python .agents/stylefork.py <command...>` from this directory. The helper selects this project automatically and locates the shared kit through `.stylefork/config.json`.

Human-facing files: `output/` contains generated images grouped by concept/turn; `styles/` contains immutable saved styles. Settings, workflows, sessions, reviews, references and research history are under `.stylefork/`.

Select an explicit saved style and a session for this chat. Keep requirements and one-off exclusions in the session. Generation and evaluation never edit a saved style. Create a new fork only after an explicit user save request. Review current and past images together with stable short numbers.

When available, read the shared kit's `AGENTS.md` and `.agents/skills/image-workflow/SKILL.md`; an installed wheel also exposes the commands through `python .agents/stylefork.py --help`. Do not recreate retired `.research`, `.evidence-harness`, `research_ops`, or root-level wrapper scripts. Historical records live under `.stylefork/history/`, not in active generation defaults. Historical file locations resolve through `.stylefork/path_aliases.json` and `history --experiment <id>`.
'''
    if not (root/'AGENTS.md').exists():atomic_write_text(root/'AGENTS.md',text)
    helper='''"""Project-bound launcher. The shared kit and ComfyUI live outside this project."""
import json, sys
from pathlib import Path
sys.dont_write_bytecode = True
root = Path(__file__).resolve().parents[1]
config = json.loads((root / ".stylefork/config.json").read_text(encoding="utf-8"))
kit = Path(config["kit_home"])
if not kit.is_absolute(): kit = (root / kit).resolve()
if not (kit / "stylekit" / "__main__.py").is_file(): raise SystemExit("Shared StyleFork installation not found; update kit_home in .stylefork/config.json")
sys.path.insert(0, str(kit))
from stylekit.__main__ import main
raise SystemExit(main(["--workspace", str(root), *sys.argv[1:]]))
'''
    atomic_write_text(agents/'stylefork.py',helper)
    rule=agents/'rules/stylefork.md'
    if not rule.exists():atomic_write_text(rule,'''---
trigger: always_on
description: "Use this project's compact StyleFork workflow and state directory"
---
Read root AGENTS.md. This project uses StyleFork and .stylefork as its active state. The user-approved layout replaces earlier research/evidence-harness bookkeeping here. Do not recreate .research, .evidence-harness, research_ops, root wrappers, or global active-session state. Use python .agents/stylefork.py with an explicit saved style, session and turn. Only explicit user save intent creates an immutable style fork. Keep images in output/concept/turn and machine records in .stylefork.
''')
    skill=agents/'skills/stylefork-project/SKILL.md'
    if not skill.exists():atomic_write_text(skill,'''---
name: stylefork-project
description: Create and review images in this StyleFork project using saved styles, isolated sessions and explicit forks. Not for unrelated tasks.
---
Read root AGENTS.md. Use `python .agents/stylefork.py ...` for this project. Read `.stylefork/config.json` to find the shared kit, then read its AGENTS.md and image-workflow skill. Keep output images under output/concept/turn and reusable styles under styles. All other project data stays under .stylefork. Do not create legacy research roots or global active-session state.
''')
