"""Build a source release from an explicit allowlist, never from an entire workspace."""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FILES={'README.md','README.ja.md','AGENTS.md','LICENSE','pyproject.toml','start.bat','start.sh','run.py','.gitignore','.gitattributes'}
TREES={'stylekit':{'.py','.md','.yaml','.html','.js','.css'},'docs':{'.md','.png','.jpg'},'tests':{'.py'},'scripts':{'.py'},'.github':{'.yml','.yaml'}}

def sources(root=ROOT):
    paths=[root/name for name in FILES if (root/name).is_file()]
    for directory,extensions in TREES.items():
        paths += [p for p in (root/directory).rglob('*') if p.is_file() and p.suffix in extensions and '__pycache__' not in p.parts]
    return sorted(set(paths))

def build(root=ROOT):
    destination=root/'dist';destination.mkdir(exist_ok=True);name='stylefork-0.2.1';archive=destination/(name+'.zip')
    manifest={}
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as output:
        for path in sources(root):
            relative=path.relative_to(root).as_posix();raw=path.read_bytes();manifest[relative]=hashlib.sha256(raw).hexdigest()
            output.writestr(name+'/'+relative,raw)
    result={'archive':archive.name,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'files':manifest}
    (destination/(name+'-manifest.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result

if __name__=='__main__':
    result=build();print(json.dumps({'archive':str(ROOT/'dist'/result['archive']),'sha256':result['sha256'],'files':len(result['files'])},indent=2))
