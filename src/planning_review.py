"""Durable, content-addressed human review checkpoints; no sleeping worker threads."""
import hashlib
import json
import time
import uuid
from pathlib import Path

from video_project import write_json

STAGES = ("outline", "storyboard")


def version_of(document):
    return hashlib.sha256(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class PlanningPending(Exception):
    def __init__(self, stage, message=None):
        self.stage = stage
        super().__init__(message or f"等待确认{'大纲' if stage == 'outline' else '分镜'}")


class ReviewConflict(ValueError):
    pass


class PlanningReview:
    def __init__(self, project, auto_approve=None):
        self.project = Path(project)
        self.file = self.project / "planning_review.json"
        self.state = json.loads(self.file.read_text(encoding="utf8")) if self.file.is_file() else {"schema_version": 1, "auto_approve": False, "stages": {}, "history": []}
        if auto_approve is not None:
            self.state["auto_approve"] = bool(auto_approve)
            self.persist()

    def persist(self):
        write_json(self.file, self.state)

    def path(self, stage):
        if stage not in STAGES:
            raise ValueError("Only outline and storyboard can be reviewed")
        return self.project / "output" / f"{stage}.json"

    def document(self, stage):
        return json.loads(self.path(stage).read_text(encoding="utf8"))

    def check_version(self, stage, version):
        if not version or version_of(self.document(stage)) != version:
            raise ReviewConflict("内容已发生变化，请重新加载后再操作，当前编辑不会覆盖新版本。")

    def checkpoint(self, stage, document):
        current = version_of(document)
        entry = self.state["stages"].setdefault(stage, {})
        entry["version"] = current
        if self.state["auto_approve"]:
            entry.update(approved_version=current, approved_by="automatic", approved_at=time.time())
        if entry.get("approved_version") == current:
            self.persist()
            return
        self.state["pending_stage"] = stage
        self.persist()
        raise PlanningPending(stage)

    def replace(self, stage, document, version, author="human", feedback=""):
        self.check_version(stage, version)
        # Keep the previous document and editor attribution for every change.
        token = f"{time.time_ns()}-{uuid.uuid4().hex[:6]}"
        write_json(self.project / "planning_history" / f"{token}-{stage}.json", {"previous": self.document(stage), "replacement": document, "author": author, "feedback": feedback})
        write_json(self.path(stage), document)
        # An explicit, version-checked edit authorizes a new handoff. Remove
        # receipts for this stage and its dependants, never the source proof.
        receipts_file = self.project / 'output' / 'handoff_receipts.json'
        if receipts_file.is_file():
            receipts = json.loads(receipts_file.read_text(encoding='utf8'))
            keep = {'logic_proof.json'} | ({'outline.json'} if stage == 'storyboard' else set())
            write_json(receipts_file, {k: v for k, v in receipts.items() if k in keep})
        for affected in STAGES[STAGES.index(stage):]:
            self.state["stages"].pop(affected, None)
            if affected != stage:
                self.path(affected).unlink(missing_ok=True)
        # Invalidate current quality pointers, preserving immutable contracts and budgets.
        for name in ('contract','timeline','failure','acceptance'):
            (self.project/'output/quality'/(name+'.json')).unlink(missing_ok=True)
        self.state["pending_stage"] = stage
        self.state["history"].append({"stage": stage, "version": version_of(document), "author": author, "at": time.time()})
        self.persist()

    def approve(self, stage, version):
        if self.state.get("pending_stage") != stage:
            raise ReviewConflict("请先确认当前等待审核的阶段。")
        self.check_version(stage, version)
        self.state["stages"][stage] = {"version": version, "approved_version": version, "approved_by": "human", "approved_at": time.time()}
        self.state.pop("pending_stage", None)
        self.persist()

    def snapshot(self):
        documents = {}
        for stage in STAGES:
            if self.path(stage).is_file():
                document = self.document(stage)
                documents[stage] = {"document": document, "version": version_of(document), "approved": self.state["stages"].get(stage, {}).get("approved_version") == version_of(document)}
        return {"auto_approve": self.state["auto_approve"], "pending_stage": self.state.get("pending_stage"), "documents": documents, "history": self.state["history"][-30:]}
