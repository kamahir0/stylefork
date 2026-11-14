import copy
import json
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import zlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

from stylekit.workspace import Workspace
from stylekit.review import ReviewStore
from stylekit.storage import read_json,atomic_write_json
from stylekit.comfy import generate

def recipe():
    return {'style_config':{'checkpoint':'example.safetensors','loras':[],'clip_stop_at_clip_layer':None,'base_resolution':[64,64],
                           'sampler':{'steps':2,'cfg':4.5,'sampler_name':'euler','scheduler':'normal','denoise':1},
                           'hires':{'enabled':False},'detailer':{'enabled':False}},
            'prompt_template':{'style_prefix':['clean lineart'],'style_suffix':[],'default_negative':'bad anatomy','detailer_positive_template':''}}

def png(path):
    def chunk(tag,raw):return struct.pack('>I',len(raw))+tag+raw+struct.pack('>I',zlib.crc32(tag+raw)&0xffffffff)
    raw=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\xff\x00\x00'))+chunk(b'IEND',b'')
    path.write_bytes(raw);return raw

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.w=Workspace(self.root);self.w.init()
        self.base=self.w.save_style(style_id='base',name='Base',recipe=recipe())
        self.base_path=self.w.styles_dir/'base.json';self.before=self.base_path.read_bytes()

    def test_generation_requirements_never_change_saved_style_or_other_session(self):
        first=self.w.create_session('base');second=self.w.create_session('base')
        first=self.w.update_session(first['session_id'],{'revision':0,'requirements':'holding coffee cup, cafe','negative_extra':'bottle',
                                                       'adjustments':{'positive_add':['seductive','matte shading'],'negative_add':['neon']}})
        self.assertIn('seductive',first['working_recipe']['prompt_template']['style_suffix'])
        self.assertEqual(self.w.session(second['session_id'])['working_recipe'],recipe())
        self.assertEqual(self.base_path.read_bytes(),self.before)
        child=self.w.fork_session(first['session_id'],style_id='child',name='New atmosphere',save_intent='Save this atmosphere')
        self.assertEqual(child['parent_style_id'],'base')
        self.assertNotIn('coffee',json.dumps(child['recipe']))
        self.assertNotIn('bottle',json.dumps(child['recipe']))
        self.assertIn('seductive',json.dumps(child['recipe']))
        self.assertEqual(self.w.session(first['session_id'])['base_style_id'],'base')
        self.assertEqual(self.base_path.read_bytes(),self.before)

    def test_overwrite_tampering_and_missing_save_intent_are_rejected(self):
        with self.assertRaises(FileExistsError):self.w.save_style(style_id='base',name='Overwrite',recipe=recipe())
        session=self.w.create_session('base')
        with self.assertRaises(ValueError):self.w.fork_session(session['session_id'],style_id='child',name='Child',save_intent='')
        changed=read_json(self.base_path);changed['recipe']['style_config']['sampler']['cfg']=99;atomic_write_json(self.base_path,changed)
        with self.assertRaises(ValueError):self.w.session(session['session_id'])

    def test_scene_controls_cannot_be_silently_frozen_into_style(self):
        for field,value in [('style_prefix',['holding mug']),('default_negative','coffee cup')]:
            bad=recipe();bad['prompt_template'][field]=value
            with self.assertRaises(ValueError):self.w.save_style(style_id='bad',name='Bad',recipe=bad)

    def test_stale_session_update_does_not_erase_newer_work(self):
        session=self.w.create_session('base');self.w.update_session(session['session_id'],{'revision':0,'requirements':'new'})
        with self.assertRaises(ValueError):self.w.update_session(session['session_id'],{'revision':0,'requirements':'stale'})
        self.assertEqual(self.w.session(session['session_id'])['requirements'],'new')

    def test_record_review_and_fork_exact_run_after_later_changes(self):
        session=self.w.create_session('base');turn=self.w.create_turn(session['session_id'],title='first',theme='concept')
        image=self.root/'input.png';raw=png(image)
        run=self.w.record_run(session['session_id'],turn['turn_id'],[image])
        self.w.update_session(session['session_id'],{'revision':0,'adjustments':{'positive_add':['new shading']}})
        child=self.w.fork_session(session['session_id'],style_id='from-image',name='Image style',save_intent='Save image atmosphere',run_id=run['run_id'])
        self.assertEqual(child['recipe'],recipe());self.assertEqual(child['source']['session_revision'],0)
        reviews=ReviewStore(self.root);review=reviews.create(title='Review',batch_id=turn['turn_id'])
        review=reviews.save(review['review_id'],{'revision':0,'ratings':{'1':{'verdict':'good','note':'Eyes look good'}}},submit=True)
        self.assertEqual(review['submitted']['items'][0]['experiment_id'],run['run_id'])
        self.assertEqual(reviews.image(review['review_id'],1).read_bytes(),raw)
        plan=self.w.drive_plan(turn['turn_id']);self.assertIsNone(plan['drive_folder_id'])
        self.assertTrue(plan['files'][0]['remote_path'].startswith('concept/'+turn['turn_id']+'/'))
        self.assertEqual(len(self.w.styles()),2)

    def test_path_traversal_is_rejected(self):
        for bad in ['../style','/absolute','a/b','C:\\outside','..']:
            with self.assertRaises(ValueError):self.w.style(bad)
        with self.assertRaises(ValueError):ReviewStore(self.root)._local_image('../secret.png')

    def test_comfy_adapter_pins_snapshot_and_writes_exact_workflow(self):
        image=self.root/'fixture.png';raw=png(image);captured={}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_POST(self):
                captured.update(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200);self.end_headers();self.wfile.write(b'{"prompt_id":"test"}')
            def do_GET(self):
                self.send_response(200);self.end_headers()
                if self.path.startswith('/view'):self.wfile.write(raw)
                else:self.wfile.write(json.dumps({'test':{'outputs':{'99':{'images':[{'filename':'fixture.png','type':'output'}]}}}}).encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        config=self.w.config();config['comfy_url']=f'http://127.0.0.1:{server.server_port}';atomic_write_json(self.w.data/'config.json',config)
        session=self.w.create_session('base');self.w.update_session(session['session_id'],{'revision':0,'requirements':'a sunny park'})
        turn=self.w.create_turn(session['session_id'],title='generation')
        run=generate(self.w,session['session_id'],turn['turn_id'],seed=7)
        self.assertEqual(captured['prompt']['5']['inputs']['seed'],7)
        self.assertIn('a sunny park',captured['prompt']['3']['inputs']['text'])
        self.assertEqual(read_json(self.root/run['workflow_path']),captured['prompt'])
        self.assertEqual(self.base_path.read_bytes(),self.before)

    def test_cli_runs_without_installation_in_a_fresh_workspace(self):
        kit=Path(__file__).resolve().parents[1]
        result=subprocess.run([sys.executable,'-m','stylekit','--workspace',str(self.root/'fresh'),'init'],cwd=kit,capture_output=True,text=True,encoding='utf-8',check=True)
        self.assertTrue(json.loads(result.stdout)['workspace'].endswith('fresh'))

if __name__=='__main__':unittest.main()
