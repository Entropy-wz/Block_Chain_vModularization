# Blockchain Sandbox - 典型实验案例与分析指南

本文档旨在提供针对特定研究场景的**预设实验参数与启动命令**，并详细说明如何利用沙盒生成的各种报表数据对实验结果进行分析比对。

> 另见：`docs/ORPHAN_RATE_ANALYSIS_GUIDE.md` —— 该文档整理了“孤块率归因”三组对照实验的**实际参数、运行结果、输出目录与新人阅读建议**，适合作为快速上手参考。

---

## 🔬 实验组 A：Tokenomics（代币经济学）对自私挖矿的抑制效果测试

**研究目标**：
在“低并发、中等延迟”的弱对抗网络环境中，探究纯粹的“自私挖矿（Selfish Mining）”攻击行为在**有/无**代币电费惩罚的情况下的表现差异。期望观察到在引入 `TokenomicsModule` 后，大模型（矿工）由于面临“孤块率上升导致币价暴跌”以及“电费持续消耗”的双重压力，会在策略上出现退让甚至主动关机（`power_off`）。

### 实验 A-1：自私挖矿突袭（无代币模块）

本组实验模拟了传统无成本发作的分叉攻击。开启了论坛、Jamming 等全量社交手段，但不开启 Tokenomics。

**直接复制运行（PowerShell）：**

```powershell
cd D:\my

# 核心：关闭代币经济学模块
$env:SANDBOX_ENABLE_TOKENOMICS='0'

# 网络参数：中等延迟，低并发，利于观察自私分叉
$env:SANDBOX_MIN_LATENCY='1.5'
$env:SANDBOX_MAX_LATENCY='3.5'
$env:SANDBOX_EDGE_PROB='0.25'
$env:SANDBOX_BLOCK_DISCOVERY_CHANCE='0.05'

# 基础参数：大幅拉长仿真时间，大约产生 50~100 个区块的激烈博弈
$env:SANDBOX_TOTAL_STEPS='1500'
$env:SANDBOX_NUM_MINERS='6'
$env:SANDBOX_NUM_FULL_NODES='12'

# 开启详细日志（可选）：能在终端实时看到大模型的回复与推理
$env:SANDBOX_VERBOSE_LLM_LOG='1'

# 开启舆论与物理攻击
$env:SANDBOX_ENABLE_FORUM='1'
$env:SANDBOX_ENABLE_ATTACK_JAMMING='1'
$env:SANDBOX_AGENT_PROFILE_FILE='D:\my\configs\agent_profiles.toml'

# 输出目录
$env:SANDBOX_OUTPUT_ROOT='D:\my\outputs\exp_a1_no_tokenomics'

python -m experiments.run_llm_sandbox
```

### 实验 A-2：自私挖矿突袭（有代币模块，引入电费与币价）

本组实验与 A-1 参数完全一致，唯一的变量是开启了 `$env:SANDBOX_ENABLE_TOKENOMICS='1'`。

**直接复制运行（PowerShell）：**

```powershell
cd D:\my

# 核心：开启代币经济学模块
$env:SANDBOX_ENABLE_TOKENOMICS='1'

# 网络参数：与 A-1 保持一致
$env:SANDBOX_MIN_LATENCY='1.5'
$env:SANDBOX_MAX_LATENCY='3.5'
$env:SANDBOX_EDGE_PROB='0.25'
$env:SANDBOX_BLOCK_DISCOVERY_CHANCE='0.05'

# 基础参数
$env:SANDBOX_TOTAL_STEPS='1500'
$env:SANDBOX_NUM_MINERS='6'
$env:SANDBOX_NUM_FULL_NODES='12'

# 开启详细日志（可选）
$env:SANDBOX_VERBOSE_LLM_LOG='1'

# 开启舆论与物理攻击
$env:SANDBOX_ENABLE_FORUM='1'
$env:SANDBOX_ENABLE_ATTACK_JAMMING='1'
$env:SANDBOX_AGENT_PROFILE_FILE='D:\my\configs\agent_profiles.toml'

# 输出目录
$env:SANDBOX_OUTPUT_ROOT='D:\my\outputs\exp_a2_with_tokenomics'

python -m experiments.run_llm_sandbox
```

---

## 📈 结果比对与报表分析指南 (Reports Analysis Guide)

实验跑完后，请分别打开 `outputs/exp_a1_no_tokenomics/...` 和 `outputs/exp_a2_with_tokenomics/...` 进行数据比对。

核心要看的报表文件有三个：`summary.json`、`miner_details.csv`、和 `prompt_traces.jsonl`。

### 1. 评估“破坏性”指标 (`summary.json`)

对比两个实验的根目录下的 `reports/summary.json`。重点关注：

- **`orphan_ratio` (总孤块率)**：
  - **A-1（无代币）预期**：较高。自私矿工为了抢夺主链，会毫无顾忌地不断 withholding 并引发重组。
  - **A-2（有代币）预期**：应有下降。因为高孤块率会导致大盘崩盘（Token Price下跌），聪明的大模型可能会顾及长期收益减少分叉。
- **`unpublished_selfish_blocks` (囤积且未释放的自私块数)**：
  - A-2 中该数值可能会显著降低，说明矿工转向保守策略。

### 2. 评估“公平性”与“收益” (`miner_details.csv`)

打开 `reports/miner_details.csv` 文件，重点观察里面标记为自私阵营策略（`strategy="selfish"`）的矿工数据：

- **`canonical_vs_hp_ratio` (实际出块比例与算力的比值)**：
  - 正常情况该值围绕 `1.0` 波动。
  - **A-1**：自私矿工该值可能远大于 `1.0`（通过攻击偷取了他人的份额）。
  - **A-2**：观察自私矿工的这一优势是否被缩减。
- **(如有) Tokenomics 字段：`fiat_balance` 与 `token_balance`**：
  - 看看诚实矿工是否因为频繁被重组而导致 `fiat`（法币/电费）亏空，从而被挤出网络。

### 3. 窥探大模型“心理活动” (`prompt_traces.jsonl`)

这是最有趣的部分。打开 `data/prompt_traces.jsonl`，搜索自私矿工的 `miner_id`。

- 在 **A-2** 实验中，搜索关键词 `economic_action`。你很可能会在它的推理字段 `reason` 中看到如下心理博弈：
  - *"由于目前的孤块率太高导致币价跌至 0.8，我继续发起分叉会导致全盘崩溃，我决定这回合直接广播以稳定市场。"*
  - 或者遇到持续亏损的矿工：*"我的资金已经见底，无法覆盖 Hash Power 的电费开销，被迫选择 `power_off` 关机。"*

### 4. 舆论与社交战分析 (`forum_posts.jsonl`)

虽然这并非本组实验的核心变量，但你可以顺便观察代币模块如何影响社交发言：
- 亏钱的矿工是否会在论坛中发布更多的情绪化攻击帖子 (`social_action: "post_fud"`)？
- 在 A-2 中，由于大家利益高度绑定（一荣俱荣一损俱损），是否会更容易出现 `call_truce`（呼吁停火）的协同行为？

---

## 🛠️ 进阶拓展

你可以根据上述模版，自由组合变量。例如：
- 调大 `$env:SANDBOX_NUM_MINERS='12'` 观察人数增加时，搭便车（Free-rider）效应是否会让币价系统彻底崩盘。
- 将 `$env:SANDBOX_BLOCK_DISCOVERY_CHANCE='0.1'` 改为高并发模式，观察代币经济学是否足以对抗极端的网络环境恶化。
