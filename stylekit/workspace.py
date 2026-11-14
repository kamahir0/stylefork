"""Immutable styles, isolated working sessions, and turn-scoped image provenance."""
from __future__ import annotations
import copy
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .storage import (ResearchLock, atomic_write_json, atomic_write_bytes, create_json,
                      read_json, safe_id, make_id, now_iso, digest, sha256_file, rel_posix)
from .recipe import split_prompt_tokens, classify_prompt_token, assemble_workflow

def merge_config(base, patch):
    if not isinstance(patch,dict): raise ValueError('Config patch must be an object')
    result=copy.deepcopy(base)
    for key,value in patch.items():
        if key not in result: raise ValueError('Unknown recipe config field: '+key)
        result[key]=merge_config(result[key],value) if isinstance(value,dict) and isinstance(result[key],dict) else copy.deepcopy(value)
    return result

def check_recipe(recipe, *, legacy=False):
    if not isinstance(recipe,dict) or not isinstance(recipe.get('style_config'),dict) or not isinstance(recipe.get('prompt_template'),dict):
        raise ValueError('A style needs style_config and prompt_template')
    template=recipe['prompt_template']
    if not isinstance(template.get('default_negative',''),str):raise ValueError('Negative prompt must be text')
    for field in ['style_prefix','style_suffix']:
        tokens=template.get(field,[])
        if not isinstance(tokens,list) or not all(isinstance(v,str) for v in tokens):raise ValueError('Style tokens must be lists of text')
    tokens=[*template.get('style_prefix',[]),*template.get('style_suffix',[]),*split_prompt_tokens(template.get('detailer_positive_template',''))]
    leaks=[t for t in tokens if classify_prompt_token(t) not in (None,'expression_drift')]
    leaks += [t for t in split_prompt_tokens(template.get('default_negative',''))
              if classify_prompt_token(t) not in (None,'expression_drift')]
    if leaks and not legacy:raise ValueError('Scene/prop/subject tokens belong in session requirements, not a saved style: '+', '.join(leaks))
    return recipe

class Workspace:
    def __init__(self,root):
        from .layout import paths
        self.root=Path(root).resolve();self.data,self.output,self.styles_dir=paths(self.root)

    def init(self):
        self.data.mkdir(parents=True,exist_ok=True)
        if not (self.data/'config.json').exists():
            create_json(self.data/'config.json',{'schema_version':2,'kit_home':str(Path(__file__).resolve().parents[1]),'comfy_home':None,'comfy_url':'http://127.0.0.1:8188','timezone_offset_minutes':None})
        self.output.mkdir(parents=True,exist_ok=True);self.styles_dir.mkdir(parents=True,exist_ok=True)
        if self.data.name=='.stylefork':
            from .layout import scaffold
            scaffold(self.root,self.config())
        return {'workspace':str(self.root),'data':str(self.data),'output':str(self.output)}

    def config(self):return read_json(self.data/'config.json') if (self.data/'config.json').exists() else {}

    def style(self,style_id):
        record=read_json(self.styles_dir/(safe_id(style_id)+'.json'))
        check={k:v for k,v in record.items() if k!='record_sha256'}
        if record.get('record_sha256')!=digest(check) or record.get('recipe_sha256')!=digest(record['recipe']):
            raise ValueError('Saved style integrity check failed: '+style_id)
        return record

    def styles(self):return [self.style(p.stem) for p in sorted(self.styles_dir.glob('*.json'))]

    def save_style(self, *, style_id, name, recipe, description='', parent_id=None, source=None, legacy=False):
        self.init();safe_id(style_id);check_recipe(recipe,legacy=legacy)
        if not isinstance(name,str) or not name.strip():raise ValueError('A saved style needs a name')
        parent=self.style(parent_id) if parent_id else None
        record={'schema_version':1,'style_id':style_id,'name':name,'description':description,'created_at':now_iso(),
                'parent_style_id':parent_id,'parent_recipe_sha256':parent['recipe_sha256'] if parent else None,
                'recipe':copy.deepcopy(recipe),'recipe_sha256':digest(recipe),'source':source or {}}
        record['record_sha256']=digest(record)
        with ResearchLock(self.data/'.style-lock'):create_json(self.styles_dir/(style_id+'.json'),record)
        return record

    def import_legacy(self):
        """Copy existing presets into the new library without changing the old records."""
        state=read_json(self.root/'.research/state.json');created=[];skipped=[]
        for preset_id,preset in state.get('style_presets',{}).items():
            recipe={k:copy.deepcopy(preset[k]) for k in ['style_config','prompt_template']}
            if (self.styles_dir/(safe_id(preset_id)+'.json')).exists():
                if self.style(preset_id)['recipe_sha256']!=digest(recipe):raise ValueError('Legacy preset changed; import with a new style ID: '+preset_id)
                skipped.append(preset_id);continue
            self.save_style(style_id=preset_id,name=preset['name'],description=preset.get('description',''),recipe=recipe,
                            source={'legacy_preset_id':preset_id,'source_experiment_id':preset.get('source_experiment_id')},legacy=True)
            created.append(preset_id)
        return {'created':created,'already_imported':skipped}

    def session(self,session_id):
        session=read_json(self.data/'sessions'/(safe_id(session_id)+'.json'))
        base=self.style(session['base_style_id'])
        if base['recipe_sha256']!=session['base_recipe_sha256']:raise ValueError('Session base style changed')
        return session

    def sessions(self):return [self.session(p.stem) for p in sorted((self.data/'sessions').glob('*.json'),reverse=True)]

    def create_session(self,style_id, *, title='', session_id=None):
        base=self.style(style_id);session_id=safe_id(session_id) if session_id else make_id('session')
        session={'session_id':session_id,'title':title or base['name'],'created_at':now_iso(),'updated_at':now_iso(),'revision':0,
                 'base_style_id':style_id,'base_recipe_sha256':base['recipe_sha256'],'requirements':'','negative_extra':'',
                 'adjustments':{'positive_add':[],'positive_remove':[],'negative_add':[],'negative_remove':[],'config_patch':{}},
                 'working_recipe':copy.deepcopy(base['recipe'])}
        create_json(self.data/'sessions'/(session_id+'.json'),session)
        return session

    def update_session(self,session_id,payload):
        with ResearchLock(self.data/'locks'/safe_id(session_id)):
            session=self.session(session_id)
            if payload.get('revision')!=session['revision']:raise ValueError('別の画面で更新されました。再読み込みしてください。')
            for field in ['requirements','negative_extra','title']:
                if field in payload:
                    if not isinstance(payload[field],str):raise ValueError(field+' must be text')
                    session[field]=payload[field]
            adj=copy.deepcopy(session['adjustments'])
            if 'adjustments' in payload:
                if not isinstance(payload['adjustments'],dict):raise ValueError('Adjustments must be an object')
                for key,value in payload['adjustments'].items():
                    if key not in adj:raise ValueError('Unknown adjustment: '+key)
                    if key!='config_patch' and (not isinstance(value,list) or not all(isinstance(x,str) for x in value)):raise ValueError('Adjustment tokens must be text lists')
                    adj[key]=value
            base=copy.deepcopy(self.style(session['base_style_id'])['recipe']);tmpl=base['prompt_template']
            for prefix,field in [('positive','style_suffix'),('negative','default_negative')]:
                add=split_prompt_tokens(','.join(adj[prefix+'_add']));remove={v.casefold() for v in adj[prefix+'_remove']}
                if prefix=='positive':
                    for location in ['style_prefix','style_suffix']:
                        tmpl[location]=[t for t in tmpl.get(location,[]) if t.casefold() not in remove]
                    tmpl[field]=split_prompt_tokens(','.join(tmpl.get(field,[])+add))
                else:
                    tmpl[field]=', '.join(split_prompt_tokens(','.join([t for t in split_prompt_tokens(tmpl.get(field,'')) if t.casefold() not in remove]+add)))
            base['style_config']=merge_config(base['style_config'],adj['config_patch'])
            session.update(adjustments=adj,working_recipe=base,revision=session['revision']+1,updated_at=now_iso())
            atomic_write_json(self.data/'sessions'/(session_id+'.json'),session)
        return session

    def fork_session(self,session_id, *, style_id, name, save_intent, description='', run_id=None):
        if not isinstance(save_intent,str) or not save_intent.strip():raise ValueError('Record the explicit user request to save a new style')
        session=self.session(session_id)
        source_revision=session['revision']
        if run_id:
            run=read_json(self.data/'runs'/(safe_id(run_id)+'.json'))
            if run['session_id']!=session_id:raise ValueError('Run belongs to another session')
            recipe=run['recipe']
            source_revision=run['session_revision']
        else:recipe=session['working_recipe']
        # No subject requirements, per-run negatives, or review verdicts are copied into the style.
        return self.save_style(style_id=style_id,name=name,description=description,recipe=recipe,parent_id=session['base_style_id'],
                               source={'session_id':session_id,'session_revision':source_revision,'run_id':run_id,'save_intent':save_intent})

    def create_turn(self,session_id, *, title='images', theme=None):
        session=self.session(session_id);theme=theme or session['base_style_id']
        if '/' in theme or '\\' in theme or theme in ('.','..') or not re.fullmatch(r'[\w-]+',theme):raise ValueError('Theme must be a single folder name')
        offset=self.config().get('timezone_offset_minutes');zone=timezone(timedelta(minutes=offset)) if offset is not None else datetime.now().astimezone().tzinfo
        slug=re.sub(r'[^\w-]+','_',title).strip('_')[:36] or 'images'
        turn_id=datetime.now(zone).strftime('%Y-%m-%d_%H%M%S_')+slug+'_'+make_id('t').split('-')[-1][:4]
        folder=self.output/theme/turn_id;folder.mkdir(parents=True,exist_ok=True)
        turn={'turn_id':turn_id,'session_id':session_id,'title':title,'theme':theme,'output_dir':rel_posix(folder,self.root),'created_at':now_iso()}
        create_json(self.data/'turns'/(turn_id+'.json'),turn);return turn

    def turn(self,turn_id):
        if not isinstance(turn_id,str) or Path(turn_id).name!=turn_id or any(x in turn_id for x in '/\\:') or turn_id in ('.','..'):raise ValueError('Invalid turn ID')
        return read_json(self.data/'turns'/(turn_id+'.json'))

    def record_run(self,session_id,turn_id,images, *, seed=123456, workflow=None, session_snapshot=None):
        session=session_snapshot or self.session(session_id);turn=self.turn(turn_id)
        if turn['session_id']!=session_id:raise ValueError('Turn belongs to another session')
        run_id=make_id('run');outputs=[]
        folder=self.root/turn['output_dir']
        for index,source in enumerate(images):
            source=Path(source).resolve()
            if not source.is_file() or source.suffix.lower() not in {'.png','.jpg','.jpeg','.webp'}:raise ValueError('Expected an image file')
            hashed=sha256_file(source);target=folder/(run_id+f'_{index:02d}'+source.suffix.lower())
            snapshot=self.data/'objects'/(hashed+source.suffix.lower())
            raw=source.read_bytes();atomic_write_bytes(target,raw)
            if not snapshot.exists():atomic_write_bytes(snapshot,raw)
            outputs.append({'path':rel_posix(target,self.root),'image_path':rel_posix(snapshot,self.root),'sha256':hashed,'label':source.stem})
        if not outputs:raise ValueError('At least one generated image is required')
        recipe=copy.deepcopy(session['working_recipe'])
        if workflow is None:workflow,_=assemble_workflow({'preset_id':session['base_style_id'],**recipe},subject_prompt=session['requirements'],negative_extra=session['negative_extra'],seed=seed)
        workflow_path=self.data/'workflows'/(run_id+'.json');atomic_write_json(workflow_path,workflow)
        run={'run_id':run_id,'session_id':session_id,'session_revision':session['revision'],'turn_id':turn_id,
             'style_id':session['base_style_id'],'style_recipe_sha256':session['base_recipe_sha256'],'recipe':recipe,
             'requirements':session['requirements'],'negative_extra':session['negative_extra'],'seed':seed,'created_at':now_iso(),
             'workflow_path':rel_posix(workflow_path,self.root),'workflow_sha256':digest(workflow),'outputs':outputs}
        create_json(self.data/'runs'/(run_id+'.json'),run);return run

    def catalog(self,track_id=None):
        result=[]
        for path in sorted((self.data/'runs').glob('*.json'),reverse=True):
            run=read_json(path)
            if track_id and run['style_id']!=track_id:continue
            for index,output in enumerate(run['outputs']):
                result.append({**output,'experiment_id':run['run_id'],'run_id':run['run_id'],'session_id':run['session_id'],
                               'output_index':index,'batch_id':run['turn_id'],
                               'track_id':run['style_id'],'created_at':run['created_at'],'hypothesis':run['requirements']})
        legacy=self.data/'history/research.json'
        if not legacy.exists():legacy=self.root/'.research/state.json'
        if legacy.exists():
            state=read_json(legacy)
            from .migration import resolve_aliases
            state=resolve_aliases(state,self.root)
            for exp in reversed(list(state.get('archive',{}).values())):
                if track_id and exp.get('research_track')!=track_id:continue
                for index,output in enumerate(exp.get('outputs',[])):
                    image_path=output.get('snapshot_relpath') or output.get('path')
                    if image_path and (self.root/image_path).is_file():
                        result.append({**output,'image_path':image_path,'experiment_id':exp['experiment_id'],'output_index':index,
                                       'label':exp['experiment_id'].removeprefix('CAND_'),'batch_id':exp.get('batch_id'),
                                       'track_id':exp.get('research_track'),'created_at':exp.get('created_at'),'hypothesis':exp.get('hypothesis','')})
        media=self.data/'media.json'
        if media.exists():
            present={item['path'] for item in result}
            result += [item for item in read_json(media) if item['path'] not in present and (not track_id or item.get('track_id')==track_id)]
        return result
