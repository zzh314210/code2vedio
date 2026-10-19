# 视频创作与剪辑调研及采用说明

调研日期：2026-10-19。仓库星数为当日 GitHub API 快照，后续会变化。目标是稳定的网页产品，运行时只用用户模型 API 与本地处理，不执行 Codex/Claude agent。

| 项目 | 调研时规模/来源 | 采用方式 |
| --- | --- | --- |
| [FFmpeg](https://github.com/FFmpeg/FFmpeg) | 约6.5万星 | 实际探测、选段、原声拼接、字幕、响度统一、1080p导出与完整解码验收。只生成经过验证的参数列表。 |
| [OpenAI Whisper](https://github.com/openai/whisper) + [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | 约11万/2.6万星；MIT | 实际本地 CPU/int8 语音识别，small 模型为主要配置；预下载完整模型，不在用户请求中联网下载，不调用付费语音 API。 |
| [PySceneDetect](https://github.com/Breakthrough/PySceneDetect) | 约5200星；BSD3 | 实际镜头变化检测；连续直播与游戏另加均匀抽帧，避免只识别硬切镜头。 |
| [OpenTimelineIO](https://github.com/AcademySoftwareFoundation/OpenTimelineIO) | Pixar 起源、ASWF；Apache2 | 实际导出带原片引用与剪点的 OTIO 工程，供继续精修。字幕及效果仍以烘焙 MP4 为准。 |
| [video-recap-skills](https://github.com/zenstory-ai/video-recap-skills) | MIT | 阅读 understanding/cut/assemble 技能，采用“证据—选段—时间线—合成—验收”的工作方法；未接其额外云端语音依赖。 |
| [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) | 约1.2万星；Apache2 | 参考真实主体优先、克制动效、重要信息停留、逐镜验收的方法；不把产品视频做成密集文字页。 |
| [Remotion](https://github.com/remotion-dev/remotion) 与官方 skills | 约6.5万星 | 阅读字幕、地图与交互等规范；未采用其运行时，避免给本产品引入额外商业许可成本与重复渲染栈。 |
| [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) | 高星视频流水线 | 参考成片编排与素材管理；未接需要外部付费/账户密钥的素材渠道。 |
| [auto-editor](https://github.com/WyattBlue/auto-editor) | 成熟自动剪辑工具及 skills | 参考识别、剪点、导出边界；不使用单纯“音量高=高光/静音=无价值”的策略替代语义与画面证据。 |
| [Google MediaPipe](https://github.com/google-ai-edge/mediapipe) | 约3.7万星 | 调研过；当前完整原画幅方案无需再叠加主体追踪依赖，暂不接入。 |
| [Manim Community](https://github.com/ManimCommunity/manim) | 既有项目渲染栈 | 延续动态图解，不另造执行系统；补充真实素材展示、知识地图、真实经纬度定位组件。 |
| [Natural Earth](https://www.naturalearthdata.com/) | 公共领域地图数据 | 使用实际110m陆地轮廓，点位与地图共用坐标投影，叙事关联线不冒充行进路线。 |

## 题材研究与边界

针对考研政治历史、数学、英语记忆及笔记复盘的专用剪辑技能，检索结果以小型或通用项目为主，未发现足以直接承担这些题材正确性与成片质量的成熟高星方案。因此复用上述可靠底座，固定各题材的内容契约、地理/图形组件、可修改大纲和分镜；不把“找到一个 skill”当作教学正确性的保证。

笔记放映室以用户原文为依据，生成知识框架、串讲、易混对照和回忆小测。历史需要可核验年代与位置；数学必须有真实变量变化；英语故事是原创记忆联想，不伪造词源。公开视频创作者可作为题材方向参考，未获取正文的网页/字幕不作为已阅读证据，也不复制讲稿。

## 交互原则

保持既有 shadcn/Radix 控件、Driver.js 引导与统一工作空间：任务入口清楚，选中项抬起强调，颜色服务模块层级；上传、分析、确认、导出各自有状态。错误保留素材和可修改方案；不会把异步任务提交说成成片完成。字幕校对在导出之前；移动端避免横向溢出，尊重减少动画偏好。

## 许可与素材

具体素材出处见 `templates/assets/ATTRIBUTION.md`。NASA 图片保留来源说明；Natural Earth 公共领域。自己的产品界面和原创笔记用于示例。游戏 API 验收使用 Commons 的 SuperTuxKart 480p 授权衍生视频，公开示例用同源原生1080p衍生文件重新导出，保留作者与 CC BY-SA 4.0 来源；公开剪辑样片按同协议发布并标明修改。产品演示验收录屏与合成旁白明确标识“非直播实录”，不将其伪装成真实主播案例。

FFmpeg 的许可证依实际构建功能为 LGPL/GPL；服务器执行不代表可忽略分发义务。项目不重新打包上游二进制；依赖许可见各上游仓库。无付费素材接口、无额外付费 TTS；模型理解、规划和审核会消耗用户配置模型额度。

另外阅读 [Anthropic 官方 frontend-design 技能](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md)，用于本轮交互验收：让视觉编号仅表示真实步骤、动效回应用户动作、提高正文可读性、把错误和空状态变成可操作的指引。遵循用户明确认可的现有布局，不为追求新外观重做网站。

### 用户指定创作者的公开资料核验

B站公开检索成功确认作者「空卡空卡空空卡」（UID 16671656），并返回《17min学完近代史｜史纲速成课01【地图速刷｜考研｜空卡】》（[BV1bwpxz4ELb](https://www.bilibili.com/video/BV1bwpxz4ELb/)）和《史前巨作！30min学完史纲所有考点！》（[BV1fhnbzjEhZ](https://www.bilibili.com/video/BV1fhnbzjEhZ/)）等公开元数据。其题目明确体现地图串讲、历史主线与压缩复习的题材方向。此次未取得和使用这些视频的完整字幕，不声称逐镜分析或复刻其脚本；本项目历史示例采用独立撰写的五四运动事件链。

### 记忆故事的主体可辨认性

真实样片检查发现，纯模型绘制的“香蕉船长”退化成普通胶囊形状，不能靠“渲染成功”验收。引入 Google 官方 [Noto Emoji](https://github.com/googlefonts/noto-emoji/tree/main/2D/svg) 的少量矢量美术素材（对应目录 Apache 2.0，不是字体 OFL）：香蕉、船、面包/小岛、机器人、猫、书本。固定演员尺度与舞台区域、离开/抵达等连续动作，并分离词义与例句排版；不要求额外图像生成 API。已有素材许可、源URL及SHA256归档。
