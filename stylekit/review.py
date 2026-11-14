"""Local review sets: stable image numbers and human feedback, separate from research state."""
from __future__ import annotations

import json
import mimetypes
import os
import re
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .storage import ResearchLock, atomic_write_json, atomic_write_text, make_id, now_iso

VERDICTS = {"": "未評価", "good": "良い", "neutral": "普通", "bad": "微妙", "unsure": "判断困難"}


class ReviewStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        from .workspace import Workspace
        self.directory = Workspace(self.root).data / "reviews"

    def _folder(self, review_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", review_id):
            raise ValueError("Invalid review ID")
        legacy = self.root / ".research" / "reviews" / review_id
        current = self.directory / review_id
        return current if current.is_dir() or not legacy.is_dir() else legacy

    def _read(self, path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    def _local_image(self, path: str) -> Path:
        target = (self.root / path).resolve()
        if not target.is_relative_to(self.root) or target.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("Image must be inside the workspace")
        if not target.is_file():
            raise FileNotFoundError(path)
        return target

    def catalog(self, track_id: str | None = None) -> list[dict]:
        from .workspace import Workspace
        return Workspace(self.root).catalog(track_id)

    def create(self, *, title: str, batch_id: str | None = None, experiments: list[str] | None = None,
               references: list[str] | None = None, track_id: str | None = None,
               labels: dict[str, str] | list[str] | None = None) -> dict:
        catalog = self.catalog(track_id)
        experiments, references = experiments or [], references or []
        if not experiments and not batch_id:
            batch_id = next((item["batch_id"] for item in catalog if item.get("batch_id")), None)
            if batch_id is None:
                raise ValueError("No batch found; specify --experiment")
        selected = list(reversed([item for item in catalog if item["experiment_id"] in experiments
                                  or (batch_id and item["batch_id"] == batch_id)]))
        for eid in experiments:
            if not any(item["experiment_id"] == eid for item in selected):
                raise ValueError(f"Experiment has no local image: {eid}")
        if not selected:
            raise ValueError("No images found for this review")
        for eid in references:
            matches = [item for item in reversed(catalog) if item["experiment_id"] == eid]
            if not matches:
                raise ValueError(f"Reference has no local image: {eid}")
            for item in matches:
                if not any((s["experiment_id"], s["output_index"]) == (eid, item["output_index"]) for s in selected):
                    selected.append(item)
        review = {"schema_version": 1, "review_id": make_id("review"), "title": title,
                  "created_at": now_iso(), "track_id": track_id, "batch_id": batch_id, "items": []}
        for index, item in enumerate(selected):
            num = index + 1
            if isinstance(labels, list):
                if index < len(labels) and labels[index]:
                    item["label"] = str(labels[index])
            elif isinstance(labels, dict):
                item["label"] = (
                    labels.get(item["experiment_id"])
                    or labels.get(item.get("path", ""))
                    or labels.get(str(num))
                    or labels.get(f"#{num}")
                    or item["label"]
                )
            review["items"].append({**item, "number": num,
                                    "role": "reference" if item["experiment_id"] in references else "candidate"})
        folder = self._folder(review["review_id"])
        atomic_write_json(folder / "review.json", review)
        atomic_write_json(folder / "draft.json", {"revision": 0, "ratings": {}, "overall_note": "", "updated_at": now_iso()})
        return self.get(review["review_id"])

    def get(self, review_id: str) -> dict:
        folder = self._folder(review_id)
        review = self._read(folder / "review.json")
        from .migration import resolve_aliases
        from .workspace import Workspace
        review = resolve_aliases(review,self.root)
        ws = Workspace(self.root)
        for item in review.get("items", []):
            if item.get("label") in (None, "", "0") and item.get("run_id"):
                run_file = ws.data / "runs" / f'{item["run_id"]}.json'
                if run_file.is_file():
                    run_data = self._read(run_file)
                    outputs = run_data.get("outputs", [])
                    idx = item.get("output_index", 0)
                    out_label = outputs[idx].get("label") if idx < len(outputs) else None
                    lbl = out_label or run_data.get("label")
                    if lbl and lbl != "0":
                        item["label"] = lbl
        review["draft"] = self._read(folder / "draft.json")
        review["submitted"] = self._read(folder / "feedback.json") if (folder / "feedback.json").exists() else None
        url = f'http://127.0.0.1:8767/reviews?review={review["review_id"]}'
        review["url"] = url
        review["markdown_link"] = f'[画像レビューを開く ({review["review_id"]})]({url})'
        return review

    def list_reviews(self) -> list[dict]:
        result = []
        paths = [*self.directory.glob("*/review.json"), *(self.root / ".research/reviews").glob("*/review.json")]
        for path in paths:
            review = self._read(path)
            draft_path = path.parent / "draft.json"
            draft = self._read(draft_path) if draft_path.is_file() else {"ratings": {}}
            sub_path = path.parent / "feedback.json"
            submitted = self._read(sub_path) if sub_path.is_file() else None
            items = review.get("items", [])
            candidates = [i for i in items if i.get("role") == "candidate"] or items
            ratings = draft.get("ratings", {})
            rated_count = sum(
                1
                for i in candidates
                if ratings.get(str(i.get("number")), {}).get("verdict")
                or ratings.get(str(i.get("number")), {}).get("note", "").strip()
            )
            result.append(
                {
                    **{k: review.get(k) for k in ["review_id", "title", "created_at", "track_id", "batch_id"]},
                    "item_count": len(items),
                    "candidate_count": len(candidates),
                    "rated_count": rated_count,
                    "submitted": bool(submitted),
                    "submitted_at": submitted.get("submitted_at") if isinstance(submitted, dict) else None,
                }
            )
        return sorted(result, key=lambda r: r["created_at"], reverse=True)

    def add(self, review_id: str, experiment_id: str, revision: int) -> dict:
        with ResearchLock(self._folder(review_id) / ".lock"):
            review = self.get(review_id)
            if review["draft"]["revision"] != revision:
                raise ValueError("別の画面で更新されました。再読み込みしてください。")
            matches = [item for item in reversed(self.catalog()) if item["experiment_id"] == experiment_id]
            if not matches:
                raise ValueError("Image not found")
            for item in matches:
                if not any((s["experiment_id"], s["output_index"]) == (experiment_id, item["output_index"]) for s in review["items"]):
                    review["items"].append({**item, "number": len(review["items"]) + 1, "role": "reference"})
            review["draft"]["revision"] += 1
            draft = review.pop("draft")
            review.pop("submitted")
            atomic_write_json(self._folder(review_id) / "review.json", review)
            atomic_write_json(self._folder(review_id) / "draft.json", draft)
        return self.get(review_id)

    def save(self, review_id: str, payload: dict, *, submit: bool = False) -> dict:
        folder = self._folder(review_id)
        with ResearchLock(folder / ".lock"):
            review = self.get(review_id)
            if payload.get("revision") != review["draft"]["revision"]:
                raise ValueError("別の画面で更新されました。再読み込みしてください。")
            ratings = payload.get("ratings", {})
            if not isinstance(ratings, dict) or not isinstance(payload.get("overall_note", ""), str):
                raise ValueError("Invalid feedback")
            allowed = {str(item["number"]) for item in review["items"]}
            for number, rating in ratings.items():
                if number not in allowed or not isinstance(rating, dict) or rating.get("verdict", "") not in VERDICTS:
                    raise ValueError("Invalid image number or verdict")
                if not isinstance(rating.get("note", ""), str):
                    raise ValueError("Invalid note")
            draft = {"revision": review["draft"]["revision"] + 1, "updated_at": now_iso(),
                     "ratings": {n: {"verdict": r.get("verdict", ""), "note": r.get("note", "")} for n, r in ratings.items()},
                     "overall_note": payload.get("overall_note", "")}
            if submit and not draft["overall_note"].strip() and not any(
                r["verdict"] or r["note"].strip() for r in draft["ratings"].values()
            ):
                raise ValueError("評価かメモを一つ以上入力してください。")
            atomic_write_json(folder / "draft.json", draft)
            if submit:
                feedback = {"review_id": review_id, "title": review["title"], "submitted_at": now_iso(),
                            "revision": draft["revision"], "overall_note": draft["overall_note"], "items": []}
                for item in review["items"]:
                    feedback["items"].append({**item, **draft["ratings"].get(str(item["number"]), {"verdict": "", "note": ""})})
                # Keep submissions immutable, and expose a convenient latest receipt for agents.
                atomic_write_json(folder / "submissions" / f'{draft["revision"]:06d}.json', feedback)
                atomic_write_json(folder / "feedback.json", feedback)
                lines = [f'# {review["title"]}', f'レビューID: `{review_id}`', f'提出日時: {feedback["submitted_at"]}', ""]
                for item in feedback["items"]:
                    lines += [f'## #{item["number"]:02d} {item["label"]} ({VERDICTS[item["verdict"]]})',
                              f'Experiment: `{item["experiment_id"]}`', f'Image: `{item["path"]}`', item["note"], ""]
                lines += ["## 全体メモ", draft["overall_note"], ""]
                atomic_write_text(folder / "feedback.md", "\n".join(lines))
        if submit:
            self._run_submit_hook(review_id, folder, feedback)
        return self.get(review_id)

    def _run_submit_hook(self, review_id: str, folder: Path, feedback: dict) -> None:
        from .workspace import Workspace
        hook = Workspace(self.root).data / "hooks" / "on_review_submit.py"
        if not hook.is_file():
            return
        event = {
            "workspace": str(self.root),
            "review_id": review_id,
            "title": feedback["title"],
            "revision": feedback["revision"],
            "submitted_at": feedback["submitted_at"],
            "overall_note": feedback.get("overall_note", ""),
            "feedback_path": str(folder / "feedback.json"),
            "markdown_path": str(folder / "feedback.md"),
        }
        try:
            subprocess.run(
                [sys.executable, "-B", str(hook)],
                cwd=self.root,
                input=json.dumps(event, ensure_ascii=False),
                text=True,
                encoding="utf-8",
                timeout=3,
                capture_output=True,
                check=False,
            )
        except Exception:
            pass

    def wait(
        self,
        review_id: str,
        *,
        since_revision: int | None = None,
        timeout: float = 86400.0,
        poll_interval: float = 0.4,
        serve_port: int | None = 8767,
    ) -> dict:
        folder = self._folder(review_id)
        if not (folder / "review.json").is_file():
            raise FileNotFoundError(f"Review not found: {review_id}")
        feedback_path = folder / "feedback.json"
        if since_revision is not None:
            baseline_rev = int(since_revision)
        elif feedback_path.is_file():
            try:
                baseline_rev = int(self._read(feedback_path).get("revision", 0))
            except Exception:
                baseline_rev = 0
        else:
            baseline_rev = 0

        watcher_file = self.directory / "watcher.pid"
        if watcher_file.is_file():
            try:
                prev = self._read(watcher_file)
                prev_pid = int(prev.get("pid", 0))
                if prev_pid and prev_pid != os.getpid():
                    os.kill(prev_pid, signal.SIGTERM)
            except Exception:
                pass
        try:
            atomic_write_json(watcher_file, {"pid": os.getpid(), "review_id": review_id, "started_at": now_iso()})
        except Exception:
            pass

        embedded_server = None
        if serve_port:
            try:
                from .server import create_http_server
                embedded_server = create_http_server(self.root, int(serve_port))
                thread = threading.Thread(target=embedded_server.serve_forever, daemon=True)
                thread.start()
            except OSError:
                embedded_server = None

        deadline = time.monotonic() + float(timeout)
        try:
            while time.monotonic() < deadline:
                if feedback_path.is_file():
                    try:
                        data = self._read(feedback_path)
                    except Exception:
                        data = None
                    if isinstance(data, dict) and int(data.get("revision", 0)) > baseline_rev:
                        if embedded_server is not None:
                            time.sleep(0.8)
                        data["continuation_policy"] = (
                            "Analyze the submitted feedback and report your findings/proposals. "
                            "Do NOT start generating the next batch automatically unless the user explicitly requested "
                            "next generation in overall_note, item notes, or chat."
                        )
                        return data
                time.sleep(max(0.05, float(poll_interval)))
            raise TimeoutError(f"Timed out waiting for review submission: {review_id}")
        finally:
            if embedded_server is not None:
                try:
                    embedded_server.shutdown()
                    embedded_server.server_close()
                except Exception:
                    pass
            try:
                if watcher_file.is_file() and self._read(watcher_file).get("pid") == os.getpid():
                    watcher_file.unlink(missing_ok=True)
            except Exception:
                pass

    def image(self, review_id: str, number: int) -> Path:
        folder = self._folder(review_id)
        review = self._read(folder / "review.json")
        from .migration import resolve_aliases
        review = resolve_aliases(review, self.root)
        item = next((i for i in review["items"] if i["number"] == number), None)
        if item is None:
            raise ValueError("Unknown image")
        return self._local_image(item["image_path"])

    def catalog_image(self, experiment_id: str, output_index: int) -> Path:
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}", experiment_id):
            from .workspace import Workspace
            run_file = Workspace(self.root).data / "runs" / f"{experiment_id}.json"
            if run_file.is_file():
                run = self._read(run_file)
                outputs = run.get("outputs", [])
                if 0 <= output_index < len(outputs):
                    out = outputs[output_index]
                    return self._local_image(out.get("image_path") or out.get("path"))
        item = next(
            (i for i in self.catalog() if i["experiment_id"] == experiment_id and i["output_index"] == output_index),
            None,
        )
        if not item:
            raise FileNotFoundError(experiment_id)
        return self._local_image(item["image_path"])
