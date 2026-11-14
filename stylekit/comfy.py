"""Optional ComfyUI adapter. No account, model download, or generation is triggered on startup."""
import json
import time
import tempfile
import urllib.request
import urllib.parse
from pathlib import Path
from .recipe import assemble_workflow

LOW_RAM_BYTES = 6 * 1024 * 1024 * 1024
LOW_VRAM_BYTES = 1 * 1024 * 1024 * 1024


def request(url, payload=None, timeout=20):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read()
        return json.loads(raw) if raw.strip() else {}


def free_memory(url, *, prompt_id=None, unload_models=False, clear_history=False):
    base = str(url).rstrip('/')
    info = {'comfy_url': base, 'freed': False, 'unload_models': bool(unload_models), 'clear_history': bool(clear_history)}
    try:
        if clear_history:
            request(base + '/history', {'clear': True}, timeout=5)
        elif prompt_id:
            request(base + '/history', {'delete': [prompt_id]}, timeout=5)
    except Exception:
        pass
    if not unload_models:
        try:
            stats = request(base + '/system_stats', timeout=3)
            ram_free = stats.get('system', {}).get('ram_free')
            devs = stats.get('devices') or []
            vram_free = devs[0].get('vram_free') if devs else None
            if (isinstance(ram_free, (int, float)) and ram_free < LOW_RAM_BYTES) or (
                isinstance(vram_free, (int, float)) and vram_free < LOW_VRAM_BYTES
            ):
                unload_models = True
                info['unload_models'] = True
                info['auto_unloaded_low_memory'] = True
        except Exception:
            pass
    try:
        request(base + '/free', {'unload_models': bool(unload_models), 'free_memory': True}, timeout=10)
        info['freed'] = True
    except Exception as exc:
        info['error'] = str(exc)
    return info


def generate(workspace, session_id, turn_id, *, seed=123456, timeout=600, unload_models=False):
    session = workspace.session(session_id)
    turn = workspace.turn(turn_id)
    if turn['session_id'] != session_id:
        raise ValueError('Turn belongs to another session')
    url = workspace.config().get('comfy_url', 'http://127.0.0.1:8188').rstrip('/')
    recipe = session['working_recipe']
    graph, _ = assemble_workflow(
        {'preset_id': session['base_style_id'], **recipe},
        subject_prompt=session['requirements'],
        negative_extra=session['negative_extra'],
        seed=seed,
        filename_prefix=turn['theme'] + '/' + turn_id + '/image',
    )
    queued = request(url + '/prompt', {'prompt': graph})
    prompt_id = queued['prompt_id']
    deadline = time.monotonic() + timeout
    finished = False
    try:
        while time.monotonic() < deadline:
            history = request(url + '/history/' + urllib.parse.quote(prompt_id))
            entry = history.get(prompt_id)
            if entry:
                if entry.get('status', {}).get('status_str') == 'error':
                    finished = True
                    raise RuntimeError('ComfyUI generation failed: ' + str(entry.get('status')))
                images = [
                    image
                    for out in entry.get('outputs', {}).values()
                    for image in out.get('images', [])
                    if image.get('type', 'output') == 'output'
                ]
                if images:
                    finished = True
                    with tempfile.TemporaryDirectory() as directory:
                        paths = []
                        for index, image in enumerate(images):
                            query = urllib.parse.urlencode(
                                {key: image.get(key, default) for key, default in [('filename', ''), ('subfolder', ''), ('type', 'output')]}
                            )
                            with urllib.request.urlopen(url + '/view?' + query, timeout=60) as response:
                                raw = response.read()
                            path = Path(directory) / (str(index) + Path(image['filename']).suffix)
                            path.write_bytes(raw)
                            paths.append(path)
                        return workspace.record_run(session_id, turn_id, paths, seed=seed, workflow=graph, session_snapshot=session)
            time.sleep(0.75)
        raise TimeoutError('ComfyUI did not finish before the timeout; prompt ID: ' + prompt_id)
    finally:
        if finished:
            free_memory(url, prompt_id=prompt_id, unload_models=unload_models)
