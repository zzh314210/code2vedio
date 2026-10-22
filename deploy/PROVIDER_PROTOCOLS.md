# 国产供应商思考协议核验

核验日期：2026-10-22。按供应商与具体型号配置，不能把所有国产模型都当成同一套 OpenAI 参数。实现：`src/provider_protocols.py`；不付费回归：`scripts/domestic_reasoning_smoke.py`；真实本地渠道验证：`deploy/verify_reasoning_protocols.py`。

## 官方协议核对结果

| 接口 / 型号 | 请求体 | 档位与限制 | 验证范围 |
| --- | --- | --- | --- |
| DeepSeek 官方现行推理模型 | `thinking:{type:"enabled"}`，`reasoning_effort:"max"` | low/high/max；medium兼容映射high | 官方文档＋模拟接口 |
| Kimi 官方 K3 | `reasoning_effort:"max"` | low/high/max；不应发送旧版thinking开关；不能关闭；产品medium映射high | 官方文档＋模拟接口 |
| Kimi 官方 K2.6 / K2.7 Code | `thinking:{type:"enabled"}` | 这些型号没有K3的强度档位；Code不能关闭 | 官方文档＋模拟接口 |
| 智谱 GLM 5.2 | `thinking:{type:"enabled"}`，`reasoning_effort:"max"` | low/medium映射high，xhigh映射max | 官方文档＋模拟接口，参考sub2api的GLM映射 |
| 智谱 GLM 5.3 | 同上 | low/high/max；medium在本站映射high；不能关闭 | 官方文档＋模拟接口 |
| 智谱旧型号 | `thinking:{type:"enabled"}` | 不伪造GLM 5.2以后才支持的effort档位 | 官方文档＋模拟接口 |
| MiniMax M3.1 Flash 官方 | `reasoning_effort:"max"`，`reasoning_split:true` | low/medium/high/xhigh/max；始终思考；split只是输出格式开关，不是强度 | 官方文档＋模拟接口 |
| MiniMax M2.x 官方 | `reasoning_split:true` | 固定思考；没有M3.1的档位控制；不能关闭 | 官方文档＋模拟接口 |
| 阿里云托管 DeepSeek V4.1 Flash | `enable_thinking:true`，`reasoning_effort:"max"` | medium映射high | **真实成功＋非法档位400** |
| 阿里云直供 Kimi K3 | 同上 | low/high/max；与Moonshot官方的开关约束不同，直供文档允许false | **真实成功＋非法档位400** |
| 阿里云托管 Qwen 3.8 Flash | `enable_thinking:true`，`reasoning_effort:"xhigh"` | 产品high/max映射xhigh；不能同时发送thinking_budget | **真实成功＋非法档位400** |
| 阿里云转供 `kimi/kimi-k3` | `enable_thinking:true`，`reasoning_effort:"max"` | 当前文档标明仅max，不能关闭；不等同于无前缀的阿里云直供型号 | 官方文档＋模拟接口 |

旧Qwen等只有预算/开关控制的型号，不假称提供了原生max档位；调用策略标记model-default。未知私有别名使用兼容透传并标记型号未核实。豆包保留原max→high候选映射，但本轮官方文档页面未能取得参数正文，且无其密钥，**不将其列入已核实或真实调用通过的供应商**。未来新增型号需根据其文档扩展规则。

本轮原生国产供应商预设限定Chat Completions；不让切换为Responses绕过型号规则，接口不匹配会在计费授权之前拒绝。默认均为开启思考、产品强度max；不支持关闭的型号也在付费调用前拒绝。

阿里云Qwen 3.8使用 `max_completion_tokens` 限制“思考＋答案”的总输出，不使用只限制答案的 `max_tokens`，确保最高思考也受本次授权输出预算限制。不同时注入 `thinking_budget`，避免与effort冲突。

## 本地授权渠道的真实正反例

所有请求均使用原本地模型服务与凭据，无降级，无禁用思考。简单算术只用于验证协议、返回格式和用量，不作为推理质量基准。

| 型号 | 实际发送 | 返回结果 | 返回思考 Token | 非法档位对照 |
| --- | --- | --- | --- | --- |
| deepseek-v4.1-flash-1017 | enable_thinking=true、effort=max | 正确JSON，HTTP200 | 38 | HTTP400，明确列出reasoning_effort合法枚举 |
| kimi-k3 | enable_thinking=true、effort=max | 正确JSON，HTTP200 | 14 | HTTP400，明确列出reasoning_effort合法枚举 |
| qwen3.8-flash | enable_thinking=true、effort=xhigh | 正确JSON，HTTP200 | 54 | HTTP400，明确列出reasoning_effort合法枚举 |

正常调用响应编号分别为：

- DeepSeek：`chatcmpl-2e22f81a-9ed8-9678-a107-64415d50f0b1`
- Kimi：`chatcmpl-6d4aaa54-664c-9ab6-a20b-38bcdc02aeea`
- Qwen：`chatcmpl-f599c639-f86e-9676-916c-4643cc82c639`

这证明请求能正常完成、有思考用量，并且端点校验了该字段。接口通常不回传“实际采用的推理档位”，因此不能仅凭200或思考Token数断言后端计算量达到了某个量级；界面显示“发送策略”，不再标“实际强度”。GLM、MiniMax和Moonshot官方原生端点没有其专属凭据，本轮没有真实调用验证。

## 官方来源

- [DeepSeek思考模式](https://api-docs.deepseek.com/guides/thinking_mode) 与 [Chat API参数](https://api-docs.deepseek.com/api/create-chat-completion)
- [Moonshot思考模型指南（含K3强度与旧型号差异）](https://platform.moonshot.cn/docs/guide/use-kimi-k2-thinking-model)
- [智谱深度思考与GLM 5.2/5.3档位](https://docs.bigmodel.cn/cn/guide/capabilities/thinking)
- [MiniMax OpenAI兼容接口](https://platform.minimax.io/docs/api-reference/text-openai-api)
- [阿里云Chat Completions参数：reasoning_effort的逐型号映射](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)
- [阿里云DeepSeek专属接口](https://help.aliyun.com/zh/model-studio/deepseek-api)
- [阿里云Kimi专属接口](https://help.aliyun.com/zh/model-studio/kimi-api)

原始文档抓取及测试JSONL仅保存在本机 `.tmp/truth-upgrade/provider-docs` / `verified-protocols.*`；不包含密钥或私有思考正文。

## 发布验收

2026-10-22 06:00 UTC已发布；生产队列空闲时备份至 `.tmp/releases/truth-20261022T055942Z`，仅重启本项目worker。未修改平台模型价格、余额与凭据。14组原生/托管模型请求体、四档映射、固定思考型号拒绝关闭、协议不匹配在计费前拒绝、原有fallback/usage回归与前端构建通过。

预览登录后模型列表、配置保存/刷新Max持久化、管理员共用组件、390/768宽弹窗通过；正式HTTPS游客面板、两样片播放/拖动/Range与移动布局复测通过。最终Qwen总输出参数版本也再次真实调用成功，三模型非法强度对照均为400。
