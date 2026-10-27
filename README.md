# qi-shu 方案工作台

本机开发中的方案工作台：从调研资料整理需求与事实，经人工确认后生成方案初稿、审核并导出 Word。当前为早期 MVP，使用虚构资料验证；真实业务质量、复杂文档及多人权限尚待验证。不要将此版本直接部署给多人或上传敏感资料。

## 本机运行

需要 Python 3.12、Node.js 及 npm。依赖安装会访问软件包仓库，模型调用按服务商用量收费。

1. 在 `backend` 目录创建虚拟环境并安装依赖：

   ```sh
   python3.12 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   cp .env.example .env
   ```

   如需调用模型，在 `backend/.env` 中填写自己的 DeepSeek API Key；不要提交或分享该文件。

2. 在 `backend` 目录启动服务：

   ```sh
   .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8766
   ```

3. 另开终端，在 `frontend` 目录安装依赖并启动：

   ```sh
   npm ci
   npm run dev -- --hostname 127.0.0.1 --port 3000
   ```

4. 浏览器打开 http://127.0.0.1:3000/。模型任务在发起前会提示发送范围及费用，需人工确认。

资料和数据默认保存在本机 `data/`，不纳入仓库。当前没有正式的多人登录及权限隔离，服务仅监听本机。

## 验证

在 `backend` 运行 `.venv/bin/python -m pytest -q`；在 `frontend` 运行 `npm run lint` 和 `npm run build`。仓库中的模板和参考案例均为虚构示例。

## 许可证

MIT，见 [LICENSE](LICENSE)。
