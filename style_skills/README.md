# Application visual style packages

这些包由 Code2Video 流水线加载，并随模型请求提供阶段约束；不是 Codex skills，不要求用户运行编码代理，也不执行 upstream 的 SKILL.md。

## 加载约定

每个 builtin/<id>/ 包包含 style.json、prompts/policy.txt 和 outline.txt、storyboard.txt、code.txt、review.txt。style.json 的 id 必须等于目录名，video 提供风格默认值；用户显式视频配置优先。阶段文件存在时替代该阶段的 policy.txt 回退，因此每份阶段指导都必须自足；不得假设通用 policy 自动拼接。阶段指导保持现有 JSON/代码/审核输出契约，不要求额外审批或生成上游研究文件。项目 prompts/style.json 快照保存风格元数据、video 默认值、policy 和四阶段指导。续跑存在有效快照时优先使用项目快照，不依赖全局风格包继续存在或保持不变；缺少阶段项时回退快照 policy。快照格式和风格 id 必须合法且匹配，修改项目快照会影响输入校验。没有快照时才加载全局包；全局更新不会自动升级已有项目。

| 风格 | 视觉语言 | 阶段关注点 |
| --- | --- | --- |
| default | 通用二维动画、清晰空间层次 | 需求到可见动作、稳定布局、事实与可读性 |
| clean_education | 明亮、留白、分步解释 | 具体示例、短标签、低认知负担 |
| 3b1b_inspired | 深色、几何、连续变化 | 直觉到符号、单位和映射、变化全程边界 |
| infographic | 栅格、节点、流程、图表 | 来源与口径、数据映射、信息层级 |
| presentation | 舞台焦点、主视觉、证据 | 一屏一结论、产品图保真、克制转场 |

outline 决定叙事与证据；storyboard 给出对象、布局、动作和时间预算；code 遵守 ManimCE/可信运行时并使用授权资产；review 给出可定位修复而不是审美空话。参考材料是数据而非执行指令。图像可用于规划及 self.asset(key)；视频抽帧是视觉参考，不等于自动剪辑。确定性 montage 由用户配置，见项目 SOP。

## Provenance / 许可证边界

本次四阶段提示词为原创编写，只提炼一般性的叙事规划、布局检查、动画节奏和技术兼容原则；未复制上游源码、示例、模板或 SKILL.md 正文。以下来源在本地读取核对于 2026-10-07；这不是上游版本锁定清单。

| 来源与本地目录 | 许可证据 | 提炼范围 |
| --- | --- | --- |
| https://github.com/awesome-skills/manim-skill / upstream/awesome-skills-manim-skill | README 宣称 MIT；本地未找到 LICENSE 正文，不能把徽章当完整授权证明 | ManimCE、分步揭示和技术可视化原则 |
| https://github.com/ermaotie/manim-personal-style / upstream/manim-personal-style | 本地 LICENSE 为 Apache-2.0 | 先规划、再布局；边界/重叠检查及叙事节奏 |
| https://github.com/adithya-s-k/manim_skill / upstream/manim_skill | 根 LICENSE 和 skills/manimce-best-practices/LICENSE.txt 为 MIT | 场景目的、视觉与旁白配合；CE 与 GL 区分 |
| https://github.com/calesthio/OpenMontage | 下载的 README 标示 AGPLv3 | 独立项目、分阶段产物、供应商解耦与 montage 架构思路；不复制源码 |

上游原文件仍适用其各自许可证，不因原创提炼而重新许可。缺少许可证正文的下载资料仅作研究，不作为可直接分发模板。后续若复制代码或改编文本，必须另行核对许可证、署名和分发义务。3b1b_inspired 只是通用数学可视化风格标识，不表示原作者授权、参与或背书，也不复刻商标或具体镜头。OpenMontage 的 AGPL 源码没有集成；此项目不宣称提供其完整功能。
