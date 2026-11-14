"""Small, dependency-free storage primitives."""
from __future__ import annotations
import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def make_id(prefix):
    return prefix + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]

def safe_id(value):
    if not isinstance(value,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}",value):
        raise ValueError("Use an ID containing letters, numbers, hyphens or underscores")
    return value

def sha256_bytes(raw): return hashlib.sha256(raw).hexdigest()
def sha256_file(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): digest.update(chunk)
    return digest.hexdigest()
def digest(value): return sha256_bytes(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
def rel_posix(path,root): return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
def read_json(path): return json.loads(Path(path).read_text(encoding='utf-8'))

def atomic_write_bytes(path,raw):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.'+path.name,suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as out: out.write(raw);out.flush();os.fsync(out.fileno())
        for attempt in range(8):
            try: os.replace(name,path);break
            except PermissionError:
                if attempt==7: raise
                time.sleep(.05*(attempt+1))
    finally:
        if Path(name).exists():Path(name).unlink()
def atomic_write_text(path,value): atomic_write_bytes(path,value.encode('utf-8'))
def atomic_write_json(path,value): atomic_write_text(path,json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def create_json(path,value):
    """Exclusive creation: saved style IDs can never be overwritten."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    raw=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    with path.open('xb') as stream: stream.write(raw);stream.flush();os.fsync(stream.fileno())

class ResearchLock:
    """Short-lived cross-process directory lock; timeouts never delete another writer's lock."""
    def __init__(self,path,timeout_sec=10):self.path=Path(path);self.timeout=timeout_sec
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True);deadline=time.monotonic()+self.timeout
        while True:
            try:self.path.mkdir();return self
            except FileExistsError:
                if time.monotonic()>deadline:raise TimeoutError('Workspace is busy; retry after the other operation finishes')
                time.sleep(.05)
    def __exit__(self,*_):self.path.rmdir()
