"""Local review sets: stable image numbers and human feedback, separate from research state."""
from __future__ import annotations

import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .storage import ResearchLock, atomic_write_json, atomic_write_text, make_id, now_iso

VERDICTS = {"": "未評価", "good": "良い", "neutral": "普通", "bad": "微妙", "unsure": "判断困難"}


class ReviewStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.directory = self.root / ".stylekit" / "reviews"

    def _folder(self, review_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", review_id):
            raise ValueError("Invalid review ID")
        legacy = self.root / ".research" / "reviews" / review_id
        return legacy if legacy.is_dir() else self.directory / review_id

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
               labels: dict[str, str] | None = None) -> dict:
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
        for item in selected:
            item["label"] = (labels or {}).get(item["experiment_id"], item["label"])
            review["items"].append({**item, "number": len(review["items"]) + 1,
                                    "role": "reference" if item["experiment_id"] in references else "candidate"})
        folder = self._folder(review["review_id"])
        atomic_write_json(folder / "review.json", review)
        atomic_write_json(folder / "draft.json", {"revision": 0, "ratings": {}, "overall_note": "", "updated_at": now_iso()})
        return self.get(review["review_id"])

    def get(self, review_id: str) -> dict:
        folder = self._folder(review_id)
        review = self._read(folder / "review.json")
        aliases_path = self.root / ".research" / "path_aliases.json"
        if aliases_path.exists():
            aliases = self._read(aliases_path)
            for item in review["items"]:
                item["path"] = aliases.get(item["path"], item["path"])
                item["image_path"] = aliases.get(item["image_path"], item["image_path"])
        review["draft"] = self._read(folder / "draft.json")
        review["submitted"] = self._read(folder / "feedback.json") if (folder / "feedback.json").exists() else None
        return review

    def list_reviews(self) -> list[dict]:
        result = []
        paths = [*self.directory.glob("*/review.json"), *(self.root / ".research/reviews").glob("*/review.json")]
        for path in paths:
            review = self._read(path)
            result.append({k: review.get(k) for k in ["review_id", "title", "created_at", "track_id"]})
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
        return self.get(review_id)

    def image(self, review_id: str, number: int) -> Path:
        review = self.get(review_id)
        item = next((i for i in review["items"] if i["number"] == number), None)
        if item is None:
            raise ValueError("Unknown image")
        return self._local_image(item["image_path"])

