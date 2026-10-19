# 2026-10-19 产品发布验收

状态：正式站已部署并通过公网验收。

入口：https://vedio.myaihub.asia
发布时间（UTC）：2026-10-19T19:03:21.757723+00:00
验收完成（UTC）：2026-10-19T19:06:58.644952+00:00

## 发布内容

七个可选创作题材与真实1080p示例，笔记放映室，AI剪辑（含30–120秒直播带货切片），成片自然语言修改/原版保留、用户主动AI修改建议；既定UI、引导、可靠素材读取、进度、账号及开放API一并保留。产品细节与质量约束见 [PRODUCT_UPGRADE.md](PRODUCT_UPGRADE.md)。

## 验收结果

| 范围 | 实际结果 |
| --- | --- |
| 正式域名示例 | 七个创作和两个剪辑示例均可匿名播放、拖动与Range下载，来源链接正常；320/390/桌面弹窗尺寸检查通过。 |
| 正式域名访客路径 | 直接显示创作面板；实际操作时登录，需求和文件保留，退出清理、个人API隔离、减少动画设置通过。 |
| 正式域名用户面板 | 登录、个人配置、余额、管理界面、临时API凭据权限/撤销，真实免费搜索和语音试听通过。 |
| 原有作品兼容 | 真实考公作品938eef858abc的90秒1080p视频、字幕、鉴权Range、Bearer轮询/下载/撤销通过。 |
| 新版修改闭环 | 隔离站真实任务df8c5c601814：模型修改分镜、手动确认、60秒新版、真实视觉审核、用量、播放及原片对比通过；原片哈希保持一致。 |
| AI修改建议 | 隔离站真实按钮调用，带时间/幕次抽帧及候选复核；只在点击后调用，建议可编辑采用；小屏固定底部操作通过。 |
| 剪辑闭环 | 实际选段、原声、字幕、效果、1080p横竖屏及OTIO导出通过；同源第二次预览定位和动效编辑保留校对字幕通过。 |
| 渲染可靠性 | 30秒1080p受限Docker实测峰值817.9MiB；60秒月相重渲染成功。资源错误不触发模型重写；真实模型画面复核匹配最终版本。 |
| 代码与边界 | Go全部测试、Python接口/样式安全/模板快照/几何与内容约束通过；前端类型检查及生产构建通过。 |
| 运行 | code2vedio和code2vedio-worker均active；发布窗口无正在执行的用户任务，启动后无warning日志。 |

可重复命令：

```bash
C2V_CHECK_URL=https://vedio.myaihub.asia /data/code2vedio-browser-venv/bin/python deploy/check_showcase_gallery.py
C2V_CHECK_URL=https://vedio.myaihub.asia /data/code2vedio-browser-venv/bin/python deploy/check_guest.py
C2V_CHECK_URL=https://vedio.myaihub.asia /data/code2vedio-browser-venv/bin/python deploy/check_users.py
/data/code2vedio-browser-venv/bin/python deploy/check_live_video.py --job 938eef858abc
```

运行截图和详细日志保存在`.tmp`，不提交账户、作品或模型密钥。公开样片的哈希和人工精修说明随源码提交。

## 发布校验与回滚

Go二进制SHA256：`0cc53bd703c5bcf8d640c4151014d45bf422d6b5033f3ec8a464ff0daee32689`
前端入口SHA256：`b763b3246eb8b0f5b0eaa723ec80ea09351bbfb53727da7b67aedc40b619feb1`
回滚备份：`/data/code2vedio/.tmp/releases/20261019T185704Z`，权限0700；包含原Go二进制、前端、SQLite一致性备份、加密密钥/服务配置与旧代码归档。原用户项目没有移动或覆盖。

发布前已推送的检查点：`88945135ab2f75a265b8c296c862fb7b40df5b6d`。当前产品通过普通提交推送同一私有仓库，不强制覆盖远程。恢复前先检查运行任务，再恢复备份二进制/前端和匹配Python代码，重启本项目两项服务；无须回退用户数据以恢复网页。

## 明确边界

样片均为真实管线生成后验收，部分经过人工精修，不表示任意输入一次自动生成即可达到相同质量。带货示例是自制录屏和合成旁白的流程演示，并非真实主播投放案例。本站不调用Codex/Claude作为线上依赖。

生产站自动扣余额仍关闭；默认用户自带API按上游实际消耗付费。已有官方单价/预占/流水基础，启用平台收费需核对渠道价格；模型成本不包含渲染、存储及带宽。素材和额外配音渠道免费。
