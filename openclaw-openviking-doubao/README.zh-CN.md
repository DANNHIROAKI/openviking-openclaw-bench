# OpenClaw + OpenViking 集成仓库（豆包 API + Local Mode）

这是一个**可直接上手的集成仓库**，目标非常明确：

把 **OpenViking** 挂到 **OpenClaw** 的 `ContextEngine` slot 上，并且默认按：

- 豆包 / 火山方舟 API
- Local Mode
- OpenViking `0.3.8`
- OpenClaw npm 稳定版 `2026.4.14`

来安装。

## 你拿到仓库后先做什么

直接按下面顺序执行：

```bash
bash scripts/00_check_requirements.sh
bash scripts/10_install_openclaw_stable.sh
bash scripts/11_onboard_openclaw.sh
bash scripts/20_install_openviking_local_doubao_prefilled.sh
bash scripts/30_verify.sh
```

如果你已经安装过 OpenClaw，可以跳过前 2 步。

## 文档入口

- `TUTORIAL.zh-CN.md`：完整详细教程
- `GET_DOUBAO_API_KEY.zh-CN.md`：如何在火山方舟拿 API Key
- `templates/openclaw.plugins.openviking.local.example.json`：最终应达到的插件配置形态
- `templates/ov.conf.doubao.prefilled.local.json`：已预填实验 Key 的本地配置模板

## 目录说明

- `plugin/`：OpenViking 官方 OpenClaw 插件源码快照
- `scripts/`：安装、校验、重置、日志查看脚本
- `templates/`：Doubao Local Mode 配置模板

## 最常用的命令

```bash
openclaw config get plugins.slots.contextEngine
openclaw config get plugins.entries.openviking.config
openclaw plugins inspect openviking
openclaw logs --follow
tail -f ~/.openviking/data/log/openviking.log
```

如果你看到：

- `plugins.slots.contextEngine` 是 `openviking`
- OpenClaw 日志里出现 `openviking: registered context-engine`

那就说明已经挂载成功。
