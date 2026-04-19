# OpenClaw + OpenViking（豆包 + Local Mode）详细教程

这个仓库已经按你的目标整理好了：

- OpenClaw：默认安装 npm 稳定版 `2026.4.14`
- OpenViking：安装 PyPI 版 `0.3.8`
- OpenViking 插件：仓库内 `plugin/` 目录，来自官方 `examples/openclaw-plugin`
- 模型提供方：火山方舟 / 豆包
- 接入方式：**Local Mode**

---

## 一、先看清你要完成什么

你真正要完成的是这 4 件事：

1. 装好 OpenClaw
2. 装好 OpenViking Python runtime
3. 把 OpenViking 插件装进 OpenClaw
4. 把 `plugins.slots.contextEngine` 切到 `openviking`

在 Local Mode 下，**模型、API Key、Embedding/VLM 配置都写在 `~/.openviking/ov.conf`**，不是写在 OpenClaw 的插件配置里。

---

## 二、解压后先做什么

进入仓库根目录：

```bash
cd openclaw-openviking-doubao-local-complete
```

先跑环境检查：

```bash
bash scripts/00_check_requirements.sh
```

你至少需要：

- Python 3.10+
- Node 22.16+（Node 24 更推荐）
- npm
- OpenClaw CLI

---

## 三、如果你还没安装 OpenClaw

先执行：

```bash
bash scripts/10_install_openclaw_stable.sh
```

它会把 OpenClaw 安装到 npm 稳定版 `2026.4.14`。

然后执行：

```bash
bash scripts/11_onboard_openclaw.sh
```

等价于：

```bash
openclaw onboard --install-daemon
```

这个步骤会完成 OpenClaw 的初始化和 daemon 安装。

---

## 四、安装 OpenViking 到 ContextEngine Slot

### 方案 A：直接使用仓库里已经预填好的实验 Key

你已经给了一个实验 Key，所以这个仓库里我已经准备好了预填模板与快捷脚本。

直接运行：

```bash
bash scripts/20_install_openviking_local_doubao_prefilled.sh
```

这个脚本会：

- 创建 `~/.openviking/.venv`
- 安装 `openviking==0.3.8`
- 用豆包模板重写 `~/.openviking/ov.conf`
- 安装仓库里的 `plugin/`
- 把 `plugins.slots.contextEngine` 设置为 `openviking`
- 写入 `plugins.entries.openviking.config.mode=local`
- 重启 OpenClaw gateway

### 方案 B：你自己手工设置环境变量

如果你之后想换 Key，不想再用仓库里预填的那个，执行：

```bash
export VOLCENGINE_API_KEY=你的新Key
bash scripts/21_install_openviking_local_doubao_env.sh
```

---

## 五、安装完成后第一时间检查什么

先看 Slot：

```bash
openclaw config get plugins.slots.contextEngine
```

预期输出：

```bash
openviking
```

再看插件配置：

```bash
openclaw config get plugins.entries.openviking.config
```

再看插件自身是否可见：

```bash
openclaw plugins inspect openviking
```

也可以直接用我给你的校验脚本：

```bash
bash scripts/30_verify.sh
```

---

## 六、日志怎么看

先看路径：

```bash
bash scripts/31_show_log_paths.sh
```

你主要看两处：

### OpenClaw 日志

```bash
openclaw logs --follow
```

成功的关键标志：

- 出现 `openviking: registered context-engine`

### OpenViking 自身日志

```bash
cat ~/.openviking/data/log/openviking.log
```

或者持续看：

```bash
tail -f ~/.openviking/data/log/openviking.log
```

---

## 七、第一次功能验证怎么做

最简单的办法是做一个小型记忆测试。

先运行：

```bash
bash scripts/50_smoke_test.sh
```

然后按它提示做：

```bash
openclaw agent --message "记住：我最喜欢的编辑器是 Neovim。" --thinking low
openclaw agent --message "我最喜欢的编辑器是什么？" --thinking low
```

如果一切正常，你会在日志里看到：

- 会话被写入 OpenViking
- recall / search / find 等检索动作
- 第二轮回答更容易提到 Neovim

---

## 八、关键文件都在哪

### OpenViking 配置

```bash
~/.openviking/ov.conf
```

### OpenViking 虚拟环境

```bash
~/.openviking/.venv
```

### OpenViking 日志

```bash
~/.openviking/data/log/openviking.log
```

### OpenClaw 给插件准备的环境文件

```bash
~/.openclaw/openviking.env
```

---

## 九、你最可能改的两个配置

### 1. 换 API Key

改这里：

```bash
~/.openviking/ov.conf
```

把两个地方的 `api_key` 都改掉：

- `embedding.dense.api_key`
- `vlm.api_key`

改完以后：

```bash
source ~/.openclaw/openviking.env
openclaw gateway restart
```

### 2. 换模型

同样改 `~/.openviking/ov.conf`：

- `embedding.dense.model`
- `vlm.model`

默认我已经按豆包推荐组合写好了：

- Embedding：`doubao-embedding-vision-251215`
- VLM：`doubao-seed-2-0-pro-260215`

---

## 十、如果你想重新来一遍

只清数据，不动配置：

```bash
bash scripts/40_reset_openviking_data.sh
```

如果想重新生成配置，再跑：

```bash
bash scripts/20_install_openviking_local_doubao_prefilled.sh
```

---

## 十一、常见问题

### 1. `plugins.slots.contextEngine` 还是 `legacy`

重新执行安装脚本：

```bash
bash scripts/20_install_openviking_local_doubao_prefilled.sh
```

或者手动设：

```bash
openclaw config set plugins.slots.contextEngine openviking
openclaw gateway restart
```

### 2. 插件装上了，但没有召回记忆

优先检查：

- `~/.openviking/ov.conf` 里的 `api_key`
- `embedding.dense.model`
- `vlm.model`
- `~/.openviking/data/log/openviking.log`

### 3. 我后面充值了，不想继续用这个实验 Key

直接换 `~/.openviking/ov.conf` 里的 Key，然后重启 Gateway。
建议你正式充值以后新建一个新的 API Key 再替换。

---

## 十二、我建议你的实际操作顺序

最稳的顺序就是下面这一套：

```bash
bash scripts/00_check_requirements.sh
bash scripts/10_install_openclaw_stable.sh
bash scripts/11_onboard_openclaw.sh
bash scripts/20_install_openviking_local_doubao_prefilled.sh
bash scripts/30_verify.sh
openclaw logs --follow
```

如果你已经装好 OpenClaw，可以直接从第 4 步开始。
