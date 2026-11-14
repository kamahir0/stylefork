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
    text=PROJECT_GUIDE
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
    skill=agents/'skills/stylefork-project/SKILL.md'
    if not skill.exists():
        atomic_write_text(skill,(Path(__file__).parent/'resources/image-workflow/SKILL.md').read_text(encoding='utf-8'))
        atomic_write_text(skill.parent/'agents/openai.yaml',(Path(__file__).parent/'resources/image-workflow/agents/openai.yaml').read_text(encoding='utf-8'))

PROJECT_GUIDE = """# StyleFork creation project

Use `python .agents/stylefork.py <command...>` from this project. The helper selects this project and finds the external shared kit via `.stylefork/config.json`.

Read `.agents/skills/stylefork-project/SKILL.md` for image generation, review and explicit style saving. The shared kit's AGENTS.md is for kit development; it is not a dependency of this creation workflow. This `AGENTS.md` and `.agents/` are initialized with standard defaults and may be customized for project- or user-specific workflows; `init` preserves existing instructions and skills.

Keep images in `output/<concept>/<turn>/`, immutable saved styles in `styles/`, and all internal state under `.stylefork/`. Use explicit session and turn IDs. Requirements and one-off exclusions belong to the session. Generation and evaluation never edit a saved style; only an explicit user save request creates a fork. Review current and past images with stable short numbers.

Always format the review URL returned by `review create` as a clickable Markdown link (`[画像レビューを開く (<review_id>)](http://127.0.0.1:8767/reviews?review=<review_id>)`) — never wrap the URL in backticks. Right after `review create`, start `python .agents/stylefork.py review wait --id <review_id>` as a background task (`WaitMsBeforeAsync: 500`, `IsDaemon: false`) before ending the turn so the session automatically resumes when the user clicks "評価を確定". After reading submitted feedback, analyze and report findings/proposals and wait for user instructions by default; only start generating the next batch immediately if the user explicitly requested next generation in the review notes or chat.

Do not use global active-session state or create legacy research/evidence bookkeeping. Fresh projects need no migration records. The kit does not rely on `.agents/rules/` for Codex instructions.
"""
