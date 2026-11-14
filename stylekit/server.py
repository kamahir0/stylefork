"""Loopback-only UI, with validated file routes and same-origin JSON writes."""
import json
import mimetypes
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from .workspace import Workspace
from .review import ReviewStore
from .storage import read_json

def serve(root,port=8767):
    workspace=Workspace(root);workspace.init();reviews=ReviewStore(root);web=Path(__file__).parent/'web'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def send(self,status,value,mime='application/json; charset=utf-8'):
            raw=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer');self.end_headers();self.wfile.write(raw)
        def dispatch(self,post=False):
            host=self.headers.get('Host','');expected={f'localhost:{self.server.server_port}',f'127.0.0.1:{self.server.server_port}'}
            if host not in expected:self.send(403,{'error':'Local access only'});return
            try:
                url=urlparse(self.path);parts=url.path.strip('/').split('/');query=parse_qs(url.query);payload={}
                if post:
                    if self.headers.get('Origin') not in (None,'http://'+host):raise ValueError('Invalid origin')
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=1_000_000 or self.headers.get_content_type()!='application/json':raise ValueError('Expected JSON (maximum 1 MB)')
                    payload=json.loads(self.rfile.read(length))
                    if not isinstance(payload,dict):raise ValueError('Expected a JSON object')
                static={'/':'studio.html','/reviews':'index.html','/app.js':'app.js','/style.css':'style.css','/studio.js':'studio.js'}
                if url.path=='/' and 'review' in query:static['/']='index.html'
                if not post and url.path in static:
                    path=web/static[url.path];self.send(200,path.read_bytes(),(mimetypes.guess_type(path.name)[0] or 'application/octet-stream')+'; charset=utf-8');return
                if not post and parts==['api','info']:
                    from . import __version__
                    result={'workspace':str(workspace.root),'version':__version__}
                elif not post and parts==['api','styles']:result=workspace.styles()
                elif not post and parts==['api','sessions']:result=workspace.sessions()
                elif not post and parts[:2]==['api','session'] and len(parts)==3:result=workspace.session(parts[2])
                elif post and parts==['api','session']:
                    result=workspace.create_session(payload['style_id'],title=payload.get('title',''))
                elif post and parts[:2]==['api','session'] and len(parts)==4 and parts[3]=='update':result=workspace.update_session(parts[2],payload)
                elif post and parts[:2]==['api','session'] and len(parts)==4 and parts[3]=='fork':
                    result=workspace.fork_session(parts[2],style_id=payload['style_id'],name=payload['name'],description=payload.get('description',''),
                                                  save_intent=payload['save_intent'],run_id=payload.get('run_id'))
                elif post and parts==['api','style']:
                    result=workspace.save_style(style_id=payload['style_id'],name=payload['name'],recipe=payload['recipe'],description=payload.get('description',''))
                elif post and parts==['api','turn']:result=workspace.create_turn(payload['session_id'],title=payload.get('title','images'),theme=payload.get('theme'))
                elif post and parts==['api','review']:
                    result=reviews.create(title=payload.get('title','画像レビュー'),batch_id=payload.get('turn_id'),experiments=payload.get('experiments'),references=payload.get('references'),labels=payload.get('labels'))
                elif not post and parts==['api','reviews']:result=reviews.list_reviews()
                elif not post and parts==['api','turns']:result=workspace.turns()
                elif not post and parts==['api','catalog']:result=reviews.catalog()
                elif not post and parts==['api','runs']:
                    result=[read_json(p) for p in sorted((workspace.data/'runs').glob('*.json'),reverse=True)]
                elif not post and parts[:2]==['api','review'] and len(parts)==3:result=reviews.get(parts[2])
                elif post and parts[:2]==['api','review'] and len(parts)==4:
                    if parts[3]=='add':result=reviews.add(parts[2],payload['experiment_id'],payload['revision'])
                    elif parts[3] in ('draft','submit'):result=reviews.save(parts[2],payload,submit=parts[3]=='submit')
                    else:raise FileNotFoundError()
                elif not post and parts==['image']:
                    path=reviews.image(query['review'][0],int(query['number'][0]));self.send(200,path.read_bytes(),mimetypes.guess_type(path.name)[0]);return
                elif not post and parts==['catalog-image']:
                    item=next((i for i in reviews.catalog() if i['experiment_id']==query['experiment'][0] and i['output_index']==int(query['index'][0])),None)
                    if not item:raise FileNotFoundError()
                    path=reviews._local_image(item['image_path']);self.send(200,path.read_bytes(),mimetypes.guess_type(path.name)[0]);return
                else:raise FileNotFoundError()
                self.send(200,result)
            except FileNotFoundError:self.send(404,{'error':'Not found'})
            except (ValueError,KeyError,TypeError,FileExistsError,TimeoutError) as exc:self.send(400,{'error':str(exc)})
            except Exception as exc:self.send(500,{'error':type(exc).__name__+': '+str(exc)})
        def do_GET(self):self.dispatch()
        def do_POST(self):self.dispatch(True)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(f'StyleFork: http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
