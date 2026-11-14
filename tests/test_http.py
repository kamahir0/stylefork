import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from stylekit.workspace import Workspace
from test_workflow import recipe

class HttpTests(unittest.TestCase):
    def test_loopback_ui_and_style_fork_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace=Workspace(directory);workspace.save_style(style_id='base',name='Base',recipe=recipe())
            original=(workspace.styles_dir/'base.json').read_bytes()
            process=subprocess.Popen([sys.executable,'-u','-m','stylekit','--workspace',directory,'serve','--port','0'],
                                     cwd=Path(__file__).resolve().parents[1],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                line=process.stdout.readline().decode('utf-8').strip();self.assertTrue(line.startswith('StyleFork: '),line)
                base=line.split(' ',1)[1]
                def request(path,payload=None,headers=None):
                    extra={'Content-Type':'application/json','Origin':base};extra.update(headers or {})
                    req=urllib.request.Request(base+path,data=json.dumps(payload).encode() if payload is not None else None,headers=extra)
                    return urllib.request.urlopen(req,timeout=5)
                self.assertIn(b'StyleFork',request('/').read())
                self.assertIn(b'focus-view',request('/reviews').read())
                session=json.load(request('/api/session',{'style_id':'base'}))
                sid=session['session_id'];session=json.load(request('/api/session/'+sid+'/update',{'revision':0,'requirements':'holding coffee cup','adjustments':{'positive_add':['matte shading']}}))
                turn=json.load(request('/api/turn',{'session_id':sid,'title':'朝のパン屋'}))
                turns=json.load(request('/api/turns'))
                self.assertEqual(len(turns),1)
                self.assertEqual(turns[0]['title'],'朝のパン屋')
                sample_img=Path(directory)/'0.png';sample_img.write_bytes(b'png-bytes')
                run=workspace.record_run(session_id=sid,turn_id=turn['turn_id'],images=[sample_img])
                self.assertEqual(run['outputs'][0]['label'],'朝のパン屋')
                cat=json.load(request('/api/catalog'))
                self.assertEqual(cat[0]['label'],'朝のパン屋')
                self.assertEqual(cat[0]['turn_title'],'朝のパン屋')
                self.assertEqual(cat[0]['style_name'],'Base')
                rev=json.load(request('/api/review',{'turn_id':turn['turn_id'],'title':'パン屋レビュー'}))
                img_resp=request('/image?review='+rev['review_id']+'&number=1')
                self.assertEqual(img_resp.read(),b'png-bytes')
                self.assertIn('immutable',img_resp.headers.get('Cache-Control',''))
                cat_img_resp=request('/catalog-image?experiment='+run['run_id']+'&index=0')
                self.assertEqual(cat_img_resp.read(),b'png-bytes')
                self.assertIn('immutable',cat_img_resp.headers.get('Cache-Control',''))
                revs=json.load(request('/api/reviews'))
                self.assertEqual(revs[0]['batch_id'],turn['turn_id'])
                self.assertEqual(revs[0]['item_count'],1)
                self.assertFalse(revs[0]['submitted'])
                child=json.load(request('/api/session/'+sid+'/fork',{'style_id':'child','name':'Child','save_intent':'Explicit test save'}))
                self.assertNotIn('coffee',json.dumps(child['recipe']))
                self.assertEqual(child['parent_style_id'],'base')
                self.assertEqual((workspace.styles_dir/'base.json').read_bytes(),original)
                with self.assertRaises(urllib.error.HTTPError) as error:request('/api/styles',headers={'Host':'example.com'})
                self.assertEqual(error.exception.code,403)
                with self.assertRaises(urllib.error.HTTPError):request('/api/session',{'style_id':'base'},headers={'Origin':'https://example.com'})
                with self.assertRaises(urllib.error.HTTPError):request('/api/session/'+sid+'/update',{'revision':0,'requirements':'stale'})
            finally:
                process.terminate();process.communicate(timeout=10)

if __name__=='__main__':unittest.main()
