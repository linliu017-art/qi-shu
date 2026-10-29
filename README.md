# 启枢 · 方案工作台

启枢是一个从调研资料到方案交付的工作台：导入资料，整理并核对需求，生成方案，协作审核并导出 Word。当前是**本地开发和试用版本**，包含实验性的多人账号与项目权限功能，尚未完成生产部署和真实业务验收。

## 当前能力

- 项目及成员协作，资料上传、版本管理和原文查看。
- AI 整理需求、事实和待确认问题，人工核对后生成需求清单。
- 选择模板、调整提纲、生成和编辑方案，审核后预览及导出 Word。
- 项目待办、任务状态、用量记录和工作台导航助手。

支持 TXT、Markdown、DOCX 和文字型 PDF；扫描件及图片文字识别尚未实现。模型输出和复杂文档解析需要人工核对。Word 分页预览需要本机安装 LibreOffice，并确保 `soffice` 可执行文件在 PATH 中；也可通过环境变量 `QISHU_SOFFICE_PATH` 指定路径。

## 本地运行

需要 Python 3.12、Node.js 及 npm。安装依赖需要访问软件包仓库；使用模型可能产生费用。

在 `backend` 目录中：

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8766
```

如需调用模型，在 `backend/.env` 中填写自己的 DeepSeek API Key；不要提交或分享该文件。默认数据目录为项目根目录的 `data/`，其中可能包含原始资料和业务记录，不要提交到 Git。

另开终端，在 `frontend` 目录中：

```sh
npm ci
npm run dev -- --hostname 127.0.0.1 --port 3000
```

访问 `http://127.0.0.1:3000/`。需要在本机试验多人账号时，可在启动后端前设置 `QISHU_EXPERIMENTAL_MULTIUSER=1`，并将前端地址配置到 `QISHU_ALLOWED_ORIGINS`；首次访问会引导创建管理员。多人模式仍是实验功能，请勿直接作为生产服务对外开放。

需求整理和方案生成会将选定内容发送给模型，发起前需确认发送范围及费用；导航助手在本地未识别输入时会自动发送输入文字进行识别。不要在助手中输入密码、密钥或敏感资料。

## 验证

在 `backend` 目录运行 `.venv/bin/python -m pytest -q`；在 `frontend` 目录运行 `npm run lint` 和 `npm run build`。仓库中的模板和参考案例均为虚构示例。

## 许可证

MIT，见 [LICENSE](LICENSE)。
