# 独立视频项目输入示例

这里是可复制的、无密钥的项目包，不是生产视频目录。领域内容只有显式选择项目包时才会注入新项目：

- `civil_service/`：考公提示词和课程要求，输入文件为 `civil_service/course.json`。
- `cow_grass/`：课程要求、教材、完整提示词及牛吃草运行时扩展，输入文件为 `cow_grass/course.json`。
- 通用初始化只复制中立提示词、通用运行时和空扩展注册表，不自动携带考公或牛吃草内容。

## 使用项目包

在仓库根目录运行；项目包内教材会复制到项目并进入模型上下文：

```powershell
.\.venv\Scripts\python.exe src\agent.py `
  --project "projects\牛吃草-v001" `
  --topic "行测数量关系：牛吃草问题" `
  --project-pack "examples\video_project\cow_grass" `
  --plan-only
```

考公项目可以使用 `--project-pack examples\video_project\civil_service`，并传入自己的 `--material`。也可分别使用 `--course-file`、`--prompts-dir`、`--material` 和 `--resource`，不选择项目包。

教材副本、完整提示词、脱敏配置和过程文件都在项目中。续跑不必重复传入外部输入：

```powershell
.\.venv\Scripts\python.exe src\agent.py `
  --project "projects\牛吃草-v001" `
  --topic "行测数量关系：牛吃草问题" `
  --resume --allow-generated-code
```

## 自建项目包

复制需要的示例包到自己的目录，再修改 `course.json`、`prompts/policy.txt` 和其他四阶段模板、`materials/`。Web 创建课程时选择项目包，或 CLI 使用 `--project-pack`；项目包默认设置可被本视频显式输入覆盖。

领域动画放入 `code/runtime/extensions/*.py`，由 `code/runtime/extensions.json` 显式声明入口。模型只能通过 `self.extension("注册名", ...)` 调用已注册入口，无需修改通用流水线。扩展是可信本地 Python，不是沙箱；仅使用自己审核过的项目包。上传的普通 Python 资源只归档到 `code/svg/`，不会变为可执行扩展。

同名项目目录不自动覆盖。修改版使用新的项目目录，或在 Web 中保存为独立新版本。
