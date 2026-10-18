import ast
import contextlib
import math
import ntpath
import os
import re
import shutil
import subprocess
import threading
import uuid
import warnings
from pathlib import Path


_project_locks = threading.local()


def validate_output(project, output):
    root = Path(project).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Project must be an existing directory")
    candidate = Path(output)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Output escapes the current project")
    return resolved


@contextlib.contextmanager
def project_lock(project):
    root = Path(project).resolve(strict=True)
    owned = getattr(_project_locks, "owned", None)
    if owned is None:
        owned = _project_locks.owned = set()
    if root in owned:
        yield root
        return
    filename = validate_output(project, ".project.lock")
    handle = filename.open("a+b")
    acquired = False
    try:
        if filename.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError as failure:
            raise RuntimeError("Project is already running; concurrent writes are forbidden") from failure
        owned.add(root)
        yield root
    finally:
        owned.discard(root)
        if acquired:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def render_environment(project):
    root = Path(project).resolve(strict=True)
    environment = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "LANG", "LC_ALL") if key in os.environ}
    paths = {"home": root / ".worker/home", "tmp": root / ".worker/tmp", "cache": root / ".worker/cache", "config": root / ".worker/config", "data": root / ".worker/data"}
    for directory in paths.values():
        validate_output(root, directory).mkdir(parents=True, exist_ok=True)
    environment.update({"HOME": str(paths["home"]), "USERPROFILE": str(paths["home"]), "TMP": str(paths["tmp"]), "TEMP": str(paths["tmp"]), "TMPDIR": str(paths["tmp"]), "XDG_CACHE_HOME": str(paths["cache"]), "XDG_CONFIG_HOME": str(paths["config"]), "XDG_DATA_HOME": str(paths["data"]), "APPDATA": str(paths["config"]), "LOCALAPPDATA": str(paths["cache"]), "MPLCONFIGDIR": str(paths["config"] / "matplotlib"), "PYTHONPATH": str(validate_output(root, "code/runtime")), "PYTHONSAFEPATH": "1", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
    return environment


def _container_path(project, value):
    root = Path(project).resolve(strict=True)
    return "/project/" + validate_output(root, value).relative_to(root).as_posix()


def _container_scene(project, script):
    root = Path(project).resolve(strict=True)
    source = validate_output(root, script)

    class ProjectPaths(ast.NodeTransformer):
        def visit_Constant(self, node):
            if isinstance(node.value, str) and (Path(node.value).is_absolute() or ntpath.isabs(node.value)):
                node.value = _container_path(root, node.value)
            return node

    tree = ProjectPaths().visit(ast.parse(source.read_text(encoding="utf-8")))
    destination = validate_output(root, source.with_name(source.stem + ".container.py"))
    destination.write_text(ast.unparse(tree) + "\n", encoding="utf-8")
    return destination


def _run(arguments, directory, environment, timeout):
    try:
        result = subprocess.run(arguments, cwd=directory, env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as failure:
        raise RuntimeError("Render exceeded its timeout") from failure
    except OSError as failure:
        raise RuntimeError("Render executor could not start") from failure
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "Render failed")[-10000:])
    return result.stdout


def render_command(arguments, project, directory, settings, timeout):
    root = Path(project).resolve(strict=True)
    working = validate_output(root, directory)
    working.mkdir(parents=True, exist_ok=True)
    timeout = float(timeout)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Render timeout must be positive and finite")
    environment = render_environment(root)
    backend = settings.get("backend", "trusted")
    if backend == "trusted":
        warnings.warn("Trusted local rendering is NOT a security sandbox", RuntimeWarning, stacklevel=2)
        return _run(list(arguments), working, environment, timeout)
    if backend != "docker":
        raise ValueError("Unknown render backend; expected trusted or docker")
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("Docker is required for isolated rendering; local fallback is forbidden")
    if len(arguments) < 4 or list(arguments[1:3]) != ["-m", "manim"]:
        raise ValueError("Docker executor accepts only python -m manim commands")
    image = settings.get("image", "code2video-worker:0.1")
    if not isinstance(image, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._/:@-]*", image):
        raise ValueError("Invalid worker image")
    cpus = float(settings.get("cpus", 2))
    memory = str(settings.get("memory", "2g"))
    pids = int(settings.get("pids_limit", 256))
    if not math.isfinite(cpus) or cpus <= 0 or not re.fullmatch(r"[1-9][0-9]*[kKmMgG]", memory) or pids < 16 or pids > 4096:
        raise ValueError("Invalid container resource limits")
    if "," in str(root):
        raise ValueError("Docker project mount path cannot contain commas")
    converted = []
    scenes = []
    for argument in arguments[1:]:
        value = str(argument)
        if Path(value).is_absolute() or ntpath.isabs(value):
            path = validate_output(root, value)
            if path.suffix == ".py":
                path = _container_scene(root, path)
                scenes.append(path)
            value = _container_path(root, path)
        converted.append(value)
    identity = f"{os.getuid()}:{os.getgid()}" if os.name != "nt" and os.getuid() != 0 else "65532:65532"
    name = "c2v-render-" + uuid.uuid4().hex
    command = [docker, "run", "--rm", "--pull=never", "--name", name, "--read-only", "--network=none", "--user", identity, "--cap-drop=ALL", "--security-opt=no-new-privileges", "--cpus", str(cpus), "--memory", memory, "--memory-swap", memory, "--pids-limit", str(pids), "--ulimit", "nofile=1024:1024", "--mount", f"type=bind,source={root},target=/project", "--workdir", _container_path(root, working)]
    for key, value in environment.items():
        if key in ("PATH", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "LANG", "LC_ALL"):
            continue
        if Path(value).is_absolute() or ntpath.isabs(value):
            value = _container_path(root, value)
        command.extend(["--env", key + "=" + value])
    command.extend([image, "python", *converted])
    try:
        return _run(command, working, environment, timeout)
    finally:
        try:
            subprocess.run([docker, "rm", "--force", name], capture_output=True, timeout=30, env=environment)
        except (OSError, subprocess.TimeoutExpired):
            pass
        for scene in scenes:
            scene.unlink(missing_ok=True)
