"""Review identity, persistence and research-state isolation in a temporary workspace."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stylekit.review import ReviewStore
from stylekit.storage import atomic_write_json


class TestReview(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / ".research/state.json"
        archive = {}
        for eid, batch, track in [("old", "b0", "art"), ("one", "b1", "art"), ("two", "b1", "art"), ("other", "b2", "other")]:
            image = self.root / "images" / f"{eid}.png"
            image.parent.mkdir(exist_ok=True)
            image.write_bytes(b"test image")
            snapshot = self.root / ".research/objects" / image.name
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_bytes(b"immutable image")
            archive[eid] = {"experiment_id": eid, "batch_id": batch, "research_track": track,
                            "outputs": [{"path": f"images/{eid}.png", "snapshot_relpath": f".research/objects/{eid}.png"}]}
        atomic_write_json(self.state, {"archive": archive, "champion": {"experiment_id": "old"}})
        self.before = self.state.read_bytes()
        self.store = ReviewStore(self.root)

    def test_explicit_set_stable_numbers_and_snapshot(self):
        review = self.store.create(title="比較", batch_id="b1", references=["old"], labels={"one": "本屋"})
        self.assertEqual([i["experiment_id"] for i in review["items"]], ["one", "two", "old"])
        self.assertEqual(review["items"][0]["label"], "本屋")
        self.assertEqual(self.store.image(review["review_id"], 1).read_bytes(), b"immutable image")
        updated = self.store.add(review["review_id"], "other", 0)
        updated = self.store.add(review["review_id"], "old", updated["draft"]["revision"])
        self.assertEqual([(i["number"], i["experiment_id"]) for i in updated["items"]], [(1,"one"),(2,"two"),(3,"old"),(4,"other")])
        self.assertEqual(self.state.read_bytes(), self.before)

    def test_latest_batch_scoped_to_track(self):
        review = self.store.create(title="最新", track_id="art")
        self.assertEqual(review["batch_id"], "b1")
        self.assertEqual(len(review["items"]), 2)

    def test_draft_submission_and_edits_are_distinct(self):
        review = self.store.create(title="評価", batch_id="b1")
        rid = review["review_id"]
        payload = {"revision": 0, "ratings": {"1": {"verdict": "unsure", "note": "#03と比較したい"}}, "overall_note": "次は屋外"}
        draft = self.store.save(rid, payload)
        self.assertIsNone(draft["submitted"])
        payload["revision"] = draft["draft"]["revision"]
        submitted = self.store.save(rid, payload, submit=True)
        self.assertEqual(submitted["submitted"]["items"][0]["experiment_id"], "one")
        self.assertEqual(submitted["submitted"]["items"][0]["note"], "#03と比較したい")
        self.assertEqual(submitted["submitted"]["items"][1]["verdict"], "")
        receipt = json.dumps(submitted["submitted"], ensure_ascii=False)
        payload["revision"] = submitted["draft"]["revision"]
        payload["ratings"]["1"]["note"] = "修正中"
        changed = self.store.save(rid, payload)
        self.assertEqual(json.dumps(changed["submitted"], ensure_ascii=False), receipt)
        self.assertEqual(self.state.read_bytes(), self.before)
        self.assertIn("#01", (self.store._folder(rid)/"feedback.md").read_text(encoding="utf-8"))

    def test_submit_invokes_optional_local_hook_not_on_draft(self):
        hook = self.root / ".stylefork/hooks/on_review_submit.py"
        hook.parent.mkdir(parents=True, exist_ok=True)
        marker = self.root / ".stylefork/hook_event.json"
        hook.write_text(
            "import pathlib, sys\n"
            f"pathlib.Path({str(marker)!r}).write_text(sys.stdin.read(), encoding='utf-8')\n",
            encoding="utf-8",
        )
        review = self.store.create(title="Hook test", batch_id="b1")
        rid = review["review_id"]
        draft = self.store.save(rid, {"revision": 0, "overall_note": "draft only"}, submit=False)
        self.assertFalse(marker.exists())
        self.store.save(rid, {"revision": draft["draft"]["revision"], "overall_note": "submitted now"}, submit=True)
        self.assertTrue(marker.is_file())
        event = json.loads(marker.read_text(encoding="utf-8"))
        self.assertEqual(event["review_id"], rid)
        self.assertEqual(event["revision"], 2)
        self.assertTrue(Path(event["feedback_path"]).is_file())

    def test_invalid_feedback_and_stale_tabs_rejected(self):
        review = self.store.create(title="評価", batch_id="b1")
        rid = review["review_id"]
        for payload in [{"revision":0,"ratings":{"99":{"verdict":"good"}}},
                        {"revision":0,"ratings":{"1":{"verdict":"invented"}}}]:
            with self.assertRaises(ValueError): self.store.save(rid,payload)
        with self.assertRaises(ValueError): self.store.save(rid,{"revision":0},submit=True)
        self.store.save(rid,{"revision":0,"overall_note":"下書き"})
        with self.assertRaises(ValueError): self.store.save(rid,{"revision":0,"overall_note":"古い画面"})

    def test_no_arbitrary_files_or_traversal(self):
        for name in ["../state", "a/b", "..", "C:\\outside"]:
            with self.assertRaises(ValueError): self.store.get(name)
        with self.assertRaises(ValueError): self.store._local_image(".research/state.json")
        with self.assertRaises(ValueError): self.store._local_image("../outside.png")
        review = self.store.create(title="評価", batch_id="b1")
        with self.assertRaises(ValueError): self.store.image(review["review_id"], 100)
        with self.assertRaises(ValueError): self.store.create(title="空", batch_id="unknown")
        with self.assertRaises(ValueError): self.store.create(title="不明", experiments=["missing"])

    def test_positional_labels_markdown_link_and_wait(self):
        import threading
        review = self.store.create(title="比較テスト", batch_id="b1", references=["old"], labels=["候補A", "候補B", "参考旧"])
        self.assertEqual([i["label"] for i in review["items"]], ["候補A", "候補B", "参考旧"])
        self.assertIn(review["review_id"], review["url"])
        self.assertTrue(review["markdown_link"].startswith("[画像レビューを開く ("))
        rid = review["review_id"]

        def submit_later():
            import time
            time.sleep(0.15)
            self.store.save(rid, {"revision": 0, "ratings": {"1": {"verdict": "good", "note": "OK"}}, "overall_note": "良い"}, submit=True)

        t = threading.Thread(target=submit_later, daemon=True)
        t.start()
        waited = self.store.wait(rid, timeout=5.0, poll_interval=0.05, serve_port=None)
        self.assertEqual(waited["review_id"], rid)
        self.assertEqual(waited["overall_note"], "良い")
        self.assertIn("continuation_policy", waited)


if __name__ == "__main__":
    unittest.main()
