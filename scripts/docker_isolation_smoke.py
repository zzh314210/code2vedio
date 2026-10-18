import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from execution import project_lock, render_command
from media import probe


SCENE = """from manim import *
import json, os
from pathlib import Path

class IsolationScene(Scene):
    def construct(self):
        project = Path.cwd().parent
        root = Path(project.anchor)
        assert os.getuid() != 0
        assert not os.environ.get('C2V_TEST_SECRET')
        assert not (project.parent / 'second/sentinel.txt').exists()
        assert not (project.parent / 'first/sentinel.txt').exists()
        try:
            (root / 'isolation-forbidden.txt').write_text('escape')
        except OSError:
            pass
        else:
            raise AssertionError('Container root is writable')
        for key in ('HOME', 'TMP', 'TEMP', 'XDG_CACHE_HOME'):
            assert Path(os.environ[key]).is_relative_to(project)
        identity = (project / 'sentinel.txt').read_text()
        (project / 'worker-result.json').write_text(json.dumps({'identity': identity, 'uid': os.getuid()}))
        self.add(Text(identity))
        self.wait(0.2)
"""


def check():
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("Real Docker acceptance requires Docker; no mock or trusted fallback")
    subprocess.run([docker, "info"], check=True, capture_output=True, timeout=30)
    image = os.environ.get("C2V_WORKER_IMAGE", "code2video-worker:0.1")
    subprocess.run([docker, "image", "inspect", image], check=True, capture_output=True, timeout=30)
    with tempfile.TemporaryDirectory(prefix="c2v-real-container-") as temporary:
        root = Path(temporary)
        projects = [root / "first", root / "second"]
        for project in projects:
            (project / "output").mkdir(parents=True)
            (project / "code/runtime").mkdir(parents=True)
            if os.name != "nt":
                project.chmod(0o777)
                (project / "output").chmod(0o777)
            (project / "sentinel.txt").write_text(project.name, encoding="utf-8")
            (project / "output/scene.py").write_text(SCENE, encoding="utf-8")
        def worker(project):
            with project_lock(project):
                render_command([sys.executable, "-m", "manim", "-ql", "--media_dir", str(project / "output/media"), str(project / "output/scene.py"), "IsolationScene"], project, project / "output", {"backend": "docker", "image": image}, 300)
            result = json.loads((project / "worker-result.json").read_text())
            assert result["identity"] == project.name
            assert result["uid"] != 0
            assert (project / "sentinel.txt").read_text() == project.name
            assert probe(next((project / "output/media/videos").rglob("IsolationScene.mp4")))["duration"] > 0
            return result
        previous_secret = os.environ.get("C2V_TEST_SECRET")
        os.environ["C2V_TEST_SECRET"] = "local-isolation-probe-not-a-real-secret"
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(worker, projects))
        finally:
            if previous_secret is None:
                os.environ.pop("C2V_TEST_SECRET", None)
            else:
                os.environ["C2V_TEST_SECRET"] = previous_secret
        assert results[0]["identity"] != results[1]["identity"]
    print("PASS: real parallel Docker Manim workers, separate artifacts, non-root, read-only root, no sibling mount, minimal environment")
    print("Scope excludes host plugins, kernel exploits and independent audio acceptance")


if __name__ == "__main__":
    check()
