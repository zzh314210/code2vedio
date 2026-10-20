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


class RenderInfrastructureError(RuntimeError):
    """A host/resource failure which model-generated code cannot repair."""


def _bounded_encoder_arguments(arguments, working):
    arguments = list(arguments)
    if arguments[1:3] != ["-m", "manim"]:
        return arguments
    # Manim 0.21's serial encoder has an unbounded frame queue. Two in-flight
    # encoders enable its supported backpressure; each holds at most two
    # pending frames, including when a long 1080p animation outruns encoding.
    config_file = validate_output(working, "render-worker.cfg")
    config_file.write_text("[CLI]\nmax_inflight_encoders = 2\nencoder_queue_size = 2\n", encoding="utf-8")
    return arguments[:3] + ["--config_file", str(config_file)] + arguments[3:]


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


def _run(arguments, directory, environment, timeout, *, container=False):
    try:
        result = subprocess.run(arguments, cwd=directory, env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as failure:
        raise RenderInfrastructureError("渲染超时，请稍后重试或缩短视频；没有额外调用模型修改代码。") from failure
    except OSError as failure:
        raise RenderInfrastructureError("渲染服务未能启动，请稍后重试。") from failure
    if result.returncode:
        detail = (result.stderr or result.stdout or "Render failed")[-10000:]
        message = f"Render exited with code {result.returncode}:\n{detail}"
        if result.returncode in (-9, 137) or any(marker in detail for marker in ("MemoryError", "Cannot allocate memory", "No space left on device", "Resource temporarily unavailable")):
            raise RenderInfrastructureError("渲染资源不足或进程被终止，请稍后重试；没有额外调用模型修改代码。\n" + message)
        if container and result.returncode in (125, 126, 127):
            raise RenderInfrastructureError("渲染容器启动失败，请稍后重试。\n" + message)
        raise RuntimeError(message)
    return result.stdout


def render_command(arguments, project, directory, settings, timeout):
    root = Path(project).resolve(strict=True)
    working = validate_output(root, directory)
    working.mkdir(parents=True, exist_ok=True)
    timeout = float(timeout)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Render timeout must be positive and finite")
    environment = render_environment(root)
    arguments = _bounded_encoder_arguments(arguments, working)
    backend = settings.get("backend", "trusted")
    if backend == "trusted":
        warnings.warn("Trusted local rendering is NOT a security sandbox", RuntimeWarning, stacklevel=2)
        return _run(list(arguments), working, environment, timeout)
    if backend != "docker":
        raise ValueError("Unknown render backend; expected trusted or docker")
    docker = shutil.which("docker")
    if not docker:
        raise RenderInfrastructureError("Docker is required for isolated rendering; local fallback is forbidden")
    if len(arguments) < 4 or list(arguments[1:3]) != ["-m", "manim"]:
        raise ValueError("Docker executor accepts only python -m manim commands")
    image = settings.get("image", "code2video-worker:0.1")
    if not isinstance(image, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._/:@-]*", image):
        raise ValueError("Invalid worker image")
    cpus = float(os.getenv('C2V_RENDER_CPUS', settings.get("cpus", 2)))
    memory = str(os.getenv('C2V_RENDER_MEMORY', settings.get("memory", "2g")))
    memory_swap = str(os.getenv('C2V_RENDER_MEMORY_SWAP', memory))
    cgroup_parent = os.getenv('C2V_RENDER_CGROUP_PARENT', '')
    pids = int(settings.get("pids_limit", 256))
    if not math.isfinite(cpus) or cpus <= 0 or not re.fullmatch(r"[1-9][0-9]*[kKmMgG]", memory) or pids < 16 or pids > 4096:
        raise ValueError("Invalid container resource limits")
    if not re.fullmatch(r'[1-9][0-9]*[kKmMgG]', memory_swap) or (cgroup_parent and not re.fullmatch(r'[A-Za-z0-9_.-]+\.slice',cgroup_parent)):
        raise ValueError('Invalid shared render resource limits')
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
    command = [docker, "run", "--rm", "--pull=never", "--name", name, "--read-only", "--network=none", "--user", identity, "--cap-drop=ALL", "--security-opt=no-new-privileges", "--cpus", str(cpus), "--memory", memory, "--memory-swap", memory_swap, "--pids-limit", str(pids), "--ulimit", "nofile=1024:1024", "--mount", f"type=bind,source={root},target=/project", "--workdir", _container_path(root, working)]
    if cgroup_parent:command.extend(['--cgroup-parent',cgroup_parent])
    for key, value in environment.items():
        if key in ("PATH", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "LANG", "LC_ALL"):
            continue
        if Path(value).is_absolute() or ntpath.isabs(value):
            value = _container_path(root, value)
        command.extend(["--env", key + "=" + value])
    command.extend([image, "python", *converted])
    try:
        return _run(command, working, environment, timeout, container=True)
    finally:
        try:
            subprocess.run([docker, "rm", "--force", name], capture_output=True, timeout=30, env=environment)
        except (OSError, subprocess.TimeoutExpired):
            pass
        for scene in scenes:
            scene.unlink(missing_ok=True)
