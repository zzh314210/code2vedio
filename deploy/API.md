# Frame 视频 API

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

- `POST /api/sources/search`：`{"query":"牛吃草 净消耗","platform":"bing","limit":6}`；来源为 `web`、`bing`、`wikipedia`、`bilibili`、`zhihu`、`library`。
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

## 获取可用模型

`POST /api/config/models`：`{"role":"text","base_url":"https://服务商域名/v1","api_key":"当前服务的密钥"}`。`role` 支持 `text`（内容生成）、`vision`（视觉审核）、`tts`（自定义配音）。返回 `{"models":["模型名称", "..."]}`，列表去重并排序。使用对应服务的 `/models` 接口，不调用生成接口。

密钥留空时，只会使用当前用户在**相同地址、相同用途**下已保存的密钥；`clear_key=true` 不复用。未保存的新地址和密钥可直接获取列表，该操作不保存配置。服务不支持列表时，仍可手动填写模型名称。网页密钥输入项标识为 `text_api_key`、`vision_api_key`；面板显示中文，API JSON 保持每个服务内的 `api_key` 字段兼容。
