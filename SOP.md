# 通用 CLI 视频流水线操作手册

## 版本技能与隔离运行

内置风格现在显式声明版本，快照保存公共技术技能、阶段风格指导、来源、布局参数和 SHA-256 内容指纹。公共技能适配自 MIT 许可的 manim-composer / manimce-best-practices，许可证保留于 style_skills/technical/LICENSE.upstream.txt；不是原样执行代理 SKILL.md。每次生成、修复、审核均固定注入项目版本，续跑不加载全局新版。

video.layout 支持 classic（标题、品牌、进度及字幕）、minimal（标题和字幕）、canvas（仅字幕）；reset_between_beats 控制清场，exit_fade 控制结尾淡出。默认保持片段间独立变量契约，连续对象模式只适合明确编排的项目。

CLI 全流程持有项目 OS 锁，同一目录并发写入立即拒绝，进程退出自动释放；不要删除锁文件解锁。渲染环境采用白名单，移除宿主 API/云凭证，临时、HOME 和缓存定向到项目 .worker。trusted 后端仍不是安全沙箱，可信 TTS 插件仍在宿主运行。

execution.backend=docker 启用禁网、非 root、只读根、单项目挂载及资源限制；Docker 不可用时拒绝执行，不回退 trusted。构建命令：docker build -f Dockerfile.worker -t code2video-worker:0.1 .。容器使用 fonts-noto-cjk，请配置 video.font=Noto Sans CJK SC。本机未提供 Docker，当前仅验证锁、最小环境、双项目 worker 以及容器参数控制，不能声称真实容器强隔离已验收。

video.target_duration 设置目标秒数：真实配音短于目标时延长末尾画面及补静音，长于预算则报错，不裁掉语音。tasks/vector_dot_10s.json 是真实 GLM/Qwen 十秒点积样片输入。

本手册保留 CLI 操作说明；Web 工作台操作见 [STUDIO.md](STUDIO.md)。

当前同时提供 CLI 与 Frame Web 工作台，启动方式见 [STUDIO.md](STUDIO.md)。前面的研究演示说明为历史资料；当前任务不要求教材或 Markdown。每次生成在 `video_projects/` 下创建一个独立视频项目，不再将任务拆到 examples 和 projects。

### 快速开始

```powershell
.\.venv\Scripts\python.exe src\agent.py --list-styles
.\.venv\Scripts\python.exe src\agent.py --list-tts
.\.venv\Scripts\python.exe src\agent.py --prompt "介绍一款新产品" --style presentation --reference "素材/产品.png" --project "video_projects/product-demo" --plan-only
.\.venv\Scripts\python.exe src\agent.py --project "video_projects/product-demo" --resume --allow-generated-code
```

先运行 `scripts/setup_windows.ps1` 安装环境。`--plan-only` 生成大纲和分镜；`--stop-after` 支持 outline/storyboard/audio/assets/code/render/review/compose。生成 Python 在本机执行，AST 校验不是沙箱，应在无敏感文件的隔离账户中运行。

### 输入和媒体支持

`--task-file` 接收 JSON 的 prompt、style、materials、references、config、tts、review；路径相对于任务 JSON，CLI 参数优先。`--material`、`--reference` 可重复，`--topic` 保留为兼容入口。text 与 vision 分别配置模型/API，支持 Responses 或 Chat Completions；发送图像的规划模型必须支持视觉输入。

- 文本、Markdown、JSON、CSV、代码/YAML 和文本 PDF 可提取上下文；扫描 PDF 没有自动 OCR，保留文件与说明。其他文件归档并记录类型、大小及 SHA-256，不声称都能理解。
- 图像送入 outline/storyboard 规划请求，并可通过运行时 `self.asset(key)` 返回的图像对象加入画面；使用资产清单键，不直接读取任意外部路径。SVG 图标源及授权本地 SVG 保留，文件归档不等于自动注册可用图标。
- 视频抽取三个参考帧用于规划；抽样不是完整时序理解，也不会自动选择剪辑点。
- 音频默认只归档；启用 `materials.transcription.enabled` 并配置其 api_key、base_url、model 后，可通过 OpenAI-compatible 转录接口加入文本上下文和缓存。须人工核对转录；该接口独立于 TTS，真实第三方 ASR 尚未验证。

### 独立项目与秘密保护

`input/materials`、`input/references` 保存输入；`prompts` 保存模板、需求和风格快照；`code/runtime` 保存可信运行时；`output` 保存大纲、分镜、配音、请求记录、日志、字幕和 `final.mp4`。`task.json` 保存需求及项目内输入路径，`settings.json` 脱敏。`prompts/style.json` 保存风格元数据、video 默认值、policy 和四阶段指导；续跑优先读取有效项目快照，即使全局包已修改或删除。缺少阶段项时回退快照 policy；快照格式和风格 id 必须合法且匹配。全局更新不会自动升级已有项目。修改输入或风格后不要盲目复用旧缓存。

密钥使用环境变量/`.env` 或忽略的私有配置，公开示例只放 `${ENV_NAME}` 占位符，不把密钥写入任务、风格包或提交。脱敏配置不是完整隐私保证：原始素材、提示词、请求及转录可能含敏感信息，公开项目目录前应审查。已在聊天中暴露的密钥应轮换。

### 风格与 TTS

Available application styles: `default`, `clean_education`, `3b1b_inspired`, `infographic`, `presentation`, `handdrawn`, `editorial_motion`. Stage-specific guidance falls back to policy.txt when absent; project snapshots bind all four stages to the selected version. handdrawn adds native sketch strokes; editorial_motion adds geometric motion and kinetic typography constraints. These are pipeline policies for external LLMs, not terminal-agent skills. See [style package documentation](style_skills/README.md).

TTS 默认仍为 edge；另有 openai/http/none/qwen_audio。应用可用 `narration.register_tts_provider(name, factory)` 注册；独立 CLI 可发现安装在当前 Python 环境中的 `code2video.tts` entry-point。工厂接收 settings，实例提供 `synthesize(text, destination)`，写入流水线可用音频并返回包含 duration 的字典，可附带 subtitles。`--list-tts` 列出供应商，插件执行 Python，必须可信。

Qwen 使用公开预设 `config.qwen-tts.example.json`，密钥由 `C2V_QWEN_TTS_API_KEY` 提供。provider 为 `qwen_audio`，从 base_url 的同源主机调用 native 路由 `/api/v1/services/audio/tts/SpeechSynthesizer`，不是 `/audio/speech`（本次端点返回 404）。返回音频 URL 下载不附带 API 授权头。

已实测合成成功：`qwen-audio-3.1-tts-next`、`qwen-audio-3.0-tts-plus`、`qwen-audio-3.0-tts-flash`，使用 voice `longanhuan_v3.6`。`qwen-audio-3.1-tts-flash` 本次 HTTP 400、引擎错误 411，不能视为可用；支持情况依赖账号与服务状态。next 在未显式设置 text_prompt 时暂以合成文本填入，其语义仍需按供应商文档核对。

```powershell
.\.venv\Scripts\python.exe src\agent.py --config config.qwen-tts.example.json --tts-model qwen-audio-3.0-tts-flash --check-tts
```

### 确定性 montage

任务配置示例（素材路径相对于任务文件）：

```json
{
  "prompt": "介绍产品，结合现场素材",
  "style": "presentation",
  "materials": [
    "footage.mp4",
    "music.wav"
  ],
  "references": [],
  "config": {
    "montage": {
      "clips": [
        {
          "source": "footage.mp4",
          "start": 0.5,
          "duration": 0.8,
          "source_start": 0
        }
      ],
      "music": {
        "source": "music.wav",
        "volume": 0.15
      }
    }
  }
}
```

`task.config.montage` 是用户确定性配置，不由模型自动挑选素材或剪辑点。clips/music 的 source 必须对应 task.materials 或 references 已归档素材的唯一 name；不要放两个同名文件，也不要使用未归档路径绕过匹配。clip 的 start 是成片覆盖起点，duration 是覆盖时长，source_start 是素材读取起点，单位为秒。片段全画面等比缩放、黑边补齐，覆盖对应生成动画时间段；保留生成旁白和字幕，不混入片段原声。music 循环混入生成音轨，volume 是混音音量系数。未覆盖部分继续使用生成动画。

OpenMontage（AGPLv3）仅提供独立项目、分阶段产物与供应商解耦等架构启发；不复制其源码，不宣称包含完整自动素材搜索、模型选剪辑或全部 OpenMontage 功能。

### 检查与验收

使用当前虚拟环境运行 `scripts/cli_smoke.py`、`scripts/qwen_tts_smoke.py` 和 `scripts/smoke.py`；montage 可用 `scripts/montage_smoke.py` 单独检查。模拟 API 检查不证明真实供应商、ASR、Edge 网络或在线图标服务可用。自动视觉审核发生在 montage 合成之前，只覆盖生成动画的抽样帧，不覆盖剪辑替换画面或新增音乐，不能作为最终 montage 验收。发布前必须人工完整观看、试听 final.mp4，检查覆盖片段衔接、黑边/裁切、音乐循环及音量、旁白与字幕同步，并核对事实和素材许可。
