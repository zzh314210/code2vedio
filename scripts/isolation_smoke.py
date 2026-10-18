import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import execution


def check():
    with tempfile.TemporaryDirectory(prefix="c2v-isolation-") as temporary:
        base = Path(temporary)
        projects = [base / "first", base / "second"]
        for project in projects:
            (project / "code/runtime").mkdir(parents=True)
        first, second = projects
        for escaped in (first / "../second/result.txt", second / "result.txt"):
            try:
                execution.validate_output(first, escaped)
            except ValueError:
                pass
            else:
                raise AssertionError("Cross-project path accepted")
        assert execution.validate_output(first, "output/result.txt") == first / "output/result.txt"
        child = "import sys,time;sys.path.insert(0,sys.argv[1]);from execution import project_lock;\nwith project_lock(sys.argv[2]):\n print('locked',flush=True);time.sleep(30)"
        process = subprocess.Popen([sys.executable, "-c", child, str(Path(execution.__file__).parent), str(first)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            assert process.stdout.readline().strip() == "locked"
            try:
                with execution.project_lock(first):
                    raise AssertionError("Concurrent project lock accepted")
            except RuntimeError:
                pass
            with execution.project_lock(second):
                pass
        finally:
            process.kill()
            process.communicate(timeout=10)
        with execution.project_lock(first):
            pass
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake", "AWS_SECRET_ACCESS_KEY": "fake", "CUSTOM_TOKEN": "fake", "PYTHONPATH": "untrusted", "HTTP_PROXY": "secret-proxy"}):
            environment = execution.render_environment(first)
            assert not any(key in environment for key in ("OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "CUSTOM_TOKEN", "HTTP_PROXY"))
            for key in ("HOME", "TMP", "TEMP", "XDG_CACHE_HOME", "PYTHONPATH"):
                assert Path(environment[key]).is_relative_to(first)
        def worker(project):
            with execution.project_lock(project):
                execution.render_command([sys.executable, "-c", "import os,pathlib,time;time.sleep(.2);pathlib.Path('result.txt').write_text(os.environ['HOME'])"], project, project / "output", {"backend": "trusted"}, 10)
            return (project / "output/result.txt").read_text()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, projects))
        assert results == [str(project / ".worker/home") for project in projects]
        with patch.object(execution.shutil, "which", return_value=None):
            try:
                execution.render_command([sys.executable, "-m", "manim"], first, first, {"backend": "docker"}, 10)
            except RuntimeError as failure:
                assert "fallback is forbidden" in str(failure)
            else:
                raise AssertionError("Docker failure downgraded")
        directory = first / "output"
        script = directory / "scene.py"
        script.write_text("assets = " + repr({"sample": str(first / "input/image.png")}) + "\n", encoding="utf-8")
        arguments = [sys.executable, "-m", "manim", "--media_dir", str(directory / "media"), str(script), "LessonScene"]
        recorded = []
        def fake_run(command, **kwargs):
            recorded.append((command, kwargs))
            if "run" in command:
                translated = script.with_name("scene.container.py").read_text(encoding="utf-8")
                assert "/project/input/image.png" in translated
                assert str(first) not in translated
            return subprocess.CompletedProcess(command, 0, "success", "")
        with patch.object(execution.shutil, "which", return_value="docker"), patch.object(execution.subprocess, "run", side_effect=fake_run):
            assert execution.render_command(arguments, first, directory, {"backend": "docker"}, 10) == "success"
        command, kwargs = recorded[0]
        for flag in ("--read-only", "--network=none", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--cpus", "--memory", "--pids-limit"):
            assert flag in command
        assert command.count("--mount") == 1
        assert command[command.index("--mount") + 1] == f"type=bind,source={first},target=/project"
        assert command[command.index("--user") + 1].split(":")[0] != "0"
        assert not script.with_name("scene.container.py").exists()
        assert recorded[-1][0][1:3] == ["rm", "--force"]
        def timeout_run(command, **kwargs):
            if "run" in command:
                raise subprocess.TimeoutExpired(command, 1)
            return subprocess.CompletedProcess(command, 0, "", "")
        with patch.object(execution.shutil, "which", return_value="docker"), patch.object(execution.subprocess, "run", side_effect=timeout_run):
            try:
                execution.render_command(arguments, first, directory, {"backend": "docker"}, 1)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Timeout accepted")
        assert not script.with_name("scene.container.py").exists()
    print("PASS: project boundaries, cross-process/crash locks, parallel workers, minimal environment, Docker fail-closed/flags/path translation/cleanup")
    print("Docker security assertions mocked; real container execution is not validated by this test")


if __name__ == "__main__":
    check()
