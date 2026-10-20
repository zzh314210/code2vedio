# vedio.myaihub.asia 当前部署

正式站：https://vedio.myaihub.asia 。Go 用户/API服务 + 私有 Python worker + React/Vite；已移除旧浏览器 Basic Auth。产品说明及样例验收见 [PRODUCT_UPGRADE.md](PRODUCT_UPGRADE.md)，用户系统/计费见 [USER_SYSTEM.md](USER_SYSTEM.md)，接口见 [API.md](API.md)，剪辑依赖见 [EDITING.md](EDITING.md)。

## 运行

- `code2vedio`：Go，`api/bin/frame-api`，127.0.0.1:7860，经Nginx HTTPS。
- `code2vedio-worker`：Python，`private/worker.sock`，仅接受Go签名用户/任务。
- `web/dist`：已构建网页与经过验收的公开样片。
- Docker `code2video-worker:0.1`：Manim0.21、Pillow12.1、FFmpeg、Noto CJK；非root、禁网、只读根、单项目挂载。整个项目共用 2.5 核 / 2 GiB 物理内存 / 4 GiB 额外 Swap 上限，包含 Docker 渲染；编码队列显式有界。
- `.venv-editing` 与 `private/models`：固定版本 CPU/int8 Whisper、PySceneDetect、OpenTimelineIO，无需额外收费语音接口。

队列、管理员调序、资源与 24 小时文件保存见 [QUEUE_AND_STORAGE.md](QUEUE_AND_STORAGE.md)。尚未开始的任务可在重启后恢复，运行中的任务不能自动重放；必须先检查运行状态，不要为了发布而终止用户正在制作的任务。公开样片与默认资产永久保存。

## 构建与发布

```bash
GOPATH=/data/code2vedio/.tmp/gopath GOCACHE=/data/code2vedio/.tmp/gocache .tmp/toolchain/go/bin/go -C api test ./...
GOPATH=/data/code2vedio/.tmp/gopath GOCACHE=/data/code2vedio/.tmp/gocache .tmp/toolchain/go/bin/go -C api build -trimpath -o ../.tmp/release-frame-api .
npm --prefix web run build -- --outDir ../.tmp/release-web --emptyOutDir
```

先在隔离预览环境测试，再备份正式二进制、前端、私有配置与SQLite。将已验收产物替换到正式路径，仅重启 `code2vedio-worker` 与 `code2vedio`。通常无需改Nginx。发布后检查公开示例、登录、个人作品与受保护下载。

运维：`systemctl status code2vedio code2vedio-worker`；日志：`journalctl -u code2vedio -u code2vedio-worker`。管理员初始凭据位于 `private/admin-access.txt`，不要复制到提交、日志或工单。

## 数据及回滚

账号数据库与加密密钥位于 `private`，必须一起备份；SQLite使用backup API。作品在 `video_projects`，个人资料库在 `private/libraries`。用户密钥不进入前端、Git或公开样片。回滚时恢复同一份二进制/前端/代码快照，然后重启两项服务；若修改了用户数据格式，先检查兼容性。本次新增任务类型未改变旧作品归属。

最新一轮背景音乐、队列与资源部署结果见 [MUSIC_QUEUE_ACCEPTANCE.md](MUSIC_QUEUE_ACCEPTANCE.md)，发布前版本 `3f5b830fcd7499c53772ee9e40e3d3bbca9997bf`。较早的视频模板验收见 `RELEASE_ACCEPTANCE.md`。

## 隔离验收站

https://vedio.myaihub.asia:8443/ 使用独立 `.tmp/staging` 账号、配置和作品，Cookie为 `frame_preview_session`。`code2vedio-preview-api` / `code2vedio-preview-worker` 是临时systemd单元，不随服务器重启恢复，不能代替正式站。预览关闭时仅操作这两个单元和独立Nginx8443配置，不影响正式443。
