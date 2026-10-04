# 旧研究代码（归档）

这里保留原研究版本的阶段提示词、错误分析器、素材下载器与评测代码。新视频流水线不导入此目录，也不把它加入渲染 PYTHONPATH。

当前入口是 src/agent.py 和 web/app.py，项目自带的模板与扩展见 examples/video_project/README.md。src/run_agent*.sh 只是当前 CLI 的兼容包装器，不是旧多阶段入口。

历史评测可从仓库根目录用 python legacy/src/eval_TQ.py 或 python legacy/src/eval_AES.py 调用；数据、依赖与旧接口兼容性不属于当前视频生产回归保障。此目录不要作为项目包或运行时复制到新视频。
