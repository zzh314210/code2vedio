# Frame 视频工作台

独立运行的教学视频流水线，不需要 Codex。八阶段保持为 outline → storyboard → audio → assets → code → render → review → compose。包含深色演示、清晰图解与手绘课堂三种通用主题；风格规则与课题内容分离。

## 安装与启动（Windows）

需要 Python 3.12（64位）、Node.js/npm；Manim 依赖和字体检查由安装脚本执行。Docker 渲染还需安装 Docker；本地 CPU 配音是可选项。

```powershell
git clone https://github.com/zzh314210/code2vedio.git
cd code2vedio
powershell -ExecutionPolicy Bypass -File scripts/start_studio.ps1 -Install
```

安装后访问 http://127.0.0.1:7860；后续双击根目录 **Start Studio.cmd**。首次安装会从 `config.studio.example.json` 创建未跟踪的 `config.local.json`，不覆盖已有本机配置。配置面板填写生成与视觉审核的 API Key，选择风格、填写提示词及素材，即可创建任务。默认1080p/30fps，支持横竖屏和最长120秒。

面板输入的密钥仅保存在后端内存；不写浏览器存储或项目文件，重启后需重新输入。也可在本机私有配置文件或 `C2V_TEXT_API_KEY` / `C2V_VISION_API_KEY` 环境变量中设置。`config.qwen-tts.local.json` 存在时优先加载；不要提交这些文件。

## Linux 网页部署

当前公网版采用 Go 用户后端与 Python 私有渲染 Worker，部署和账户说明以 [`deploy/USER_SYSTEM.md`](deploy/USER_SYSTEM.md) 为准；原单机部署记录见 [`deploy/README.md`](deploy/README.md)。公网首页可直接浏览创作面板并填写需求，实际操作时再登录，同一页面内的登录往返保留草稿。个人作品、素材、余额与加密保存的模型配置按用户隔离。

公网域名需通过 `C2V_ALLOWED_ORIGINS` 显式加入允许来源，例如 `https://vedio.myaihub.asia`；多个来源用逗号分隔。未设置时仍仅允许原有本机工作台来源。上文 Windows 单机版的内存配置说明不适用于 Go 多用户部署。

## 模型与配音

示例使用阿里云兼容接口，地址可在私有配置中调整。文本模型按 `kimi-k3 → deepseek-v4-flash-0731 → deepseek-v4.1-flash` 降级；视觉模型按 `deepseek-v4.1-flash → qwen3.7-flash → qwen3.8-flash` 降级；请求失败时保留地址、密钥和图片输入切换模型。可用性、计费及模型支持范围以自己的阿里云服务为准。

默认使用阿里云 TTS，复用生成密钥。参考 `config.qwen-tts.example.json` 选择可用音色与模型。

## 大纲与分镜审核

新任务默认先生成大纲；支持表单或 JSON 编辑、保存草稿、输入意见让 AI 修改。确认大纲后才生成分镜，分镜同样需要确认后才开始配音和动画生产。AI 修改完成后仍等待人工确认。

可在创建时勾选“免审核，自动完成”，或在等待确认时开启。确认绑定内容的 SHA256 版本；旧页面保存返回409。编辑大纲会归档历史并废弃旧分镜。项目、审核状态和历史存于 `video_projects/`，重启后恢复；等待审核不会占用生产线程。按真实配音测时若触发分镜精简，人工模式会再次等待确认。

## 可独立调用的素材功能

复用 Agent Reach 的 WebChannel/Jina Reader，以及 bili-cli / bilibili-api-python，提供网页、B站、知乎和本地素材库检索。运行时直接调用 Python/CLI，不执行 Codex skill。依赖锁定在 `requirements-teaching.txt`，安装主环境时一并安装。

行测/讲题任务会在大纲阶段先检索现有讲解；指定链接或已入库素材也会触发检索。至少取得两份实际正文/字幕，再选定一个主来源，校验原文引文，提取“步骤、理由、考生疑问、可视化动作”，注入大纲和分镜。检索不足会保留错误，不回退到虚构教程。题目是否真题仍需独立核验。

```powershell
.venv\Scripts\python.exe scripts\teaching_sources.py search "数量关系 精讲" --platform web
.venv\Scripts\python.exe scripts\teaching_sources.py search "数量关系 行测" --platform bilibili
.venv\Scripts\python.exe scripts\teaching_sources.py ingest "公开讲解文章或B站完整URL"
.venv\Scripts\python.exe scripts\teaching_sources.py batch references\urls.txt
.venv\Scripts\python.exe scripts\teaching_sources.py local references\lesson.srt
.venv\Scripts\python.exe scripts\teaching_sources.py search "数量关系" --platform library
```

HTTP接口：

- `POST /api/sources/search`：`{query,platform,limit}`
- `POST /api/sources/ingest`：`{urls:[...]}`
- `GET /api/sources/{id}`
- `GET /api/jobs/{id}/planning`
- `PUT /api/jobs/{id}/planning/{outline|storyboard}`：`{version,document}`
- `POST /api/jobs/{id}/planning/{stage}/revise`：`{version,document,feedback}`
- `POST /api/jobs/{id}/planning/{stage}/approve`：`{version}`
- `PATCH /api/jobs/{id}/planning-mode`：`{auto_approve:true}`

素材正文、哈希和时间片段存入 SQLite FTS5；原始检索与解题证据保存于各项目的 `output/teaching_research`。B站优先读取字幕，缺字幕时可启用 faster-whisper CPU/int8 转写公开音轨。只读取显式保存的B站凭据，不扫描浏览器Cookie。知乎等网站可能拒绝访问；转写可能误识别数字和术语。字幕提取的是口述内容，不代表理解全部视频画面。

## 可选本地 CPU 语音与转写

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_local_speech.ps1
```

安装脚本在 `D:/Code2VideoCache` 创建独立 CPU 环境与模型，可用 `-CacheRoot` 改变位置。需要数GB磁盘和模型下载时间，不会在主渲染环境安装 PyTorch。

本地 TTS 使用 GPT-SoVITS v2ProPlus。准备固定参考音频及其准确逐字稿，按 `config.gpt-sovits.example.json` 创建 `config.gpt-sovits.local.json` 并修改路径。安装脚本不会自动创建音色参考；示例路径需要按机器调整。本机配置存在后，启动工作台会自动启动本地语音后台服务，面板可切换阿里云。单独启动：`powershell -File scripts/start_speech.ps1`，自定义安装目录需加 `-CacheRoot`。服务仅监听127.0.0.1:9880，日志在 `.tmp/speech-cpu.*.log`。首次加载需等待，合成速度取决于CPU；字幕时间目前按文本估算。

ASR 可通过 `scripts/download_whisper_model.py` 下载本地模型，并在私有配置添加 `teaching_research.asr`：`enabled`、`python`（独立环境解释器）、`model`（模型目录）、`max_seconds`、`timeout`。参考 `scripts/transcribe_cpu.py`。

## 通用手绘风格

主题位于 `style_skills/builtin`，技术指导位于 `style_skills/technical`。项目创建时快照风格与运行时，续跑使用自己的版本。手绘运行时预加载 Rough.js 4.6.6 与 Perfect Freehand 1.2.2，支持按任意坐标构造形状和笔迹；代码与许可证保存在 `src/vendor/handdrawn`，渲染时不下载。Node.js需在PATH中。

生成代码需允许执行；AST检查不构成安全沙箱，可用 `Dockerfile.worker` 构建隔离渲染环境。视觉审核采用逐段抽帧、修复和复审，不保证未抽到的瞬间或教学内容绝对无误。

## 实现测试

```powershell
.venv\Scripts\python.exe scripts\planning_system_smoke.py
.venv\Scripts\python.exe scripts\teaching_research_smoke.py
.venv\Scripts\python.exe scripts\studio_api_smoke.py
cd web
npm ci
npm run build
```

浏览器测试额外安装 `playwright` 和 Chromium，启动工作台后运行 `scripts/planning_web_smoke.py` 或 `scripts/studio_web_smoke.py`。前者隔离HTTP测试数据，后者默认只做交互检查，不创建真实视频。模型降级测试使用模拟请求，不表示所有模型都已在当前账号上获得配额。

## 仓库范围

此仓库提交应用源码、通用风格规则、第三方运行库及许可、安装脚本、测试和配置示例。`deliverables/`、`video_projects/`、`references/`、`tasks/`、抓取研究资料、开发skill、本地密钥、虚拟环境、模型权重、前端构建产物和生成视频不随实现分发；首次启动作品库为空。原项目已有的历史演示资料不属于本次新增产物。
