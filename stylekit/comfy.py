"""Optional ComfyUI adapter. No account, model download, or generation is triggered on startup."""
import json
import time
import tempfile
import urllib.request
import urllib.parse
from pathlib import Path
from .recipe import assemble_workflow

def request(url,payload=None,timeout=20):
    data=json.dumps(payload).encode() if payload is not None else None
    req=urllib.request.Request(url,data=data,headers={'Content-Type':'application/json'} if data else {})
    with urllib.request.urlopen(req,timeout=timeout) as response:return json.load(response)

def generate(workspace,session_id,turn_id, *, seed=123456, timeout=600):
    session=workspace.session(session_id);turn=workspace.turn(turn_id)
    if turn['session_id']!=session_id:raise ValueError('Turn belongs to another session')
    url=workspace.config().get('comfy_url','http://127.0.0.1:8188').rstrip('/')
    recipe=session['working_recipe']
    graph,_=assemble_workflow({'preset_id':session['base_style_id'],**recipe},subject_prompt=session['requirements'],
                             negative_extra=session['negative_extra'],seed=seed,filename_prefix=turn['theme']+'/'+turn_id+'/image')
    queued=request(url+'/prompt',{'prompt':graph});prompt_id=queued['prompt_id'];deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        history=request(url+'/history/'+urllib.parse.quote(prompt_id));entry=history.get(prompt_id)
        if entry:
            if entry.get('status',{}).get('status_str')=='error':raise RuntimeError('ComfyUI generation failed: '+str(entry.get('status')))
            images=[image for out in entry.get('outputs',{}).values() for image in out.get('images',[]) if image.get('type','output')=='output']
            if images:
                with tempfile.TemporaryDirectory() as directory:
                    paths=[]
                    for index,image in enumerate(images):
                        query=urllib.parse.urlencode({key:image.get(key,default) for key,default in [('filename',''),('subfolder',''),('type','output')]})
                        with urllib.request.urlopen(url+'/view?'+query,timeout=60) as response:raw=response.read()
                        path=Path(directory)/(str(index)+Path(image['filename']).suffix);path.write_bytes(raw);paths.append(path)
                    return workspace.record_run(session_id,turn_id,paths,seed=seed,workflow=graph,session_snapshot=session)
        time.sleep(.75)
    raise TimeoutError('ComfyUI did not finish before the timeout; prompt ID: '+prompt_id)
