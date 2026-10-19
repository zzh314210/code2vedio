# vedio.myaihub.asia 部署

> 2026-10-19 已升级为 Go 用户面板 + 私有 Python worker。旧 Basic Auth 已移除。当前架构、账号凭据位置、计费开关和备份说明见 [USER_SYSTEM.md](USER_SYSTEM.md)，开放接口见 [API.md](API.md)。以下为首次部署的历史记录。

源代码：`/data/code2vedio`，基于 main 提交 `91058e66341401d388244cac4ce2e0c94ddb3e3d`，SSH remote 为 `git@github.com:zzh314210/code2vedio.git`。

生产入口：https://vedio.myaihub.asia 。Nginx Basic Auth 用户名为 `studio`，随机密码在仓库外 `/data/code2vedio-access.txt`（0600）。站点与 API 均要求认证。配置面板的模型密钥只存后端内存，重启后需要重新输入；可通过被 gitignore 的私有配置持久化。

## 运行环境

Ubuntu 24.04、Python 3.12 虚拟环境 `.venv`、FFmpeg、Python 开发头文件、Cairo/Pango、Noto CJK 和 LaTeX。前端通过已有 `node:22.23-alpine` 镜像构建；系统 Node 18 仅用于已有运行时代码。

`config.local.json` 从 Studio 示例生成，字体设为 `Noto Sans CJK SC`；`execution.backend=docker`，镜像 `code2video-worker:0.1`。单个渲染容器限制 1 CPU / 1 GiB，禁用网络，根文件系统只读，仅挂载当前视频项目。服务端线程池一次生产一个任务，避免与机器上其他站点争用内存。

服务文件：`/etc/systemd/system/code2vedio.service`，仅监听 `127.0.0.1:7860`，启用开机启动和失败重启。允许的网页来源由 `C2V_ALLOWED_ORIGINS=https://vedio.myaihub.asia` 指定，保留原有本机来源校验，其他网页写入仍返回 403。

Nginx 配置：`/etc/nginx/sites-available/vedio.myaihub.asia`。认证哈希：`/etc/nginx/code2vedio.htpasswd`。证书：`/etc/letsencrypt/live/vedio.myaihub.asia/`。Certbot 定时续期，deploy hook 在续期后检查并重载 Nginx。

## 运维

```bash
sudo systemctl status code2vedio
sudo journalctl -u code2vedio -n 100 --no-pager
sudo systemctl restart code2vedio
sudo nginx -t
sudo systemctl reload nginx
```

作品、上传材料与规划记录保存在 `video_projects/`；检索库保存在 `references/`。备份时包含这些目录及私有配置，凭据文件独立保存，不提交 Git。服务重启后未完成生产任务标为失败，可从界面继续；等待规划审核的任务可恢复。

## 更新

先保存或提交本地部署修改（当前未推送），检查 `git status`，再以 SSH fetch 并评估新提交，不执行强制重置。依赖变动时更新 `.venv`。前端构建：

```bash
docker run --rm --user 1000:1000 --memory=768m --cpus=1 \
  -e npm_config_cache=/tmp/npm-cache \
  -v /data/code2vedio/web:/app -w /app node:22.23-alpine \
  sh -c 'npm ci --registry=https://registry.npmjs.org --no-audit --no-fund && npm run build'
```

渲染镜像更新：`docker build -f Dockerfile.worker -t code2video-worker:0.1 .`。验证通过后重启工作台；`MemoryMax` 仅约束后端，Docker worker 使用自己的资源限制。

此部署未配置或调用付费模型，也未安装可选 GPT-SoVITS/Whisper 权重。首次使用需在网页配置生成与视觉审核密钥；默认使用示例里的阿里云模型及 TTS，可用模型与额度由账号决定。

## 验收

```bash
.venv/bin/python src/agent.py --doctor
.venv/bin/python scripts/studio_api_smoke.py
.venv/bin/python scripts/planning_system_smoke.py
.venv/bin/python scripts/teaching_research_smoke.py
.venv/bin/python scripts/docker_isolation_smoke.py
.venv/bin/python deploy/check_render.py
/data/code2vedio-browser-venv/bin/python deploy/check_site.py
```

浏览器验收使用独立环境 `/data/code2vedio-browser-venv` 的 Playwright/Chromium，读取仓库外访问凭据。截图和合成视频位于 `.tmp/deployment-check`、`.tmp/deployment-render`，不进入作品库或 Git。公网 Cloudflare 会阻止默认 Python User-Agent，HTTP 检查使用浏览器标识。所有验收均不请求付费模型。

2026-10-18 验收完成：前端生产构建、Python doctor / pip check、Studio API、规划审核、素材证据测试、公网 HTTPS 浏览器、390/768 手机平板布局、密码认证、来源校验、生产权限下 1920×1080 / 30fps 中文 + LaTeX + Rough.js 渲染、双项目真实 Docker 隔离全部通过。工作台 systemd 服务已启用，部署完成时无异常重启。未进行真实模型生成和云 TTS 验证，因为尚未提供模型密钥。

已构建渲染镜像 ID：`sha256:3d60b7107b6e3adeca2c558be1d9603fb1f259545bc60370c834bd6f056bdbef`。代码和部署修改只保留在本机工作区，未推送 GitHub。
