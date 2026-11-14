import json
import tempfile
import subprocess
import sys
import unittest
from pathlib import Path
from stylekit.workspace import Workspace
from stylekit.migration import migrate, resolve_aliases
from stylekit.review import ReviewStore
from stylekit.storage import atomic_write_json, sha256_file
from test_workflow import recipe, png

class LayoutTests(unittest.TestCase):
    def test_fresh_project_has_five_root_entries_and_hidden_workflows(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);w=Workspace(root);w.init()
            self.assertEqual({p.name for p in root.iterdir()}, {'AGENTS.md','.agents','styles','output','.stylefork'})
            self.assertFalse((root/'.agents/rules').exists())
            self.assertEqual({p.name for p in w.data.iterdir()},{'config.json'})
            skill=(root/'.agents/skills/stylefork-project/SKILL.md').read_text(encoding='utf-8')
            self.assertIn('python .agents/stylefork.py',skill)
            self.assertIn('session fork',skill)
            self.assertIn('requirements',skill)
            self.assertNotIn('Read the repository `AGENTS.md`',skill)
            self.assertTrue((root/'.agents/skills/stylefork-project/agents/openai.yaml').is_file())
            process=subprocess.run([sys.executable,'-B',str(root/'.agents/stylefork.py'),'style','list'],cwd=root,capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(process.returncode,0,process.stderr)
            self.assertEqual(json.loads(process.stdout),[])
            w.save_style(style_id='base',name='Base',recipe=recipe())
            session=w.create_session('base');turn=w.create_turn(session['session_id'],title='test')
            source=root/'.stylefork/test.png';png(source)
            run=w.record_run(session['session_id'],turn['turn_id'],[source])
            self.assertTrue(run['workflow_path'].startswith('.stylefork/workflows/'))
            self.assertEqual(len(list((root/turn['output_dir']).glob('*.json'))),0)

    def test_init_preserves_project_instructions_and_skills(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);w=Workspace(root);w.init()
            guide=root/'AGENTS.md';skill=root/'.agents/skills/stylefork-project/SKILL.md'
            guide.write_text('Custom project instructions',encoding='utf-8')
            skill.write_text('Custom skill',encoding='utf-8')
            w.init()
            self.assertEqual(guide.read_text(encoding='utf-8'),'Custom project instructions')
            self.assertEqual(skill.read_text(encoding='utf-8'),'Custom skill')

    def test_migrate_preserves_style_bytes_images_history_and_review_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            atomic_write_json(root/'.stylekit/config.json',{'comfy_url':'http://127.0.0.1:8188'})
            old=Workspace(root);old.save_style(style_id='base',name='Base',recipe=recipe())
            style_before=(root/'.stylekit/styles/base.json').read_bytes()
            image=root/'ai/output/theme/turn/test.png';image.parent.mkdir(parents=True);png(image)
            snapshot=root/'.research/objects/test.png';snapshot.parent.mkdir(parents=True);snapshot.write_bytes(image.read_bytes())
            atomic_write_json(root/'.research/state.json',{'archive':{'test':{'experiment_id':'test','batch_id':'batch','outputs':[{'path':'ai/output/theme/turn/test.png','snapshot_relpath':'.research/objects/test.png'}]}},'evaluations':{'e1':{'experiment_id':'test','raw_text':'human comment'}}})
            review=ReviewStore(root).create(title='Old review',batch_id='batch')
            result=migrate(root,apply=True);self.assertEqual(result['unique_images'],1)
            modern=Workspace(root);self.assertEqual(modern.data.name,'.stylefork')
            self.assertEqual((modern.styles_dir/'base.json').read_bytes(),style_before)
            self.assertEqual(sha256_file(root/'output/theme/turn/test.png'),sha256_file(image))
            self.assertEqual(resolve_aliases('.research/objects/test.png',root),'output/theme/turn/test.png')
            self.assertEqual(ReviewStore(root).image(review['review_id'],1),(root/'output/theme/turn/test.png').resolve())
            self.assertTrue((root/'.research/state.json').exists())
            self.assertEqual(json.loads((root/'.stylefork/history/research.json').read_text())['evaluations']['e1']['raw_text'],'human comment')

if __name__=='__main__':unittest.main()
