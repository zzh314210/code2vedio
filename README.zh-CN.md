# Code2Video: 通过代码生成视频

> **Frame 工作台：** 独立运行的视频流水线、素材检索、大纲/分镜人工与 AI 审核、本地 CPU 配音。安装与配置见 [STUDIO.md](STUDIO.md)。仓库不包含本地成片、生产项目、题库、密钥和模型权重。


> **Windows 部署请使用文末的「Code2Video 2026 Windows 流程」**。原研究项目的部署说明仅作历史参考，不适用于当前命令行入口。

<p align="right">
  <a href="./README.md">English</a> | <b>简体中文</b>
</p>

<p align="center">
  <b>Code2Video: 以代码为中心的教学视频生成新范式</b>
</p>
<video src="assets/video.mp4" width="600" controls>
  您的浏览器不支持 video 标签。
</video>

<p align="center">
  <a href="https://scholar.google.com.hk/citations?user=9lIMS-EAAAAJ&hl=zh-CN&oi=sra">Yanzhe Chen*</a>,
  <a href="https://qhlin.me/">Kevin Qinghong Lin*</a>,
  <a href="https://scholar.google.com/citations?user=h1-3lSoAAAAJ&hl=en">Mike Zheng Shou</a> <br>
  新加坡国立大学 Show Lab
</p>

<p align="center">
  <a href="https://arxiv.org/abs/2510.01174">📄 Arxiv 论文</a> &nbsp; | &nbsp;
  <a href="https://huggingface.co/papers/2510.01174">🤗 Daily Paper</a> &nbsp; | &nbsp;
  <a href="https://huggingface.co/datasets/YanzheChen/MMMC">🤗 数据集</a> &nbsp; | &nbsp;
  <a href="https://showlab.github.io/Code2Video/">🌐 项目主页</a> &nbsp; | &nbsp;
  <a href="https://x.com/KevinQHLin/status/1974199353695941114">💬 推特 (X)</a>
</p>



---

## 🔥 更新
- [x] [2025.10.11] 近期收到关于 [ICONFINDER](https://www.iconfinder.com/account/applications) 注册问题的反馈，在 [MMMC](https://huggingface.co/datasets/YanzheChen/MMMC/tree/main/assets) 数据集中更新了 Code2Video 自动收集的 icon，作为临时替代方案。
- [x] [2025.10.6] 在 Huggingface 上更新了 [MMMC](https://huggingface.co/datasets/YanzheChen/MMMC) 数据集。
- [x] [2025.10.3] 感谢 @_akhaliq 在 [推特](https://x.com/_akhaliq/status/1974189217304780863)上分享我们的工作！
- [x] [2025.10.2] 我们发布了 [ArXiv](https://arxiv.org/abs/2510.01174)、[代码](https://github.com/showlab/Code2Video)和[数据集](https://huggingface.co/datasets/YanzheChen/MMMC)。
- [x] [2025.9.22] Code2Video 已被 **NeurIPS 2025 Workshop ([DL4C](https://dl4c.github.io/))** 接收。

---

### 目录
- [🌟 项目总览](#-项目总览)
- [🚀 快速上手](#-快速上手)
  - [1. 环境配置](#1-环境配置)
  - [2. 配置 LLM API 密钥](#2-配置-llm-api-密钥)
  - [3. 运行智能体](#3-运行智能体)
  - [4. 项目结构](#4-项目结构)
- [📊 评测 -- MMMC](#-评测----mmmc)
- [🙏 致谢](#-致谢)
- [📌 引用](#-引用)
- 
---

## 🌟 项目总览

<p align="center">
  <img src="figures/first.png" alt="Overview" width="90%">
</p>

**Code2Video** 是一个**基于智能体、以代码为中心**的框架，能够根据知识点生成高质量的**教学视频**。
与基于像素空间的文生视频模型不同，我们的方法生成可执行的 **Manim 代码**来确保视频的**清晰度、连贯性和可复现性**。

**核心特性**:
- 🎬 **以代码为中心的范式** — 将可执行代码作为统一媒介，同时实现教学视频的时间序列和空间布局组织。
- 🤖 **模块化三智能体设计** — 规划者 (Planner) 负责故事板扩展，编码员 (Coder) 负责可调试代码的合成，鉴赏家 (Critic) 负责通过视觉锚点（Visual Anchor）优化布局，三者协同完成结构化生成。
- 📚 **MMMC 基准** — 用于代码驱动视频生成的基准数据集，涵盖了 117 个受 3Blue1Brown 启发的精选学习主题，横跨多个领域。
- 🧪 **多维度评测** — 从效率、美学和端到端知识传递三个维度进行系统性评估。

---

## 🚀 快速上手

<p align="center">
  <img src="figures/approach.png" alt="Approach" width="85%">
</p>

### 1. 环境配置

```bash
cd src/
pip install -r requirements.txt
```
这里是 Manim Community v0.19.0 的[官方安装指南](https://docs.manim.community/en/stable/installation.html)，以帮助您正确设置环境。

### 2. 配置 LLM API 密钥

请在 `api_config.json` 文件中填入您的 **API key**。

* **LLM API**:
  * 运行 Planner 和 Coder 所需。
  * 使用 **Claude-4-Opus** 可获得最佳的 Manim 代码质量。
  * 使用 **ChatGPT-4.1** 亦具有不错的生成表现。
* **VLM API**:
  * 运行 Critic 所需。
  * 为优化布局和美学，请提供 **Gemini API key**。
  * 使用 **gemini-2.5-pro-preview-05-06** 可获得最佳质量。
* **视觉素材 API**:
  * 为丰富视频内容，请从 [IconFinder](https://www.iconfinder.com/account/applications) 获取并设置 `ICONFINDER_API_KEY`。

### 3. 运行智能体

提供了两种 Shell 脚本，用于不同的生成模式：

#### (a) 单个主题生成

脚本: `run_agent_single.sh`

从脚本中指定的单个**知识点**生成视频。

```bash
sh run_agent_single.sh --knowledge_point "Linear transformations and matrices"
```

**`run_agent_single.sh` 内部重要参数:**

* `API`: 指定使用的 LLM。
* `FOLDER_PREFIX`: 输出文件夹的前缀 (例如, `TEST-single`)。
* `KNOWLEDGE_POINT`: 目标概念，例如 `"Linear transformations and matrices"`。

---

#### (b) 完整基准测试模式

脚本: `run_agent.sh`

运行 `long_video_topics_list.json` 中定义的所有（或部分）学习主题。

```bash
sh run_agent.sh
```

**`run_agent.sh` 内部重要参数:**

* `API`: 指定使用的 LLM。
* `FOLDER_PREFIX`: 输出文件夹的前缀 (例如, `TEST-LIST`)。
* `MAX_CONCEPTS`: 要运行的概念数量 (`-1` 表示全部)。
* `PARALLEL_GROUP_NUM`: 并行运行的组数。

### 4. 项目结构

建议的目录结构如下：
```
src/
│── agent.py
│── run_agent.sh
│── run_agent_single.sh
│── api_config.json
│── ...
│
├── assets/
│   ├── icons/       # 通过 IconFinder API 下载的视觉素材缓存
│   └── reference/   # 参考图像
│
├── json_files/      # 基于 JSON 的主题列表及元数据
├── prompts/         # 用于 LLM 调用的提示模板
├── CASES/           # 生成的案例，按 FOLDER_PREFIX 组织
│   └── TEST-LIST/   # 示例：多主题生成结果
│   └── TEST-single/ # 示例：单主题生成结果
```

---

## 📊 评测 -- MMMC

从以下**三个互补的维度**进行评测：

1. **知识传递 (TeachQuiz)**
   ```bash
   python3 legacy/src/eval_TQ.py
   ```

2. **美学质量 (AES)**
   ```bash
   python3 legacy/src/eval_AES.py
   ```

3. **效率指标 (EFF)**
   * Token 使用量
   * 执行时间

👉 更多数据和评测脚本请见：
[HuggingFace: MMMC 基准](https://huggingface.co/datasets/YanzheChen/MMMC)

---

## 🙏 致谢

* 视频数据来源于 **[3Blue1Brown 官方课程](https://www.3blue1brown.com/#lessons)**。
  这些视频代表了教学视频在清晰度和美学设计上的最高标准，并为我们的评测指标提供了参考。
* 感谢 **Show Lab @ NUS** 所有成员的支持！
* 本项目得益于 **Manim 社区**和 AI 研究生态系统的开源贡献。
* 高质量的视觉素材（图标）由 **[IconFinder](https://www.iconfinder.com/)** 和 **[Icons8](https://icons8.com/icons)** 提供，用于丰富教学视频内容。

---

## 📌 引用

如果我们的工作对您有帮助，欢迎引用我们的工作：

```bibtex
@misc{code2video,
      title={Code2Video: A Code-centric Paradigm for Educational Video Generation},
      author={Yanzhe Chen and Kevin Qinghong Lin and Mike Zheng Shou},
      year={2025},
      eprint={2510.01174},
      archivePrefix={arXiv},
      primaryClass={cs.CV},
      url={[https://arxiv.org/abs/2510.01174](https://arxiv.org/abs/2510.01174)},
}
```

如果您喜欢我们的项目，欢迎在 GitHub 上给我们一个 Star ⭐ 以获取最新动态！
[![Star History Chart](https://api.star-history.com/svg?repos=showlab/Code2Video&type=Date)](https://star-history.com/#showlab/Code2Video&Date)

## 通用 CLI 视频流水线

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
