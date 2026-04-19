# 获取豆包（火山方舟）API Key：给 OpenViking Local Mode 用

你这套集成默认走：

- OpenClaw + OpenViking
- Local Mode
- 火山方舟 / 豆包 API

## 1. 先准备账号

你需要先有火山引擎账号，并完成实名认证。火山方舟文档把“注册账号”和“实名认证”列为前提条件；如果多人共用账号，也可以创建 IAM 子账号做权限隔离。

## 2. 进入火山方舟控制台

进入火山方舟控制台后，先看两件事：

- `API Key 管理`
- `开通管理`

## 3. 创建 API Key

在 `API Key 管理` 页面创建一个新的 API Key。

建议：

- 给 Key 起一个易识别名称，例如 `openviking-local`。
- 创建后立刻复制保存；后续直接填到 `~/.openviking/ov.conf` 里。
- 如果你的运行环境 IP 固定，可在控制台给 API Key 加 IP 白名单，以减少误用风险。

## 4. 开通 OpenViking 需要的模型

OpenViking 至少要两类模型能力：

- Embedding：向量化 / 语义检索
- VLM：记忆抽取 / 内容理解

这个包默认的豆包模板使用的是：

- Embedding：`doubao-embedding-vision-251215`
- VLM：`doubao-seed-2-0-pro-260215`

如果控制台里这两个模型还没开通，就到 `开通管理` 或 `模型广场` 里开通。

## 5. 把 Key 填进 ov.conf

编辑：

```bash
vim ~/.openviking/ov.conf
```

把下面两个字段都替换成你的同一个方舟 API Key：

```json
"embedding": {
  "dense": {
    "api_key": "你的方舟API Key"
  }
},
"vlm": {
  "api_key": "你的方舟API Key"
}
```

通常 `api_base` 保持：

```text
https://ark.cn-beijing.volces.com/api/v3
```

## 6. 最快的本地安装命令

拿到 Key 以后，在这个仓库里运行：

```bash
export VOLCENGINE_API_KEY='你的方舟API Key'
bash scripts/install_local_doubao.sh
```

或者显式写 provider：

```bash
export VOLCENGINE_API_KEY='你的方舟API Key'
bash scripts/install_local_openviking_context_engine.sh --provider doubao
```

## 7. 没有充值能不能先试

火山方舟文档说明：

- 新用户可以先走免费推理体验额度
- 未开通模型服务时，很多模型仍有一定免费调用额度
- 还有“安心体验模式”，新用户可在接近 50w 免费 token 时自动暂停，避免超预期费用

但注意：实际是否能跑通，仍取决于你选的模型是否已在账号里开通并可调用。

## 8. 装完后检查

```bash
openclaw config get plugins.slots.contextEngine
openclaw config get plugins.entries.openviking.config
openclaw logs --follow
```

如果看到：

- `plugins.slots.contextEngine` = `openviking`
- 日志中出现 `openviking: registered context-engine`

说明已经挂载成功。

---

## 你当前这个仓库怎么使用 Key

这个仓库里已经额外准备了两种方式：

1. `templates/ov.conf.doubao.prefilled.local.json`
   - 已经预填了一个实验用 Key
   - 适合你现在这种“先跑通再说”的场景

2. `scripts/21_install_openviking_local_doubao_env.sh`
   - 适合你以后换成正式 Key 时使用
   - 运行前先：
     ```bash
     export VOLCENGINE_API_KEY=你的新Key
     ```
