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
            original=(workspace.data/'styles/base.json').read_bytes()
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
                child=json.load(request('/api/session/'+sid+'/fork',{'style_id':'child','name':'Child','save_intent':'Explicit test save'}))
                self.assertNotIn('coffee',json.dumps(child['recipe']))
                self.assertEqual(child['parent_style_id'],'base')
                self.assertEqual((workspace.data/'styles/base.json').read_bytes(),original)
                with self.assertRaises(urllib.error.HTTPError) as error:request('/api/styles',headers={'Host':'example.com'})
                self.assertEqual(error.exception.code,403)
                with self.assertRaises(urllib.error.HTTPError):request('/api/session',{'style_id':'base'},headers={'Origin':'https://example.com'})
                with self.assertRaises(urllib.error.HTTPError):request('/api/session/'+sid+'/update',{'revision':0,'requirements':'stale'})
            finally:
                process.terminate();process.communicate(timeout=10)

if __name__=='__main__':unittest.main()
