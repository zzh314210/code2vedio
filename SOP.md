# Code2Video：Windows 启动与教学视频生产 SOP

适用项目：`E:\gptandcc\Code2Video`  
更新日期：2026-10-04  
目标：反复启动本地 Web 面板，配置模型、配音和素材源，使用 Markdown/PDF 教案生成、审核并迭代考公教学视频。

> 日常使用不需要重新安装依赖，不需要 Linux/WSL，不需要激活全局 Python 环境。以下操作均使用项目独立的 `.venv`。本文不包含真实 API Key。

## 1. 日常启动：每次使用先做这几步

### 1.1 打开 PowerShell，进入项目并启动

```powershell
cd E:\gptandcc\Code2Video
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\start_web.ps1
```

浏览器打开：**http://127.0.0.1:8787**。

- 保持这个 PowerShell 窗口运行；它是 Web 服务，不是一次性命令。
- 关闭浏览器不会停止服务。任务生成中不要关闭服务窗口、重启电脑或让电脑睡眠。
- 如果面板已经能打开，直接使用，不必重复启动。
- 面板读取此前保存的配置，并恢复磁盘上的历史任务。已保存的 Key 输入框留空是正常的，不代表密钥丢失。
- 日常启动不运行 `setup_windows.ps1`，不重复安装，不覆盖 `config.local.json` 或 `.env`。

### 1.2 停止和再次启动

待任务完成后，在运行服务的 PowerShell 窗口按 **Ctrl+C**。下次再运行上面的启动命令。

如果之前由后台进程启动，没有可用的服务窗口，应先确认端口所属进程及其命令行再停止，不要批量结束所有 Python 进程。没有把握时保留现有服务，直接打开面板。

### 1.3 端口被占用时

先访问 http://127.0.0.1:8787，确认是否就是已运行的本项目。也可检查监听进程：

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8787 -ErrorAction SilentlyContinue |
    Select-Object LocalAddress,LocalPort,OwningProcess
```

如果确认是其他程序占用，可以换端口启动：

```powershell
.\scripts\start_web.ps1 -Port 8788
```

此时浏览器使用 http://127.0.0.1:8788，不再使用 8787。

## 2. 首次安装／重建环境：已经装好则跳过

前置条件：Windows、Python 3.12 64 位；仅在启用 `graphics-api-remotion` 时还需要 Node.js/npm。

```powershell
cd E:\gptandcc\Code2Video
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup_windows.ps1
```

需要安装 Remotion 图形桥接依赖时：

```powershell
.\scripts\setup_windows.ps1 -WithGraphics
```

脚本会：

1. 在缺失时创建项目 `.venv`，不向全局 Python 安装依赖。
2. 在该虚拟环境内设置并使用清华 PyPI 镜像安装 `src\requirements.txt`。
3. 使用 `https://registry.npmmirror.com` 安装可选的 npm 图形桥接依赖。
4. 仅在本地配置不存在时复制示例配置，不覆盖已有本地配置。
5. 执行离线环境检查，检查 Manim、FFmpeg 和中文字体。

清华镜像不可用时，可改用阿里云 PyPI 镜像：

```powershell
.\scripts\setup_windows.ps1 -Mirror https://mirrors.aliyun.com/pypi/simple/ -WithGraphics
```

只检查当前环境、不重新安装：

```powershell
.\.venv\Scripts\python.exe src\agent.py --doctor
```

项目可使用 `imageio-ffmpeg` 随附的 FFmpeg，因此系统终端找不到 `ffmpeg`／`ffprobe` 不一定代表项目无法合成；以 `--doctor` 结果为准。基础动画使用中文 `Text`，无需额外安装 LaTeX 或 GPU。

国内镜像用于 pip/npm 安装；模型、Edge TTS、图标服务仍需访问其各自的外部地址，不能保证它们都能从国内镜像获取。

## 3. 配置模型：通常第一次配置，之后复用

### 3.1 文本模型

在面板的“模型接入”中填写：

| 字段 | 填写规则 |
| --- | --- |
| 文本协议 | `Responses API` 或 `Chat Completions`；必须是服务实际支持的协议 |
| 模型 ID | 服务商实际支持的模型标识，无固定旧模型列表 |
| 文本 API 地址 | 协议根地址，通常到 `/v1`；不要填完整的 `/responses` 或 `/chat/completions` 请求路径 |
| 文本 API Key | 首次填写；已有配置且不更换时留空 |

此模型用于大纲、分镜、Manim 代码和错误修复。当前曾接入的 `gpt-6.1-sol` 是第三方中转的模型标识，不应据此认定 OpenAI 官方也提供同名模型。

依次点击 **“保存配置” → “测试本地与模型”**。该按钮会检查环境并实际调用文本模型，可能产生费用；它不是完整视频生成测试，也不替代配音／图标检查。

“查询模型列表”只适用于支持 `/models` 的服务。服务不支持列举时，可手动填写可用模型，不要仅因列表查询失败认定模型不可调用。

### 3.2 视觉模型

- 需要自动检查抽样画面时，勾选“启用独立视觉模型自动评审”，选择协议并填写模型、地址和 Key。
- 使用同一多模态服务时，可以配置为继承文本模型；独立服务则设为不继承，并填写完整配置。
- 先跑通时可关闭视觉评审。关闭不影响视频合成，但也意味着没有外部视觉模型审计结果。
- 推荐先少量抽样帧、1 轮评审，确认服务稳定后再增加。
- 自动评审只看抽样帧，不能替代完整动态视频、教材和数学审核。

精确控制继承关系时，在“高级配置”填写：

```json
{
  "vision": {
    "inherit_text": true
  }
}
```

如果要独立视觉服务，改为 `false`，并通过面板填写该服务的协议、地址、模型和 Key。继承开启时，已有非空视觉字段仍可覆盖文本字段；要确保使用同一模型，应核对两组字段，而不是只修改一个开关。

### 3.3 配置保存与保密

- 根目录 `config.local.json` 是模型、TTS、素材和画面等默认配置；也可用 `.env` 引用密钥。
- 创建／重跑课程时，“保存模型、语音、素材等为默认”只更新公共设置，不会把本视频 `course` 要求写回全局。单独点击“保存配置”仍可主动设置默认课程预设。
- 每个视频项目另外保存脱敏 `settings.json`、完整提示词和课程要求副本；已创建项目不会跟随全局提示词变化。模型/API 的默认值改变影响新项目，旧项目续跑保留原服务和模型，用当前匹配服务的凭证恢复密钥。
- 已保存的 Key 不回显到浏览器，留空不会覆盖已有 Key；需要更换时填写新 Key 并保存。
- `.env` 中的 `C2V_TEXT_*`、`C2V_VISION_*`、`C2V_TTS_*` 等环境覆盖项可能影响有效配置；面板修改不生效时应核对这些项。
- 不把含真实密钥的配置、命令历史或截图发到公开渠道，不把 `config.local.json`、`.env` 或私有任务配置提交到 Git。

## 4. TTS 配音：生成有声音的视频

### 4.1 推荐：Edge TTS

在“TTS 配音”设置：

- 提供方：`Edge TTS（免费，无 Key）`。
- 声音：`zh-CN-XiaoxiaoNeural`。
- 语速：先用 `+0%`；本次牛吃草成片使用 `+6%`。
- 无需填写 TTS API 地址、Key 和 OpenAI TTS 模型。

点击 **“测试配音”**，使用面板播放器确认中文声音正常，再保存配置。

Edge TTS 不需要 Key，但需要联网，并不是 Windows 离线系统朗读。服务不可用时，可换到已配置的 OpenAI-compatible TTS 或自定义 HTTP TTS。

### 4.2 其他提供方

| 提供方 | 所需配置 | 注意事项 |
| --- | --- | --- |
| OpenAI / 兼容 TTS | 语音模型 ID、声音、服务地址和 Key | 留空地址／Key可继承文本服务，但中转站不一定提供语音接口，必须实际测试 |
| 自定义 HTTP TTS | 高级配置中的 `tts.url`、headers、payload 和返回音频规则 | 按服务文档配置，不能只填一个 URL 就保证兼容 |
| 静音占位 | 无 | 只适合测试画面，不作为有配音的课程成品 |

本流水线先合成每个 beat 的音频，测量真实时长，再驱动动画和最终合成。Edge 有句级时间戳时使用真实字幕边界；没有时间戳时会回退到按文本长度分配，不能把回退时间当作精确逐词对齐。

## 5. 免费图标源：勾选你需要的风格

先勾选“启用素材增强”，再勾选具体源，最后点击 **“检查已勾选图标源”**。

| 源 | 配置方式 | 使用提示 |
| --- | --- | --- |
| IconVaultKit | MCP 地址及 collection；面板可填写 `lucide`、`mdi` 等图标集 | 优先一个图标集，避免同片混杂风格 |
| Infyicon | MCP 地址及 outline / fill / color-outline / color-fill | 按实际素材许可保留署名 |
| graphics-api-remotion | 本地 npm 桥接，providers 如 `lucide,phosphor` | 先执行 `setup_windows.ps1 -WithGraphics`；包许可不等于全部下游素材许可 |

- “第一个成功源”适合风格一致的课程；“所有已启用源”会增加查询和风格混用，谨慎开启。
- 默认非严格模式下，找不到素材可降级为空素材继续；完成视频不等于所有图标请求都成功。
- 不允许缺图时，可在高级配置设置 `{"assets":{"strict":true}}`，素材失败会阻止继续。
- 每个任务的 `assets.json` 记录素材与错误，`ATTRIBUTION.md` 记录来源和许可提示；发布前检查。
- 不应仅凭“免费”认定所有素材都可无条件商用。

更换源端点时，用高级配置覆盖，例如：

```json
{
  "assets": {
    "sources": {
      "iconvaultkit": {"url": "https://iconvaultkit.com/api/mcp"},
      "infyicon": {"url": "https://infyicon.com/mcp"}
    }
  }
}
```

本次牛吃草 V2 采用已下载的 Noto 彩色 SVG，经 Iconify 公共 API 获取，以保持牛、草、幼苗和太阳的统一风格。它是专项课程脚本预置的素材，不是 Web 面板中的第四个通用勾选源，也不代表以后每个课程自动使用 Noto。

## 6. 视频项目与教材：一个视频一个独立目录

### 6.1 应用目录与视频项目目录要分开

仓库根目录是生产系统，不是某一门课程。`.venv`、`src`、`web`、`scripts` 和默认 API 凭证共用；每个新视频拥有独立的输入、提示词、素材、绘图代码和生产过程，不必复制一套虚拟环境。

新 Web 任务与未指定目录的新 CLI 任务，会创建：

```text
E:\gptandcc\Code2Video\projects\
└── 20261004-行测数量关系：牛吃草问题--任务ID\
    ├── README.md                  本视频项目说明
    ├── project.json               标题、ID、创建时间、父版本
    ├── job.json                   Web 任务状态；CLI 不一定有
    ├── settings.json              本项目配置快照，真实密钥已脱敏
    ├── prompts\
    │   ├── policy.txt             本项目公共教学规则
    │   ├── outline.txt            完整大纲模板
    │   ├── storyboard.txt         完整分镜／旁白模板
    │   ├── code.txt               完整 Manim 生成／修复模板
    │   ├── review.txt             完整视觉审核模板
    │   └── requirements.json      本项目全局要求和各阶段补充
    ├── materials\                 实际使用的原始 Markdown/PDF 副本
    ├── examples\                  本视频例题、示例和设计参考
    ├── code\
    │   ├── runtime\               本项目实际使用的绘图运行代码副本
    │   ├── svg\                   提供的 SVG 绘制源码；不会自动执行
    │   └── manim\                 生成的章节 Python 源码及修订版
    └── output\
        ├── materials.json         教材选段与来源
        ├── outline.json           大纲
        ├── storyboard.json        旁白、字幕、动画步骤
        ├── requests\              实际模型提示词及协议/模型/帧路径记录
        ├── audio\                 配音、时长和字幕时间戳
        ├── assets\                本项目 SVG 本体；local 子目录是上传素材
        ├── section_*\             Manim 源码、各轮渲染、媒体缓存和日志
        ├── events.jsonl           阶段事件记录
        ├── ATTRIBUTION.md          素材出处和许可提示
        ├── final.mp4               最终视频
        └── subtitles.srt          字幕文件
```

目录名中的 Windows 非法字符会自动替换，因此实际标题中的冒号通常变成下划线；以页面显示的项目目录为准。每次修改生成新版本，也创建新目录，用 `project.json` 的 `parent` 关联原版本，不覆盖旧成品。

- 页面任务卡直接显示项目路径，点击“项目全部文件”浏览输入、提示词、素材、绘图源码与成品；点击“载入项目配置”查看该视频自己的设置。
- 根目录 `examples` 只是共享示例模板库。作为教材传入的示例会复制到项目 `materials`，作为参考资源传入的示例会复制到项目 `examples`，运行不依赖原教材文件一直存在。
- 需要 AI 阅读的例题和教材放在上传教材入口或 `--material`；资源栏中的 `.md/.json` 只做归档，不会自动加入模型上下文。
- SVG 本体保存在本项目；提供的 `.py` 绘制源码保存在 `code/svg`，生成的 Manim 源码和实际绘图运行代码分别保存在 `code/manim`、`code/runtime`。上传的 SVG 会安全清理；上传 Python 仅归档，不会自动运行。
- 下载图标保留 SVG 标记、来源与许可提示，但第三方图标未必提供生成程序，不能声称每个下载图标都有 Python 绘制源码。
- 新项目默认模板是初始副本；其他视频的模板或教材不会因同名而覆盖本项目。提示词、教材、示例或绘图运行源码改变后，不允许直接复用旧缓存，应新建版本。
- 旧测试用的 `workspace\`、`outputs\` 内容已清理；以后若存在正式旧项目，应保留其独立项目目录，不把成片搬回根目录。
- 旧 CLI 若尚无教材副本，第一次续跑仍需传入原 `--material` 和 PDF 页码；新项目保存教材顺序与页码，可直接从项目内部续跑。
- `projects/` 已加入 Git 忽略规则。API Key 留在根目录 `.env/config.local.json`，项目配置快照不复制真实 Key；项目教案和实际提示词仍可能是私有资料，不应直接公开整个目录。

### 6.2 准备本视频教材

支持 `.md`、`.markdown` 和**文本型 PDF**，可以上传多个文件。建议先整理相关教案，而不是上传整本教材让模型自行猜测。

Markdown 建议保存为 UTF-8，并采用以下结构：

```markdown
# 知识点：牛吃草问题

## 教学目标
理解原有库存、每天生长和净消耗之间的关系。

## 条件与假设
草匀速生长；每头牛每天吃一份；两个方案从相同初始库存开始。

## 原理
Q + GT = NT，所以 Q = (N - G)T。

## 唯一例题
10头牛吃22天，16头牛吃10天，问25头牛吃多久。

## 标准答案与推导
G=5份/天，Q=110份，净消耗20份/天，T=5.5天。

## 易错点
不是先吃22天再换牛；5头抵消生长只是等效分组。

## 来源与发布要求
注明参考教材、题目是自编还是实际试题，以及必须保留的出处。
```

PDF 注意：

- 扫描图片型 PDF 尚未内置 OCR，需先转为可复制文字的 PDF 或 Markdown。
- 加密 PDF 需先解密；无文字可提取的页会报错。
- “高级配置”里的 PDF 页码支持 `2-5,8`，从 1 开始；统一应用于这次上传的所有 PDF。
- 默认单文件限制 50MB、教材上下文预算 24000 字符；超出上下文预算会按知识点相关度选择片段，而不是保证整本教材逐页使用。
- 使用法律、政策、时政材料时，应提供经过确认的有效版本并人工核验，不要求模型凭记忆补全。

模型会收到选中的教材内容；启用视觉评审会发送视频帧，外部 TTS 会收到旁白。不要上传不允许外传的教材或个人信息。

## 7. 设置课程风格、浅色画面和横竖屏

### 7.1 全部提示词入口

日常不必改 Python。每个视频的输入分为“讲什么”的教材和“怎么讲”的创作要求：

| 输入 | Web 位置 | CLI／配置字段 | 项目内位置 |
| --- | --- | --- | --- |
| 知识点 | 创建课程 → 知识点标题 | `--topic` | `project.json` 的 `topic` |
| 教材、例题、答案 | Markdown/PDF 教案 | `--material`，可重复 | `materials/` |
| 全局创作要求 | 全局课程风格 | `course.instructions` | `prompts/requirements.json` 的 `instructions` |
| 大纲补充 | 大纲阶段补充 | `course.prompts.outline` | 同文件 `prompts.outline` |
| 分镜／旁白补充 | 分镜阶段补充 | `course.prompts.storyboard` | 同文件 `prompts.storyboard` |
| 代码／调试补充 | 代码阶段补充 | `course.prompts.code` | 同文件 `prompts.code` |
| 审核补充 | 视觉评审阶段补充 | `course.prompts.review` | 同文件 `prompts.review` |
| 完整阶段模板 | 可选：本视频完整提示词模板 | `--prompts-dir` | `prompts/*.txt` |
| 参考示例／SVG／绘制源码 | 本视频 SVG、绘图源码、示例参考 | `--resource`／`--example`，可重复 | `examples/`、`output/assets/local/`、`code/svg/` |

全局创作要求会追加到四个阶段；没有单独的调试字段，调试复用代码模板和 `course.prompts.code`，再加入原代码与错误／审核意见。视觉补充仅在启用评审时使用。

教材是事实依据，不是指令。风格、时长和构图要求写到课程要求中，不要只塞进教材。TTS 不另行生成讲稿：朗读分镜 `sections[].beats[].narration`，画面字幕使用 `caption`；要改口播，编辑分镜并生成新版本。

CLI 推荐使用本视频独立的课程输入文件，而不是反复改根目录 `config.local.json`。示例项目包中的 `examples/video_project/cow_grass/course.json` 和 `examples/video_project/civil_service/course.json` 都采用以下结构：

```json
{
  "course": {
    "instructions": "面向行测初学者，约2分钟，先直觉后公式，讲清原理和一道例题。",
    "prompts": {
      "outline": "只讲一个核心方法，突出适用条件与易错点。",
      "storyboard": "旁白口语化，每句对应一个可视化步骤，公式适合朗读。",
      "code": "浅色背景、深色文字，优先图形推导，有授权素材时使用 self.asset。",
      "review": "检查数字、公式、中文、对比度和推理步骤是否一致。"
    }
  },
  "video": {"theme": "light", "orientation": "landscape"}
}
```

通过 `--course-file` 传入上述 JSON；也支持仅含 `instructions/prompts` 的 JSON 对象。这个文件会落实为本项目要求和设置快照，不会改写其他项目。Web 创建时则直接使用本次页面输入。

### 7.2 修改本项目完整模板

每个项目都有 `policy.txt`、`outline.txt`、`storyboard.txt`、`code.txt`、`review.txt`，不是只记录几句补充。可在任务卡点“编辑项目提示词/大纲/分镜/代码”，选择 `prompts/` 下的文件，保存为独立新版本。

新任务也可直接上传上述命名的 `.txt` 文件；未上传的模板使用默认副本。CLI 用 `--prompts-dir "你的模板目录"`，该目录需包含全部五个文件。

| 模板 | 可用占位符 |
| --- | --- |
| 各阶段通用 | `{{policy}}`，在使用该占位符的位置插入公共规则 |
| 大纲 | `{{topic}}`、`{{max_sections}}`、`{{material_context}}` |
| 分镜 | `{{outline_json}}`、`{{max_beats}}`、`{{material_context}}` |
| 代码 | `{{section_json}}`、`{{previous_json}}`、`{{feedback}}`、`{{layout_bounds}}`、`{{background}}`、`{{primary}}`、`{{emphasis}}`、`{{secondary}}`、`{{foreground}}` |
| 审核 | `{{section_json}}` |

不要随意删除输出 JSON 结构或阶段标识；陌生占位符会报错，输出仍受结构与 AST 安全检查。`output/requests` 保存实际使用的完整提示词，含教材选段、修复反馈和结构化重试要求，方便复盘，而不是只保存原始模板。

默认模板源在 `src/lesson_prompts.py`，追加补充的逻辑在 `src/pipeline.py`。修改默认源码只影响之后创建的项目；已有项目使用自己的副本。改源码后重启 Web；修改项目输入应保存成新版本，不在运行中切换。

### 7.3 画面设置不是提示词开关

“课程创作要求”中可填写全局风格和大纲、分镜、代码、评审阶段补充。推荐全局要求：

```text
面向考公行测初学者，目标约2分钟，只聚焦一个知识点和一道例题。
先用直觉可视化解释原理，再逐步引入公式，最后验证并总结三步法。
使用自然中文短句旁白，字幕简短；不要整屏堆叠教案或一次显示所有公式。
使用浅暖白背景、深灰或深绿色文字、柔和青绿和橙色强调，保证对比度。
图标风格统一，优先使用授权素材；避免粗糙的代用图形。
横屏按16:9构图，标题、主体与字幕保持安全区，不重叠、不越界。
所有数据、公式和答案以教材为准，不伪称自编例题是历年真题。
```

在“高级配置”的 JSON 中设置实际画面样式。例如横屏正式版：

```json
{
  "video": {
    "theme": "light",
    "orientation": "landscape",
    "brand": "行测可视化 · 数量关系",
    "quality": "high",
    "fps": 30,
    "max_sections": 3,
    "max_beats": 4,
    "render_timeout": 900
  }
}
```

竖屏改为 `"orientation":"portrait"`，并把创作要求中的构图改成竖屏 9:16、纵向排布，重新创建版本。`theme` 控制视频模板背景，不改变 Web 面板自身的配色；生成代码还需遵循创作要求来使用合适的文字／图形颜色。

重要规则：

- 高级 JSON 的同名字段优先于面板普通输入。例如上面写了 `quality=high`，仅把普通质量下拉改成“低”不会生效，需要同时修改或移除高级 JSON 中的质量字段。
- 高级 JSON 可同时包含 `course`、`video`、`vision`、`assets`、`tts`；合并为一个 JSON 对象，不能直接粘贴两个并列的 JSON 对象。
- 修改后点击“保存配置”；样式、质量或配音改变时用新任务／新版本，不能仅续跑旧缓存。
- 横屏高质量为 1920×1080；竖屏高质量为 1080×1920。竖屏低／中质量当前使用 540×960，适合预览。
- “约2分钟”是创作目标，不是硬性的精确120秒限制，最终时长以真实音频和合成结果为准。

## 8. 推荐生产流程：先审教案，再生成成片

### 8.1 创建课程，先停在分镜

制作新知识点先点“新视频 · 清空课程输入”，避免沿用上一视频的题目、上传文件、PDF 页码或阶段补充。模型、语音和素材默认设置可复用。之后的每次创建仍会生成新的项目目录。

1. 确认模型连通、TTS试听正常；需要素材时检查已勾选源。
2. 填写“知识点”，例如“行测数量关系：牛吃草问题”。
3. 上传相关 Markdown／PDF 教案，必要时设置 PDF 页码。
4. 填写创作要求与高级样式配置；先使用低质量预览，定稿后再生成高质量版本。
5. 在“停止阶段”选择“分镜”或“大纲”。
6. 点击“创建课程”；此时不需要允许执行生成代码。
7. 在任务卡片中点击“编辑大纲/分镜/代码”，检查大纲与分镜。

重点检查：是否讲清原理、只用一道例题、是否过长、题目数据与答案是否一致、有没有模型添加的未经教材支持的结论。

### 8.2 修改大纲／分镜

在编辑器中选择对应 JSON，修改内容后点击 **“保存为新版本并运行”**。

- 保留 JSON 结构与必需字段，保持合法 JSON，不添加说明文字或 Markdown 代码围栏。
- 修改已有章节／beat 的文字最稳妥；不随意改 ID 或删掉必要字段。
- 编辑操作创建新任务和新版本，不覆盖旧成品；被编辑阶段之后的相关产物会重新生成。
- 提交前确认主页面的“停止阶段”和代码执行勾选，它们也决定新版本运行到哪里。

### 8.3 先试听，再渲染

如果想检查旁白，可将停止阶段设为“TTS”，在对应任务上点击 **“继续/从缓存运行”**。任务产物中的 `audio` 文件夹包含各段 WAV。

教案／分镜确认后：

1. 把“停止阶段”改为“合成”。
2. 勾选允许执行模型生成代码的确认项。
3. 点击目标任务的“继续/从缓存运行”。
4. 等待渲染、可选视觉评审和合成完成。

模型生成的 Python 在本机执行。项目有 AST 检查，但它不是系统沙箱；正式生产建议使用无敏感文件的隔离账户，不在高权限账户下执行未审核代码。

### 8.4 直接生成：教案可靠时可用

上传教案、设置风格，停止阶段直接选“合成”，勾选代码执行确认，然后“创建课程”。这会连贯运行全链路，但仍需最后人工验收。

## 9. 看懂任务导览：每一阶段做什么

| 阶段 | 输入／工作 | 主要产物 |
| --- | --- | --- |
| 大纲 `outline` | 结合知识点和教材规划课程 | `outline.json`、`materials.json` |
| 分镜 `storyboard` | 拆分旁白、字幕说明与动画意图 | `storyboard.json` |
| TTS `audio` | 合成各段配音、测量真实时长 | `audio/`、`timing.json` |
| 素材 `assets` | 查询已启用源、缓存和记录出处 | `assets/`、`assets.json`、`ATTRIBUTION.md` |
| 代码 `code` | 依据分镜和配音时长生成 Manim 片段 | `section_*_code.json` |
| 渲染 `render` | 本地渲染，失败时调用模型修复 | 各章节 `scene.py`、MP4、日志 |
| 评审 `review` | 启用时抽帧交给视觉模型并按反馈修改 | 评审 JSON；禁用时标记为 skipped |
| 合成 `compose` | 合并章节、配音和字幕 | `final.mp4`、`subtitles.srt`、`timeline.json` |

面板的阶段栏和事件记录显示任务运行到哪里、错误和最新状态。任务显示 `complete` 也可能只是“停在大纲／分镜的阶段完成”；只有 **合成完成且出现“下载最终 MP4”** 才是成片完成。

## 10. 找到成品、试听并验收

### 10.1 成品位置

- 新 Web／默认 CLI 生成：`projects\日期-知识点--ID\output\final.mp4`。
- CLI 指定 `--project "projects\牛吃草-v001"`：`projects\牛吃草-v001\output\final.mp4`。
- `--output` 作为项目目录兼容参数，新项目也使用其 `output` 子目录；旧 CLI 原目录续跑会识别原有顶层 `manifest.json`，保持旧成片路径。
- 旧测试用的 `workspace\` 和 `outputs\` 已清理；正式项目的成片统一以对应 `projects\...\output\final.mp4` 为准。
- 面板成品任务卡片可直接播放，并点击“下载最终 MP4”。
- 字幕：同目录 `subtitles.srt`；素材出处：同目录 `ATTRIBUTION.md`。
- 任务ID记录在面板卡片中，定位时不要把其他任务或预览版当成新成片。

### 10.2 牛吃草项目包

牛吃草不再依赖根目录的固定任务或成片路径。使用 `examples\video_project\cow_grass` 创建新项目；成片写入该项目的 `output`，验收记录模板见 `examples\cow_grass_v2_acceptance.md`。本课未启用外部视觉模型审计时，应明确记录人工检查结果，不应误称自动视觉审计通过。

### 10.3 发布前检查清单

- [ ] 题目、条件、公式、答案与教材一致；没有错误的比例图或单位。
- [ ] 前几秒明确知识点与悬念，原理解释在答案之前。
- [ ] 完整播放检查中文配音，不只是检查“有音频轨”；没有静音、截断或难懂的读法。
- [ ] 字幕与旁白基本同步，句子可读，没有文字重叠或超出安全区。
- [ ] 动画变化与旁白一致，竖屏没有沿用横屏布局导致越界。
- [ ] `assets.json` 的缺失／错误已查看，素材出处和许可要求已处理。
- [ ] 记录哪些审核是模型自动执行、哪些是人工完成；没有把 skipped 当作通过。
- [ ] 时长符合目标，正式版本使用预期分辨率，并保留前一版。

## 11. 反复修改：三个按钮的区别

| 操作 | 适用情况 | 会发生什么 |
| --- | --- | --- |
| 继续/从缓存运行 | 同任务网络中断、阶段暂停、失败后恢复 | 使用保存的任务配置与已有产物继续；不等于应用页面所有新设置 |
| 修改配置后重跑 | 更换模型、语音、风格、质量、构图或提示词 | 按页面设置创建新任务；旧任务保留 |
| 编辑大纲/分镜/代码 | 要精确修改某一段内容或画面 | 带编辑后的产物创建新版本，并重新执行相应后续阶段 |

实践规则：

- 只是中断恢复：保持教材和配置不变，点击“继续”。
- 新知识点／新教材：创建课程并重新上传；“修改配置后重跑”会复用原任务教材，不是重新上传入口。
- 调整配音、内容、画面、清晰度：创建新版本，不直接复用旧渲染缓存。
- 修改项目包中的 `code\runtime\extensions\cow_grass.py` 或 `extensions.json` 后，也应生成新项目版本。旧项目续跑可能跳过已有章节，不会自动把新扩展当作旧缓存的一部分。
- 不手动覆盖 `final.mp4` 或删除任务缓存来碰运气；保留可追溯版本。
- 有任务正在运行时，不要重复点击创建、重跑；它们可能产生多个收费任务。

## 12. 牛吃草精修模板复跑：区别于通用 AI 生成

`examples\create_cow_grass_v2.py` 是这节课的专项制作脚本：固定的12个精修动画镜头和旁白，直接使用项目内扩展生成横／竖屏新版本，不依赖 Web 服务，不是其他知识点的通用模板。

前置条件：已安装项目虚拟环境；专项脚本会使用牛吃草项目包，并把运行时扩展和资源归档到新项目。旧 `workspace\` 测试任务不再是前置条件。

```powershell
cd E:\gptandcc\Code2Video
.\.venv\Scripts\python.exe examples\create_cow_grass_v2.py --quality high --allow-generated-code
```

竖屏新版本：

```powershell
.\.venv\Scripts\python.exe examples\create_cow_grass_v2.py --orientation portrait --quality high --allow-generated-code
```

每次不指定 `--project` 时创建独立新项目，控制台输出 `PROJECT` 和 `AUDIO_SECONDS`，成片位于该项目的 `output\final.mp4`。中断恢复使用 `--project "项目目录" --resume --allow-generated-code`，无需启动 Web 或修改端口。

制作其他知识点用第8节的上传教案／创建课程流程，不要只改此脚本的课程标题。

## 13. 命令行备选流程

不使用 Web 时，可直接运行共用虚拟环境，输入与输出仍属于本视频独立项目。需要与浏览器任务相同的“分阶段检查 → 渲染”原则。

先生成大纲和分镜：

```powershell
cd E:\gptandcc\Code2Video
.\.venv\Scripts\python.exe src\agent.py --config config.local.json `
  --project "projects\牛吃草-v001" `
  --topic "行测数量关系：牛吃草问题" `
  --project-pack "examples\video_project\cow_grass" `
  --material "examples\牛吃草教案.md" `
  --plan-only
```

检查该项目 `output` 子目录中的 `outline.json`、`storyboard.json` 后，以**相同知识点和项目目录**继续。程序恢复该项目配置快照，并读取项目内教材副本，不必依赖原教材路径：

```powershell
.\.venv\Scripts\python.exe src\agent.py --config config.local.json `
  --project "projects\牛吃草-v001" `
  --topic "行测数量关系：牛吃草问题" `
  --resume --allow-generated-code
```

PDF 用 `--material "你的路径\教案.pdf" --pdf-pages "2-5,8"`；多个教材可重复添加 `--material`。

项目配置 `video.narration_max_chars`、`video.caption_max_chars` 控制分镜字符上限（默认 140/42），实际上限同时注入分镜提示词；`video.subtitle_language` 控制成片字幕轨语言标记（默认 `zho`）。`course.language` 会注入四个阶段的提示词（默认“中文”），不会自动替换 TTS 语音或字体。

可选输入：`--prompts-dir "本课程完整模板目录"`、`--resource "本课程\草.svg"`、`--resource "本课程\draw_grass.py"`、`--example "本课程\例题参考.md"`；资源参数可重复。SVG 可用于启用素材后的代码生成，Python 仅归档，参考文档若要模型阅读仍需使用 `--material`。

不指定 `--project` 时自动创建日期、知识点与随机 ID 命名的项目。续跑必须明确指定 `--project` 或 `--output`；不能只传 `--resume`，否则无法知道要续跑哪一门课程。

不要在两次命令之间改变项目提示词、示例、绘图代码、质量、TTS或教材。需要修改时创建新的 `projects\牛吃草-v002`，或在 Web 使用“保存为新版本”。根目录 API 默认值改变不会把已有项目的模型悄悄替换；若原服务地址与当前凭证不一致会拒绝恢复，需提供匹配凭证或创建新版本。

## 14. 常见故障处理

| 现象 | 处理顺序 |
| --- | --- |
| `.venv\Scripts\python.exe` 不存在 | 执行第2节安装脚本；不要改用系统Python混装 |
| PowerShell禁止脚本 | 先运行 `Set-ExecutionPolicy -Scope Process Bypass`，只改变当前会话 |
| 面板打不开 | 看服务窗口报错，确认端口、访问地址和服务是否仍运行 |
| 协议／模型报错 | 核对地址到协议根、模型ID、Key和该服务是否支持Responses；只在确实支持时切换Chat Completions |
| 模型调用慢或超时 | 查看任务错误和当前阶段，减少课程规模／评审帧数；改配置后创建新版本，恢复原配置任务则使用“继续” |
| Edge TTS失败 | 先“测试配音”、确认网络；服务持续不可用时换可用TTS并创建新版本 |
| 图标检查失败 | 分别检查勾选源，npm源确认安装；非严格模式可先关闭素材跑通，素材错误见 `assets.json` |
| PDF没有可提取文字 | 先OCR并转为文本PDF或Markdown，再重新上传 |
| 中文字体缺失／方框 | 运行 `--doctor`，选择系统实际安装的中文字体，再创建新版本 |
| Manim渲染失败 | 查看阶段错误及章节日志，确认自动修复次数；必要时通过编辑器调整代码后新建版本 |
| 修改样式后视频没变 | 确认高级JSON是否覆盖普通输入，并使用新版本；“继续”可能复用旧代码与MP4 |
| 视觉评审失败 | 判断服务是否支持图像输入，减少帧数；可在新版本关闭评审并人工检查，不能标为审计通过 |
| 任务显示complete但没有成品 | 检查是否仅停在大纲／分镜等前置阶段，将停止阶段改为合成并确认代码执行后继续 |
| 刷新后Key输入框空白 | 密钥不回显是设计行为；先测试，不要立即覆盖成空值 |

维护／升级后需做回归时，可执行：

```powershell
.\.venv\Scripts\python.exe scripts\smoke.py
```

默认 smoke 使用本地模拟接口检查流水线及 Web 安全／版本操作；不代表真实外部服务、所有免费图标源和所有题型都已可用。真实服务仍通过面板的模型、配音、图标检查分别测试。

## 15. 必须保留的文件与日常顺序

保留：`.venv`、`config.local.json`、`.env`、`projects`、历史 `workspace/outputs`、`examples` 和项目源码。每个 `projects` 子目录包含课程输入和版本资产，不能只留 MP4 后删除教材、提示词与绘图代码。虚拟环境可重建，课程项目应整体备份。

日常顺序：**启动 → 打开面板 → 核对配置 → 上传教案 → 先审大纲/分镜 → 试听配音 → 允许渲染 → 等待合成 → 完整验收 → 导出 → 修改时生成新版本。**
