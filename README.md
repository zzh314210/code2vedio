
# Code2Video: Video Generation via Code

> **Frame Studio:** standalone web pipeline, source research, editable outline/storyboard reviews and CPU speech integration. See [STUDIO.md](STUDIO.md) for installation and configuration. This source checkout excludes generated videos, production projects, datasets, credentials and model weights.


> **Current CLI:** use the [current workflow](#current-cli-workflow) below. Original research/demo instructions are retained as historical reference and do not describe the current application.

<p align="right">
  <b>English</b> | <a href="./README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <b>Code2Video: A Code-centric Paradigm for Educational Video Generation</b>
<br>
以代码为中心的教学视频生成新范式
</p>
<video src="assets/video.mp4" width="600" controls>
  Your browser does not support the video tag.
</video>






<p align="center">
  <a href="https://scholar.google.com.hk/citations?user=9lIMS-EAAAAJ&hl=zh-CN&oi=sra">Yanzhe Chen*</a>,
  <a href="https://qhlin.me/">Kevin Qinghong Lin*</a>,
  <a href="https://scholar.google.com/citations?user=h1-3lSoAAAAJ&hl=en">Mike Zheng Shou</a> <br>
  Show Lab @ National University of Singapore
</p>


<p align="center">
  <a href="https://arxiv.org/abs/2510.01174">📄 Paper</a> &nbsp; | &nbsp;
  <a href="https://huggingface.co/papers/2510.01174">🤗 Daily Paper</a> &nbsp; | &nbsp;
  <a href="https://huggingface.co/datasets/YanzheChen/MMMC">🤗 Dataset</a> &nbsp; | &nbsp;
  <a href="https://showlab.github.io/Code2Video/">🌐 Project Website</a> &nbsp; | &nbsp;
  <a href="https://x.com/KevinQHLin/status/1974199353695941114">💬 X (Twitter)</a>
</p>

https://github.com/user-attachments/assets/d906423f-734a-41c9-b102-b113ad3b3c25



<!-- <p align="center">
<table>
  <thead>
    <tr>
      <th style="text-align: center;">Learning Topic</th>
      <th style="text-align: center;">Veo3</th>
      <th style="text-align: center;">Wan2.2</th>
      <th style="text-align: center;">Code2Video (Ours)</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td style="text-align: center; vertical-align: middle;"><strong>Hanoi Problem</strong></td>
      <td style="text-align: center;">
        <img src="assets/videos/veo/Hanoi.gif">
      </td>
      <td style="text-align: center;">
        <img src="assets/videos/wan/Hanoi.gif">
      </td>
      <td style="text-align: center;">
        <img src="assets/videos/code2video/Hanoi_4K_SpeedUp.gif">
      </td>
    </tr>
    <tr>
      <td style="text-align: center; vertical-align: middle;"><strong>Large Language Model</strong></td>
      <td style="text-align: center;">
        <img src="assets/videos/veo/LLM.gif">
      </td>
      <td style="text-align: center;">
        <img src="assets/videos/wan/LLM.gif">
      </td>
      <td style="text-align: center;">
        <img src="assets/videos/code2video/LLM_speed.gif">
      </td>
    </tr>
    <tr>
      <td style="text-align: center; vertical-align: middle;"><strong>Pure Fourier Series</strong></td>
      <td style="text-align: center;">
        <img src="assets/videos/veo/fourier.gif">
      </td>
      <td style="text-align: center;">
        <img src="assets/videos/wan/fourier.gif">
      </td>
      <td style="text-align: center;">
        <img src="assets/videos/code2video/fourier_speed.gif">
      </td>
    </tr>
    </tbody>
</table>
</p> -->

<p align="center">
<table style="width: 90%; border-collapse: collapse; text-align: center; margin: auto;">
  <thead>
    <tr>
      <th style="text-align: center; padding: 8px;">Learning Topic</th>
      <th style="text-align: center; padding: 8px;">Veo3</th>
      <th style="text-align: center; padding: 8px;">Wan2.2</th>
      <th style="text-align: center; padding: 8px;">Code2Video (Ours)</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td style="text-align: center; vertical-align: middle; font-weight: bold;">Hanoi Problem</td>
      <td>
        <div style="width: 320px; aspect-ratio: 16 / 9; overflow: hidden; margin: auto;">
          <img src="assets/videos/veo/Hanoi.gif" style="width: 100%; height: 100%; object-fit: cover;">
        </div>
      </td>
      <td>
        <div style="width: 320px; aspect-ratio: 16 / 9; overflow: hidden; margin: auto;">
          <img src="assets/videos/wan/Hanoi.gif" style="width: 100%; height: 100%; object-fit: cover;">
        </div>
      </td>
      <td>
        <div style="width: 320px; aspect-ratio: 16 / 9; overflow: hidden; margin: auto;">
          <img src="assets/videos/code2video/Hanoi_4K_SpeedUp.gif" style="width: 100%; height: 100%; object-fit: cover;">
        </div>
      </td>
    </tr>
    <tr>
      <td style="text-align: center; vertical-align: middle; font-weight: bold;">Large Language Model</td>
      <td>
        <div style="width: 320px; aspect-ratio: 16 / 9; overflow: hidden; margin: auto;">
          <img src="assets/videos/veo/LLM.gif" style="width: 100%; height: 100%; object-fit: cover;">
        </div>
      </td>
      <td>
        <div style="width: 320px; aspect-ratio: 16 / 9; overflow: hidden; margin: auto;">
          <img src="assets/videos/wan/LLM.gif" style="width: 100%; height: 100%; object-fit: cover;">
        </div>
      </td>
      <td>
        <div style="width: 320px; aspect-ratio: 16 / 9; overflow: hidden; margin: auto;">
          <img src="assets/videos/code2video/LLM_speed.gif" style="width: 100%; height: 100%; object-fit: cover;">
        </div>
      </td>
    </tr>
    <tr>
      <td style="text-align: center; vertical-align: middle; font-weight: bold;">Pure Fourier Series</td>
      <td>
        <div style="width: 320px; aspect-ratio: 16 / 9; overflow: hidden; margin: auto;">
          <img src="assets/videos/veo/fourier.gif" style="width: 100%; height: 100%; object-fit: cover;">
        </div>
      </td>
      <td>
        <div style="width: 320px; aspect-ratio: 16 / 9; overflow: hidden; margin: auto;">
          <img src="assets/videos/wan/fourier.gif" style="width: 100%; height: 100%; object-fit: cover;">
        </div>
      </td>
      <td>
        <div style="width: 320px; aspect-ratio: 16 / 9; overflow: hidden; margin: auto;">
          <img src="assets/videos/code2video/fourier_speed.gif" style="width: 100%; height: 100%; object-fit: cover;">
        </div>
      </td>
    </tr>
  </tbody>
</table>
</p>

---

## 🔥 Update
**Any contributions are welcome!**

- [x] `2026.08.23` Code2Video has reached 2000 stars!
- [x] `2026.05.01` Code2Video has been accepted to [ICML 2026](https://icml.cc/)!
- [x] `2025.11.06` We optimized `requirements.txt`, which resulted in an 80-90% reduction in installation time. Thanks to [daxiongshu](https://github.com/daxiongshu)!
- [x] `2025.10.11` Due to issues on [ICONFINDER](https://www.iconfinder.com/account/applications), we’ve updated Code2Video auto-collected icons at [MMMC](https://huggingface.co/datasets/YanzheChen/MMMC/tree/main/assets) as a temporary alternative.
- [x] `2025.10.06` We have updated the ground truth human-made videos and metadata for the [MMMC](https://huggingface.co/datasets/YanzheChen/MMMC) dataset.
- [x] `2025.10.03` Thanks @_akhaliq for sharing our work on [Twitter](https://x.com/_akhaliq/status/1974189217304780863)!
- [x] `2025.10.02` We release the [arXiv](https://arxiv.org/abs/2510.01174), [code](https://github.com/showlab/Code2Video) and [dataset](https://huggingface.co/datasets/YanzheChen/MMMC) .
- [x] `2025.09.22` Code2Video has been accepted to the **Deep Learning for Code ([DL4C](https://dl4c.github.io/)) Workshop at NeurIPS 2025**.


---

### Table of Contents
- [🌟 Overview](#-overview)
- [🚀 Quick Start: Code2Video](#-try-code2video)
  - [1. Requirements](#1-requirements)
  - [2. Configure LLM API Keys](#2-configure-llm-api-keys)
  - [3. Run Agents](#3-run-agents)
  - [4. Project Organization](#4-project-organization)
- [📊 Evaluation: MMMC](#-evaluation----mmmc)
- [🙏 Acknowledgements](#-acknowledgements)
- [📌 Citation](#-citation)

---

## 🌟 Overview

<p align="center">
  <img src="figures/first.png" alt="Overview" width="90%">
</p>

**Code2Video** is an **agentic, code-centric framework** that generates high-quality **educational videos** from knowledge points.  
Unlike pixel-based text-to-video models, our approach leverages executable **Manim code** to ensure **clarity, coherence, and reproducibility**.

**Key Features**:
- 🎬 **Code-Centric Paradigm** — executable code as the unified medium for both temporal sequencing and spatial organization of educational videos.
- 🤖 **Modular Tri-Agent Design** — Planner (storyboard expansion), Coder (debuggable code synthesis), and Critic (layout refinement with anchors) work together for structured generation.
- 📚 **MMMC Benchmark** — the first benchmark for code-driven video generation, covering 117 curated learning topics inspired by 3Blue1Brown, spanning diverse areas.
- 🧪 **Multi-Dimensional Evaluation** — systematic assessment on efficiency, aesthetics, and end-to-end knowledge transfer.

---

## 🚀 Try Code2Video

<p align="center">
  <img src="figures/approach.png" alt="Approach" width="85%">
</p>

### 1. Requirements

```bash
cd src/
pip install -r requirements.txt
````

Here is the [official installation guide](https://docs.manim.community/en/stable/installation.html) for [Manim Community v0.19.0](https://www.manim.community/), to help everyone correctly set up the environment.

### 2. Configure LLM API Keys

Fill in your **API credentials** in `api_config.json`.

* **LLM API**: 
  * Required for Planner & Coder.
  * Best Manim code quality achieved with **Claude-4-Opus**.
* **VLM API**:
  * Required for Planner Critic.
  * For layout and aesthetics optimization, provide **Gemini API key**.
  * Best quality achieved with **gemini-2.5-pro-preview-05-06**.

* **Visual Assets API**:

  * To enrich videos with icons, set `ICONFINDER_API_KEY` from [IconFinder](https://www.iconfinder.com/account/applications).

### 3. Run Agents

We provide two shell scripts for different generation modes:

#### (a) Any Query

Script: `run_agent_single.sh`

Generates a video from a single **knowledge point** specified in the script.

```bash
sh run_agent_single.sh --knowledge_point "Linear transformations and matrices"
```

**Important parameters inside `run_agent_single.sh`:**

* `API`: specify which LLM to use.
* `FOLDER_PREFIX`: output folder prefix (e.g., `TEST-single`).
* `KNOWLEDGE_POINT`: target concept, e.g. `"Linear transformations and matrices"`.

---

#### (b) Full Benchmark Mode

Script: `run_agent.sh`

Runs all (or a subset of) learning topics defined in `long_video_topics_list.json`.

```bash
sh run_agent.sh
```

**Important parameters inside `run_agent.sh`:**

* `API`: specify which LLM to use.
* `FOLDER_PREFIX`: name prefix for saving output folders (e.g., `TEST-LIST`).
* `MAX_CONCEPTS`: number of concepts to include (`-1` means all).
* `PARALLEL_GROUP_NUM`: number of groups to run in parallel.

### 4. Project Organization

A suggested directory structure:

```
src/
│── agent.py
│── run_agent.sh
│── run_agent_single.sh
│── api_config.json
│── ...
│
├── assets/
│   ├── icons/          #  downloaded visual assets cache via IconFinder API
│   └── reference/      # reference images
│
├── json_files/         # JSON-based topic lists & metadata
├── prompts/            # prompt templates for LLM calls
├── CASES/              # generated cases, organized by FOLDER_PREFIX
│   └── TEST-LIST/      # example multi-topic generation results
│   └── TEST-single/    # example single-topic generation results
```


---

## 📊 Evaluation -- MMMC

We evaluate along **three complementary dimensions**:

1. **Knowledge Transfer (TeachQuiz)**

   ```bash
   python3 legacy/src/eval_TQ.py
   ```

2. **Aesthetic & Structural Quality (AES)**

   ```bash
   python3 legacy/src/eval_AES.py
   ```

3. **Efficiency Metrics (During Video Creating)**

   * Token usage
   * Execution time


👉 More data and evaluation scripts are available at:
[HuggingFace: MMMC Benchmark](https://huggingface.co/datasets/YanzheChen/MMMC)

---

## 🙏 Acknowledgements

* Video data is sourced from the **[3Blue1Brown official lessons](https://www.3blue1brown.com/#lessons)** and **[Grant Sanderson](https://x.com/3blue1brown)**.
  These videos represent the **upper bound of clarity and aesthetics** in educational video design and inform our evaluation metrics.
* We thank all the **Show Lab @ NUS** members for support!
* This project builds upon open-source contributions from **Manim Community** and the broader AI research ecosystem.
* High-quality visual assets (icons) are provided by **[IconFinder](https://www.iconfinder.com/)** and  **[Icons8](https://icons8.com/icons)**, which were used to enrich the educational videos.


---

## 📌 Citation

If you find our work useful, please cite:

```bibtex
@misc{code2video,
      title={Code2Video: A Code-centric Paradigm for Educational Video Generation}, 
      author={Yanzhe Chen and Kevin Qinghong Lin and Mike Zheng Shou},
      year={2025},
      eprint={2510.01174},
      archivePrefix={arXiv},
      primaryClass={cs.CV},
      url={https://arxiv.org/abs/2510.01174}, 
}
```

If you like our project, please give us a star ⭐ on [GitHub](https://github.com/showlab/Code2Video) for the latest update!
[![Star History Chart](https://api.star-history.com/svg?repos=showlab/Code2Video&type=Date)](https://star-history.com/#showlab/Code2Video&Date)

## Current CLI workflow

The application provides both the CLI and the local Frame Web studio (see [STUDIO.md](STUDIO.md)); the research/demo instructions above are historical. Tasks accept general prompts and materials, not just textbooks or Markdown. Each video gets an independent directory under `video_projects/`, rather than splitting inputs across examples and projects.

### Quick start

Install using `scripts/setup_windows.ps1`, then run:

```powershell
.\.venv\Scripts\python.exe src\agent.py --list-styles
.\.venv\Scripts\python.exe src\agent.py --list-tts
.\.venv\Scripts\python.exe src\agent.py --prompt "Introduce a product" --style presentation --reference "materials/product.png" --project "video_projects/product-demo" --plan-only
.\.venv\Scripts\python.exe src\agent.py --project "video_projects/product-demo" --resume --allow-generated-code
```

`--plan-only` produces outline and storyboard. `--stop-after` accepts outline/storyboard/audio/assets/code/render/review/compose. Generated Python executes locally: AST validation is not a sandbox. Use an isolated account without sensitive files.

### Inputs and media

`--task-file` accepts prompt, style, materials, references, config, tts and review. Input paths are relative to the task JSON; CLI options take precedence. `--material` and `--reference` are repeatable; `--topic` remains a compatibility alias. Configure text and vision APIs separately using Responses or Chat Completions. Planning with images requires an image-capable model.

- Text, Markdown, JSON, CSV, code/YAML and text PDFs provide context. Scanned PDFs are retained without automatic OCR. Other files are archived with type, size and SHA-256; archival does not imply semantic understanding.
- Images are sent to outline/storyboard planning and can appear in generated scenes through the image object returned by `self.asset(key)`. Use authorized inventory keys, not arbitrary paths. SVG icon sources and authorized local SVG remain supported; archival alone does not register an icon.
- Videos contribute three sampled planning frames, not full temporal understanding or automatic edit selection.
- Audio is archived by default. Enable `materials.transcription.enabled` and configure its api_key, base_url and model to add cached OpenAI-compatible transcription context. Verify transcripts manually; ASR is separate from TTS and a real third-party ASR endpoint has not been validated.

### Independent projects and secrets

`input/materials` and `input/references` hold inputs; `prompts` stores templates, requirements and style snapshots; `code/runtime` holds the trusted runtime. `output` contains plans, narration, request records, logs, subtitles and `final.mp4`. `task.json` records requirements and project input paths; `settings.json` is redacted. `prompts/style.json` stores style metadata, video defaults, policy and stage guidance. Resume prefers a valid project snapshot, even if the global package changed or was removed; absent stage entries fall back to the snapshot policy. The style id and snapshot structure must match. Global updates do not automatically upgrade existing projects. Do not blindly reuse caches after changing inputs or styles.

Use environment variables, `.env` or ignored private configuration for credentials. Public presets contain placeholders such as `${ENV_NAME}` only; never put keys in tasks, style packages or commits. Redaction is not a complete privacy guarantee: inputs, prompts, requests and transcripts may be confidential. Inspect project folders before sharing and rotate credentials exposed in chat.

### Application styles and TTS

Built-in styles are default, clean_education, 3b1b_inspired, infographic and presentation. Each has original outline/storyboard/code/review guidance; explicit user video settings override style defaults. These are pipeline instructions for third-party LLMs, not Codex skills. Downloaded upstream materials are research-only. See [style package provenance](style_skills/README.md).

Edge remains the default. Other providers include openai/http/none/qwen_audio. Applications can call `narration.register_tts_provider(name, factory)`; the standalone CLI discovers installed Python `code2video.tts` entry-points. The factory receives settings; the instance implements `synthesize(text, destination)`, writes compatible audio and returns a dictionary with duration and optional subtitles. `--list-tts` lists providers. Install trusted plugins only: they execute Python.

Qwen uses `config.qwen-tts.example.json` with `C2V_QWEN_TTS_API_KEY`. The `qwen_audio` provider calls `/api/v1/services/audio/tts/SpeechSynthesizer` on the configured base_url origin, not `/audio/speech` (404 on the tested endpoint). Returned audio URLs are downloaded without the API Authorization header. Real synthesis succeeded with `qwen-audio-3.1-tts-next`, `qwen-audio-3.0-tts-plus` and `qwen-audio-3.0-tts-flash`, using voice `longanhuan_v3.6`. `qwen-audio-3.1-tts-flash` failed with HTTP 400 / engine error 411; model listing is not proof of availability. For next, absent an explicit text_prompt, the adapter currently uses the spoken text; confirm that parameter meaning with the provider.

```powershell
.\.venv\Scripts\python.exe src\agent.py --config config.qwen-tts.example.json --tts-model qwen-audio-3.0-tts-flash --check-tts
```

### Deterministic montage

Task example (paths relative to the task file):

```json
{
  "prompt": "Introduce a product with footage",
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

`task.config.montage` is user-authored, deterministic configuration, not model-selected editing. Each source must uniquely match the name of an archived task.materials or references entry. Avoid duplicate basenames; unarchived paths are not a shortcut. start is the destination timeline start, duration the replacement length, and source_start the source offset, all in seconds. Clips replace generated animation intervals with full-frame, aspect-preserving footage and black padding. Generated narration and subtitles remain; clip audio is not mixed in. Music loops into the generated audio with the specified volume coefficient. Uncovered intervals retain generated animation.

OpenMontage is AGPLv3. Only architectural ideas such as independent projects, stage artifacts and provider separation are referenced; its source code is not copied. This is not the full OpenMontage product, automated footage search or model-selected editing.

### Validation

Run `scripts/cli_smoke.py`, `scripts/qwen_tts_smoke.py` and `scripts/smoke.py` using the project virtual environment; `scripts/montage_smoke.py` checks montage separately. Mock API tests do not validate real providers, ASR, Edge network access or online icon services. Automatic visual review samples generated animation frames before montage composition. It does not review replacement footage or added music, and cannot certify the final montage. Watch and listen to the entire final export manually, checking footage transitions, black padding/cropping, music looping and levels, narration/subtitle alignment, facts and licensing.
