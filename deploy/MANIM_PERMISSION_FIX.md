# Manim 线上权限修复（2026-10-20）

## 故障与原因

线上任务在 `code` 阶段报错：

```text
[Errno 13] Permission denied: '/home/admin1/.config/manim/manim.cfg'
```

`pipeline.validate_snippet()` 为检查模型是否编造 Manim 类名，在服务进程中直接导入了 Manim。Manim 0.21 导入时用 `Path.home()` 读取用户配置，即便指定 `XDG_CONFIG_HOME` 也不会跳过这个位置。生产 worker 的 `ProtectHome=true` 正确阻止了访问，尚未进入 Docker 渲染便失败。

## 修复

- 在独立短生命周期进程中读取已安装 Manim 的 API 名称，使用现有 `render_environment()` 为该进程创建独立临时目录并过滤环境变量。
- 缓存 API 名称；主 worker 不再导入或常驻加载 Manim，也不修改主进程环境。
- 此进程只加载受信任的库，不执行模型代码；生成代码仍按原有 Docker 隔离策略渲染。
- 在代码生成的模型请求之前检查校验环境；环境错误按基础设施故障处理，不交给模型反复修复。
- 不变更 `/home` 权限、服务用户、`ProtectHome`、`ProtectSystem` 或 Docker 资源上限。

## 验收

先在临时 systemd 服务中以 `admin1`、`ProtectHome=true`、`ProtectSystem=strict`、`PrivateTmp=true`、`NoNewPrivileges=true` 复现原始调用栈，再使用相同限制执行：

```bash
.venv/bin/python scripts/manim_validation_smoke.py \
  --docker-project /data/code2vedio/.tmp/manim-permission-acceptance/project
.venv/bin/python scripts/isolation_smoke.py
.venv/bin/python scripts/render_reliability_smoke.py
```

通过项：真实库加载与代码校验、缓存复用、临时目录清理、父进程环境不变、虚构类名和危险语法拒绝、环境故障后恢复、Docker 实际渲染与 FFmpeg 完整解码。动画为 1 秒、1080p、30 fps，包含中文和图形动画；验收不调用收费模型。

仅需在任务队列空闲时重启生产和预览 Python worker；Go API 和前端无须重建。失败任务可使用原有“重试”入口，继续复用已保存的大纲、分镜和配音。此次修复不改变项目配置或缓存指纹。
