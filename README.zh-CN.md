# Code2Video: 通过代码生成视频

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
   python3 eval_TQ.py
   ```

2. **美学质量 (AES)**
   ```bash
   python3 eval_AES.py
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

## Code2Video 2026 Windows 流程

本仓库当前推荐使用 Windows 原生流程：独立 `.venv`、清华 PyPI 镜像、Manim + FFmpeg 本地渲染，以及本地 Web 面板管理课程。

### 快速开始

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup_windows.ps1
.\scripts\start_web.ps1
```

浏览器打开 `http://127.0.0.1:8787`，在面板中配置文本模型、独立视觉审计模型、TTS、图标源，上传 Markdown/PDF 教材后创建课程。命令行方式：

```powershell
.\.venv\Scripts\python.exe src\agent.py --config config.local.json `
  --topic "资料分析：增长率" --material examples\增长率.md `
  --allow-generated-code --feedback
```

模型名完全可配置：将示例配置中的 `YOUR_MODEL_ID` 改为服务商实际支持的 ID，不使用旧版硬编码列表。本机接入的是第三方服务提供的 `gpt-6.1-sol`，不代表 OpenAI 官方接口提供同名模型。模型网关支持 OpenAI Responses 与 OpenAI-compatible Chat Completions，`base_url` 填协议根地址（通常到 `/v1`）。

设置 `vision.inherit_text: true` 时，视觉评审使用与文本模型相同的地址、密钥、模型和协议。仅更改视觉配置后可用 `--resume` 保留大纲、分镜、配音和渲染，只重新评审和合成；知识点、教材及其他配置变化仍需新输出目录。

### 外部服务

- 文本/规划/分镜/Manim/调试：一个可用的 OpenAI 或兼容 API。
- 视觉审计：可单独配置一个多模态 OpenAI/兼容 API；不启用也能生成画面。
- TTS：Edge TTS 无 API Key 但需要联网；也支持 OpenAI 兼容语音和自定义 HTTP TTS。
- 图标：IconVaultKit、Infyicon、`graphics-api-remotion` 可在 `config.local.json` 中分别启用；每个源风格不同，素材记录会保存来源和许可提示。
- Manim 和 FFmpeg 在本机运行，不需要视频生成 API。

### 安全与限制

不要把 API Key 写入仓库或命令历史；使用 `.env` 环境变量引用。模型生成的 Python 代码必须在隔离账户或明确允许后执行，`--allow-generated-code` 不是沙箱。PDF 支持文本型 PDF，扫描件/OCR 暂未内置。教材文本、视觉审计帧和 TTS 文本会发送到你配置的外部服务。

同一课程可以从 Web 面板继续、重跑或编辑大纲/分镜/代码生成新版本；流水线阶段为：大纲 → 分镜 → TTS → 素材 → Manim 代码 → 渲染 → 视觉审计 → 合成。

`src/run_agent.sh` 与 `src/run_agent_single.sh` 仅保留为旧环境兼容包装器；Windows 请使用 `scripts\run_windows.ps1` 或 Web 面板。
