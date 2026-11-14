"""Agent-facing CLI. Run `python -m stylekit --help` from the kit folder."""
import argparse
import json
from pathlib import Path
from .workspace import Workspace
from .storage import read_json,atomic_write_json
from .review import ReviewStore

def _parse_labels(raw):
    if not raw:return None
    if isinstance(raw,str):raw=[raw]
    if len(raw)==1:
        val=raw[0].strip()
        if (val.startswith('{') and val.endswith('}')) or (val.startswith('[') and val.endswith(']')):
            return json.loads(val)
        p=Path(val)
        if p.is_file():return read_json(p)
        if '=' in val and val.split('=',1)[0].strip().startswith(('run-','CAND_','#')):
            k,v=val.split('=',1);return {k.strip():v.strip()}
        if val.endswith('.json'):return read_json(p)
        return [val]
    if all('=' in item and item.split('=',1)[0].strip().startswith(('run-','CAND_','#')) for item in raw):
        return {item.split('=',1)[0].strip():item.split('=',1)[1].strip() for item in raw}
    return list(raw)

def main(argv=None):
    p=argparse.ArgumentParser(description='StyleFork: immutable styles, isolated sessions, image review')
    p.add_argument('--workspace',default='.',help='Data workspace (never the kit source when preparing a release)')
    sub=p.add_subparsers(dest='cmd',required=True)
    init=sub.add_parser('init');init.add_argument('--import-legacy',action='store_true')
    init.add_argument('--comfy-url',default=None);init.add_argument('--timezone-offset',type=int,default=None)
    init.add_argument('--comfy-home',default=None);init.add_argument('--kit-home',default=None)
    migration=sub.add_parser('migrate');migration.add_argument('--apply',action='store_true',help='Copy and verify legacy data; sources are never deleted by this command')
    history=sub.add_parser('history');history.add_argument('--experiment',default=None)
    serve=sub.add_parser('serve');serve.add_argument('--port',type=int,default=8767)
    style=sub.add_parser('style').add_subparsers(dest='style_cmd',required=True)
    style.add_parser('list');show=style.add_parser('show');show.add_argument('--id',required=True)
    create=style.add_parser('create');create.add_argument('--id',required=True);create.add_argument('--name',required=True);create.add_argument('--recipe',required=True)
    session=sub.add_parser('session').add_subparsers(dest='session_cmd',required=True)
    session.add_parser('list');sc=session.add_parser('create');sc.add_argument('--style',required=True);sc.add_argument('--title',default='')
    ss=session.add_parser('show');ss.add_argument('--id',required=True)
    su=session.add_parser('update');su.add_argument('--id',required=True);su.add_argument('--patch',required=True,help='JSON file containing revision and session-only changes')
    sf=session.add_parser('fork');sf.add_argument('--id',required=True);sf.add_argument('--style-id',required=True);sf.add_argument('--name',required=True)
    sf.add_argument('--save-intent',required=True);sf.add_argument('--description',default='');sf.add_argument('--run',default=None)
    turn=sub.add_parser('turn');turn.add_argument('--session',required=True);turn.add_argument('--title',required=True);turn.add_argument('--theme',default=None)
    gen=sub.add_parser('generate');gen.add_argument('--session',required=True);gen.add_argument('--turn',required=True);gen.add_argument('--seed',type=int,default=123456);gen.add_argument('--timeout',type=int,default=600);gen.add_argument('--unload-models',action='store_true')
    free=sub.add_parser('free',help='Release ComfyUI VRAM/RAM caches and prompt history');free.add_argument('--keep-models',action='store_true');free.add_argument('--keep-history',action='store_true')
    record=sub.add_parser('record');record.add_argument('--session',required=True);record.add_argument('--turn',required=True);record.add_argument('--image',nargs='+',required=True);record.add_argument('--workflow',default=None);record.add_argument('--seed',type=int,default=123456)
    review=sub.add_parser('review').add_subparsers(dest='review_cmd',required=True)
    rc=review.add_parser('create');rc.add_argument('--turn',default=None);rc.add_argument('--experiment',nargs='*',default=[]);rc.add_argument('--reference',nargs='*',default=[]);rc.add_argument('--title',default='画像レビュー');rc.add_argument('--labels',nargs='*',default=None,help='JSON file path, inline JSON object/list, or positional label strings')
    rs=review.add_parser('show');rs.add_argument('--id',required=True);rs.add_argument('--feedback',action='store_true')
    rw=review.add_parser('wait',help='Wait for review submission (also serves UI on --port if not running)');rw.add_argument('--id',required=True);rw.add_argument('--since-revision',type=int,default=None);rw.add_argument('--timeout',type=float,default=86400);rw.add_argument('--port',type=int,default=8767)
    sub.add_parser('doctor')
    args=p.parse_args(argv);w=Workspace(args.workspace)
    if args.cmd=='init':
        result=w.init();cfg=w.config()
        for name,field in [('comfy_url','comfy_url'),('timezone_offset','timezone_offset_minutes'),('comfy_home','comfy_home'),('kit_home','kit_home')]:
            if getattr(args,name) is not None:cfg[field]=getattr(args,name)
        atomic_write_json(w.data/'config.json',cfg)
        if args.import_legacy:result['import']=w.import_legacy()
    elif args.cmd=='serve':
        from .server import serve
        serve(args.workspace,args.port);return 0
    elif args.cmd=='style':
        result=w.styles() if args.style_cmd=='list' else w.style(args.id) if args.style_cmd=='show' else w.save_style(style_id=args.id,name=args.name,recipe=read_json(args.recipe))
    elif args.cmd=='migrate':
        from .migration import migrate
        result=migrate(args.workspace,apply=args.apply)
    elif args.cmd=='history':
        path=w.data/'history/research.json';data=read_json(path) if path.exists() else {}
        from .migration import resolve_aliases
        if args.experiment:
            result={'experiment':data.get('archive',{}).get(args.experiment),'evaluations':[e for e in data.get('evaluations',{}).values() if e.get('experiment_id')==args.experiment]}
        else:result={'experiments':len(data.get('archive',{})),'evaluations':len(data.get('evaluations',{})),'findings':len(data.get('findings',[])),'tracks':list(data.get('research_tracks',{}))}
        result=resolve_aliases(result,w.root)
    elif args.cmd=='session':
        if args.session_cmd=='list':result=w.sessions()
        elif args.session_cmd=='create':result=w.create_session(args.style,title=args.title)
        elif args.session_cmd=='show':result=w.session(args.id)
        elif args.session_cmd=='update':result=w.update_session(args.id,read_json(args.patch))
        else:result=w.fork_session(args.id,style_id=args.style_id,name=args.name,description=args.description,save_intent=args.save_intent,run_id=args.run)
    elif args.cmd=='turn':result=w.create_turn(args.session,title=args.title,theme=args.theme)
    elif args.cmd=='generate':
        from .comfy import generate
        result=generate(w,args.session,args.turn,seed=args.seed,timeout=args.timeout,unload_models=args.unload_models)
    elif args.cmd=='free':
        from .comfy import free_memory
        url=w.config().get('comfy_url','http://127.0.0.1:8188')
        result=free_memory(url,unload_models=not args.keep_models,clear_history=not args.keep_history)
    elif args.cmd=='record':result=w.record_run(args.session,args.turn,args.image,seed=args.seed,workflow=read_json(args.workflow) if args.workflow else None)
    elif args.cmd=='review':
        reviews=ReviewStore(args.workspace)
        if args.review_cmd=='show':
            result=reviews.get(args.id)
            if args.feedback:result=result['submitted']
        elif args.review_cmd=='wait':
            result=reviews.wait(args.id,since_revision=args.since_revision,timeout=args.timeout,serve_port=args.port)
        else:
            from .comfy import free_memory
            free_memory(w.config().get('comfy_url','http://127.0.0.1:8188'),unload_models=True,clear_history=True)
            result=reviews.create(title=args.title,batch_id=args.turn,experiments=args.experiment,references=args.reference,labels=_parse_labels(args.labels))
            url=f'http://127.0.0.1:8767/reviews?review={result["review_id"]}'
            result['url']=url
            result['markdown_link']=f'[画像レビューを開く ({result["review_id"]})]({url})'
            result['wait_command']=f'python .agents/stylefork.py review wait --id {result["review_id"]}'
    elif args.cmd=='doctor':
        from .comfy import request
        result={'workspace':str(w.root),'styles':len(w.styles()),'python_only_ui':True,'comfy_url':w.config().get('comfy_url','http://127.0.0.1:8188')}
        try:request(result['comfy_url']+'/system_stats',timeout=3);result['comfy_reachable']=True
        except Exception as exc:result['comfy_reachable']=False;result['comfy_error']=str(exc)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
