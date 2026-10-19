# 视频工作台 API

入口：`https://vedio.myaihub.asia`。在用户面板的「开放 API」创建调用密钥；原文只显示一次。所有 API 使用 `Authorization: Bearer frame_...`，包括视频和图片下载。调用密钥仅可访问本人的配置、素材、音色及视频任务，不能充值或管理用户。

## 自动生成与轮询

```bash
curl https://vedio.myaihub.asia/api/jobs \
  -H "Authorization: Bearer $FRAME_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"用60秒讲解牛吃草问题，明确净消耗的含义","style":"studio_sketch","duration":60,"orientation":"landscape","auto_approve":true,"reference_urls":[],"source_ids":[]}'
```

返回 HTTP 202 和 `{"id":"..."}`。每3至5秒请求 `GET /api/jobs/{id}`，状态为 `complete` 后读取 `video` 路径并携带同一密钥下载。`failed` 包含错误说明；已发生的模型消耗不会因生成失败而取消。`auto_approve=false` 时会在大纲和分镜阶段暂停，等待确认。

`duration` 为15至120秒的目标时长；`orientation` 为 `landscape` 或 `portrait`。主题通过 `GET /api/styles` 获取，目前支持 `studio_noir`、`studio_editorial`、`studio_sketch`。

## 模型和配音配置

可以先 `POST /api/config` 保存个人配置，也可以在 JSON 任务请求的 `config` 字段内传入完整配置，后者仅用于该任务。任务配置加密归档，重启、审核和重试保持相同模型及凭据。

```json
{
  "use_platform": false,
  "text": {
    "base_url": "https://your-provider.example/v1",
    "model": "your-generation-model",
    "api_key": "YOUR_PROVIDER_KEY",
    "protocol": "chat_completions",
    "fallback_models": [],
    "max_tokens": 24000
  },
  "vision_inherit": false,
  "vision": {
    "base_url": "https://your-provider.example/v1",
    "model": "your-vision-model",
    "api_key": "YOUR_VISION_KEY",
    "protocol": "chat_completions",
    "fallback_models": [],
    "max_tokens": 6000
  },
  "tts": {"provider": "edge", "voice": "zh-CN-YunxiNeural"}
}
```

模型名称自由填写，协议支持 `chat_completions` 和 `responses`。`vision_inherit=true` 时使用生成模型进行图片审核，所选模型必须支持图片。`api_key` 留空保留同一接口已有密钥；更换接口地址后必须重新填写，`clear_key=true` 明确删除。

`GET /api/config` 只返回配置状态，不返回密钥。个人模型服务不使用部署机器的模型密钥。`use_platform=true` 仅在管理员配置并启用平台模式后可用。

`GET /api/voices` 返回322种在线音色及 `sample_url`。试听为2秒音频，13种推荐音色已预生成；其他音色首次试听生成后缓存。基础在线配音免费，不启用其他付费素材或语音渠道。

## 上传与素材

带文件的任务使用 multipart/form-data，与网页字段一致：

```bash
curl https://vedio.myaihub.asia/api/jobs \
  -H "Authorization: Bearer $FRAME_API_KEY" \
  -F 'prompt=根据上传文稿生成手绘讲解' \
  -F 'style=studio_sketch' -F 'duration=60' \
  -F 'orientation=landscape' -F 'auto_approve=true' \
  -F 'source_ids=[]' -F 'files=@lesson.pdf'
```

最多10份文件，每份50 MB。multipart 使用已保存的个人配置；JSON 的 `config` 支持单任务覆盖。`reference_urls` 在 JSON 中为字符串数组，在 multipart 中为每行一个链接。`source_ids` 在 multipart 中为 JSON 数组字符串。

- `POST /api/sources/search`：`{"query":"复利","platform":"wikipedia","limit":6}`；来源为 `wikipedia`（百科正文）和 `library`（我的素材库）。旧 `web` 值兼容映射到百科；不可靠的 Bing、B站、知乎搜索已停用。搜索返回已读取、已归档的正文及 ID，可直接作为 source_ids 选用；unreadable_count 表示被过滤的页面数量。
- `POST /api/sources/ingest`：`{"urls":["https://公开来源"]}`；正文读取成功才返回素材 ID。
- `GET /api/sources`、`GET /api/sources/{id}`：仅当前用户的素材。

部分网页需要登录或验证，视频需要公开可读取字幕；无法读取时请换源或上传文稿，不会把搜索摘要当作已验证正文。

## 大纲与分镜

`GET /api/jobs/{id}/planning` 返回 `documents.outline` 和 `documents.storyboard`，每个文档包含 `document`、`version`、`approved`。以下 `stage` 是 `outline` 或 `storyboard`：

- `PUT /api/jobs/{id}/planning/{stage}`：`{"version":"当前版本","document":{...}}`，保存草稿。
- `POST /api/jobs/{id}/planning/{stage}/revise`：增加 `feedback` 字段，AI 改稿后等待确认。
- `POST /api/jobs/{id}/planning/{stage}/approve`：`{"version":"当前版本"}`，确认并继续。
- `PATCH /api/jobs/{id}/planning-mode`：`{"auto_approve":true}`，自动确认后续规划。
- `POST /api/jobs/{id}/retry`：重试失败任务。
- `GET /api/jobs/{id}/usage`：逐次调用用量，缺少上游 usage 的调用明确标记未计量。

HTTP 401：凭据无效；403：权限不足；404：资源不存在或不属于当前用户；409：任务忙或文档版本冲突；429：请求频率限制。服务器当前串行渲染，避免同时抢占资源；409 时应稍后重试。

## 修改成片与 AI 建议

已完成且 `can_revise=true` 的作品支持独立新版本，原片及原始输入保留：

```http
POST /api/jobs/ORIGINAL_ID/revisions HTTP/1.1
Content-Type: application/json
Authorization: Bearer YOUR_FRAME_KEY

{
  "feedback": "把最后的回忆题改为询问这个搭配的含义，提问后停顿两秒再给答案。",
  "auto_approve": false,
  "request_id": "a-unique-request-id-at-least-16-characters"
}
```

返回202与新 `id`、`parent_id`、`revision_number`。同一原片和 `request_id` 重复提交返回同一任务；修改意见改变时使用新的 ID。轮询新任务，默认暂停在修改后的分镜；通过上述 planning 接口调整、确认，再生成配音和画面。新版本沿用原任务的模型配置、素材与已核验的教学来源。`revision_summary` 说明本次调整，`revision_parent` 可用于原版对比。

- `POST /api/jobs/{id}/revision-advice`：用户主动发起视觉审核，返回202；从成片抽帧并结合分镜给出至多四条建议，使用已配置视觉模型并记录实际用量。
- `GET /api/jobs/{id}/revision-advice`：读取/轮询已有结果，不调用模型。状态为 `idle`、`queued`、`running`、`ready`、`failed`。
- `ready` 返回 `summary` 和 `suggestions[]`，每条含 `title`、`reason`、可直接提交但仍可编辑的 `feedback`。审核只提供建议，不自动改片；没有明显问题时建议可为空。

此功能对应网页中的「修改视频」与「AI 帮我看看」。抽帧审核不能代替完整播放和声音检查。

## 获取可用模型

`POST /api/config/models`：`{"role":"text","base_url":"https://服务商域名/v1","api_key":"当前服务的密钥"}`。`role` 支持 `text`（内容生成）、`vision`（视觉审核）、`tts`（自定义配音）。返回 `{"models":["模型名称", "..."]}`，列表去重并排序。使用对应服务的 `/models` 接口，不调用生成接口。

密钥留空时，只会使用当前用户在**相同地址、相同用途**下已保存的密钥；`clear_key=true` 不复用。未保存的新地址和密钥可直接获取列表，该操作不保存配置。服务不支持列表时，仍可手动填写模型名称。网页密钥输入项标识为 `text_api_key`、`vision_api_key`；面板显示中文，API JSON 保持每个服务内的 `api_key` 字段兼容。

## 创作模板与笔记复盘

任务支持 `template_id`：`explainer`（知识讲解）、`documentary`（微纪录片）、`product`（产品种草）、`history_map`（历史地图故事）、`math_visual`（数学看得见）、`word_story`（单词奇遇记）、`notes`（笔记放映室）。模板规定叙事与视觉约束，画风仍使用 `style` 单独选择。

`notes` 允许最长300秒，必须用 multipart 上传至少40字、可提取正文的笔记（TXT、Markdown、文字 PDF）。扫描 PDF 需要先转文字。超出本课容量会明确要求拆分；不会静默丢弃剩余笔记。建议 `auto_approve=false`，先审阅知识框架再制作。

## AI 剪辑：提交、确认与导出

所有路径支持同一 Bearer 调用密钥。视频内容是任务输入，生产运行不依赖 Codex/Claude。镜头与语音使用本地免费组件；画面理解和选段使用用户配置的两个模型接口，记录实际模型用量。站内自动余额扣费仍关闭。

```bash
curl https://vedio.myaihub.asia/api/edits \
  -H "Authorization: Bearer $FRAME_API_KEY" \
  -F 'mode=product' -F 'target_duration=60' \
  -F 'orientation=portrait' -F 'captions=true' \
  -F 'prompt=围绕同一件商品，保留实物演示、主要卖点以及完整价格和优惠门槛，删除无关弹幕和重复催单。' \
  -F 'files=@livestream-fragment.mp4'
```

返回202及 `id`。每5秒轮询 `GET /api/edits/{id}`；`GET /api/edits` 返回自己的剪辑历史。状态依次为 `analyzing` → `awaiting_review` → `rendering` → `complete`；`failed` 可用 `POST /api/edits/{id}/retry` 重试。

- 模式：`highlights`（精华）、`product`（直播带货）、`gaming`（游戏高光）、`documentary`（叙事纪实）。
- 目标：普通剪辑5至120秒；带货30至120秒，成片也强制30至120秒。
- 素材：每次1至3份 MP4/MOV/WebM/MKV，单份150 MB、合计400 MB。带货单份最长15分钟、合计30分钟；其余单份5分钟、合计10分钟。上传完成前不要关闭请求。
- 原画面完整保留，比例不同时留边；原声保留，不添加未经授权的音乐。字幕来自本地识别，发布前应校对。
- `GET /api/edits/{id}/source/{source_id}` 可预览原片，支持 Range 请求。

`awaiting_review` 返回 `plan.clips`（原片的 source_id/start/end/reason/effect）、`plan.subtitles`（成片的 start/end/text）、`plan.summary` 及 `version`。

通过 `PUT /api/edits/{id}/plan` 提交 `{ "version": 当前版本, "clips": [...], "summary": "...", "subtitles": [...] }`。`effect` 为 `none` 或 `focus`，最多16段；重复、越界、非有限时间被拒绝。版本冲突返回409。修改选段后将 `subtitles` 设为null或省略，系统按新时间线重新匹配；只改字幕时提交完整字幕数组。字幕按成片秒数排列且不重叠。

确认后 `POST /api/edits/{id}/render`。带货导出前再次核对商品、报价条件和语句边界；核对未通过会保留方案供修改。完成后可下载 `/video`、`/poster`、`/subtitles`、`/timeline`、`/project`。`project` 为 OpenTimelineIO 工程，需在兼容软件中重新关联原片；字幕与轻聚焦效果已烘焙在 MP4，OTIO 只导出剪点。
