# AI 剪辑部署与验收

公共入口使用既有 Go API，Python worker 通过 Unix socket 接收签名请求。素材、方案、进度和输出位于 `video_projects/edit-{id}`；每个任务记录 owner_id，所有原片、字幕、成片、工程下载均检查归属。个人 API 配置在创建任务时加密冻结；任务重试不悄悄换成账户后来修改的配置。

## 安装

在项目根目录执行 `python3 deploy/setup_editing.py`。脚本使用隔离的 `.venv-editing`，安装已固定版本的 PySceneDetect、faster-whisper、PyAV、OpenTimelineIO 与繁简转换组件。Whisper small 的四个文件按固定 Hugging Face revision 下载并验证 SHA256，存于 private/models，不进入 Git。CPU int8，无需 GPU 或额外语音密钥。原先 base 模型仅作为已有部署的兼容后备。

主渲染依赖 `src/requirements.txt` 与 Dockerfile.worker 固定 Pillow 12.1.0：Manim 0.21 的图片合成接口不兼容 Pillow 13。升级镜像前保留上一镜像，构建后再切换；已有容器不受镜像标签变化影响。

本站服务器资源有限，创作与剪辑共用单个任务执行器。普通上传最多5分钟/份；带货15分钟/份、总计30分钟，不能声称处理整场数小时直播。分析和导出给出阶段及粗略耗时；重启时中断任务会标为可重试。

## 带货质量约束

- 模型根据镜头、语音及均匀抽帧选取语义完整的范围；程序按完整片段组合到30至120秒，不截半句话凑时长。
- required 片段不能在时长编排时丢弃；价格和优惠门槛必须在同一完整片段内。
- 分析后的方案及导出前均核对商品、优惠门槛、否定条件和悬空转折。模型复核仍不能代替发布者确认。
- 用户可预览原片范围、调整顺序与时间、校对字幕，再确认导出。修改时间后重新匹配字幕，避免旧字幕错位。
- 保留原声与完整画幅；最多两处轻聚焦，不遮挡商品或价格。不虚构折扣、功效、销量，不添加无授权音乐。
- 视频完整解码、时长及1080p尺寸检查；另导出 SRT、JSON 时间线和 OTIO 工程。OTIO 需要重新关联原片，字幕/效果以 MP4 为准。

## 可重复检查

- `.venv/bin/python scripts/editing_smoke.py`：真实音频/无音频混剪、字幕、动效、解码、工程；范围、重叠、格式和带货时长拒绝。
- `.venv/bin/python scripts/editing_api_smoke.py`：签名接口、归属、版本冲突、导出条件、重复提交。
- `.venv/bin/python scripts/notes_api_smoke.py`：真实文本抽取、乱码、坏PDF、笔记容量及模板传递。
- `.venv/bin/python scripts/frame_clock_smoke.py`：真实渲染验证帧与配音不累积漂移。
- `.venv/bin/python scripts/commerce_model_acceptance.py`：**显式真实模型消耗**。检查完整报价通过、删优惠门槛失败、跨商品拼价失败。
- `deploy/check_product_workspace.py` 使用隔离测试站7861的账号文件，检查访客登录、剪辑草稿保留、笔记引导和响应式布局。测试账号不写入代码。

实际带货示例验收源为原创95.7秒产品演示录屏与合成旁白，标识“非直播实录”，导出约58.8秒。包含闲聊、商品演示与模型调用收费限制；应保留原始稿和质检记录。此验收不冒充真实主播的商业投放成绩。
