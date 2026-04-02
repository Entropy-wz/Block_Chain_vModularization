# Agentic Blockchain Sandbox 

<div align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/LLM-Powered-orange.svg" alt="LLM Powered">
  <img src="https://img.shields.io/badge/Simulation-Discrete%20Event-green.svg" alt="Discrete Event">
  <img src="https://img.shields.io/badge/License-MIT-purple.svg" alt="License">
</div>

<br>

**Agentic Blockchain Sandbox** 这是一个基于 **大语言模型 (LLM)** 和 **离散事件模拟 (DES)** 构建的区块链社会学实验沙盘。

与传统的区块链网络模拟器（仅关注延迟、带宽、共识算法）不同，本项目**将矿工建模为具有独特“人格”、“利益诉求”和“心理状态”的 LLM Agent**。它允许你在一个包含**“P2P网络层 + 舆论论坛层 + 攻击治理层”**的多维环境中，观察自私挖矿、社交战（Social Warfare）、网络定向攻击（Jamming）以及集体治理的涌现行为。

---

## 🌟 核心特性 (Key Features)

### 🤖 LLM 驱动的智能矿工
- 每个节点背后由独立的 LLM Prompt 驱动，具备独特的阵营分配（诚实、自私）与性格特征（激进、保守、声誉导向等）。
- 矿工可以感知当前网络的胜率、私有链的长度、竞争对手的压力，自主决定是 **“立刻广播 (Publish)”**、**“囤块隐匿 (Withhold)”** 还是 **“定向物理打击 (Jam Target)”**。

### 🌐 基于泊松分布的 DES P2P 网络
- 高度可调的网络延迟（Latency）与拓扑边缘概率（Edge Probability）。
- 真实的自然孤块（Natural Orphans）模拟与传播冲突检测。

### 🗣️ 论坛舆论与社会动力学 (Tieba/Forum Module)
- 内置一个去中心化的匿名矿工论坛，矿工在出块/收块时可以在论坛发帖造势或互相攻击。
- LLM 实时进行情感分析（Tone Analysis）并对矿工打分，形成网络范围的**公共声誉系统（Reputation System）**。
- 支持基于舆论锁定的“协同攻击”，再现社区分裂与舆论战。

### ⚔️ 网络攻击与治理 (Jamming & Governance)
- 矿工可以通过 `jam_target` 动作对竞争对手发起 DDoS 风格的网络封锁，延缓目标节点的区块传播。
- 集成治理惩罚机制：声誉低落或被检测出严重作恶的节点，会被整个网络发起“社交驱逐（Banned）”。

---

## 📁 架构与目录概览

本沙盘遵循高度模块化的设计，支持从极简纯网络基线测试，到复杂的全功能社会实验无缝切换。

```text
blockchain_sandbox/
├── core/               # 核心层：离散事件引擎、图模型、基础实体 (Block/Node)
├── engine/             # 引擎层：事件调度、策略接口、沙盒主控循环
├── llm/                # LLM 层：异步 API 网关、Prompt 模板、历史上下文管理
├── modules/            # 扩展模块：论坛(Forum)、治理(Governance)、攻击(Jamming)
├── reporting/          # 分析报告层：数据持久化、JSONL日志导出、时序统计
├── social/             # 社交动力学：(遗留支持/可与扩展模块组合)
└── cli/                # 命令行入口
configs/                # 配置文件 (LLM 密钥, Agent 人格设置)
experiments/            # 开箱即用的实验脚本配方 (Recipes)
outputs/                # 生成的区块树图(PNG)、详细实验数据(CSV/JSONL)
docs/                   # 详细的技术原理与模块开发者文档
```

> 💡 **项目文档导航**：
> - **想了解核心机制与代码架构？** 👉 请参阅 [`docs/README_structure.md`](docs/README_structure.md) (模块、离散事件引擎、参数含义)
> - **想调整参数、运行命令行实验？** 👉 请参阅 [`docs/README_engine.md`](docs/README_engine.md) (全部 CLI 参数列表、输出文件判读)

---

## 🚀 快速上手 (Quick Start)

### 1. 环境准备

```bash
git clone https://github.com/Entropy-wz/block_v2.git
cd block_v2
pip install -r requirements.txt
```

### 2. 配置 LLM API (如果需要运行 LLM 模式)

复制配置文件并填入你的 API Key：
在 `configs/llm_provider.yaml` 中配置：
```yaml
provider: openai
model: gpt-4o-mini  # 推荐使用兼顾速度与智能的模型
base_url: https://api.openai.com/v1
api_key: sk-your-api-key-here
```

---

## 🧪 预设实验配方 (Experiment Recipes)

我们内置了多组具有极高对比价值的实验，只需复制命令即可运行，结果会输出至 `outputs/` 目录。

> **参数调整指南**：更多细节参数如延迟、并发度等，请参阅 [`docs/README_engine.md`](docs/README_engine.md)。

### 🟢 实验 1: No-LLM 高延迟诚实基线 (自然孤块率测试)
排除了所有 LLM 和攻击行为，使用纯数学策略验证网络拥堵导致的自然孤块率分布。
```powershell
$env:SANDBOX_TOTAL_STEPS='1000'
$env:SANDBOX_TARGET_MINED_BLOCKS='500'
$env:SANDBOX_NUM_MINERS='40'
$env:SANDBOX_BLOCK_DISCOVERY_CHANCE='0.02' # 高延迟/低并发设置
python -m experiments.run_honest_no_llm
```

### 🟡 实验 2: 自私挖矿策略突袭 (关闭论坛)
6个具备人格的 LLM 矿工中混杂了“自私矿工”，观察在没有社区沟通的情况下，隐藏与截胡（Withholding）如何影响系统公平性。
```powershell
$env:SANDBOX_ENABLE_FORUM='0'
$env:SANDBOX_ENABLE_ATTACK_JAMMING='0'
$env:SANDBOX_BLOCK_DISCOVERY_CHANCE='0.05'
python -m experiments.run_llm_sandbox
```

### 🔴 实验 3: 全量社会战争 (开启论坛 + 攻击 + 治理)
开启完整特性的极限测试。观察矿工如何在 Tieba 论坛带节奏，锁定竞争对手进行 DDoS (`jam_target`)，以及因为作恶被系统降级封杀。
```powershell
$env:SANDBOX_ENABLE_FORUM='1'
$env:SANDBOX_ENABLE_ATTACK_JAMMING='1'
$env:SANDBOX_OUTPUT_ROOT='outputs/social_warfare'
python -m experiments.run_social_warfare
```

---

## 📊 结果分析与可视化

引擎在运行结束后，会自动在 `outputs/` 生成极其丰富的实验数据包：

1. `summary.json`：全量核心指标，包含算力与主链出块份额的相关性 `corr(hash_power, canonical_share)`。
2. `blocks.jsonl` / `forum_posts.jsonl` / `jam_events.jsonl`：详细的追溯日志。
3. `miner_details.csv`：各矿工孤块率、实际收益比例分析表。
4. **区块树图 (PNG)**：直观展现主链与分叉孤块的树状演化结构。

![Tree Example Demo](https://via.placeholder.com/600x300?text=Block+Tree+Visualization+Demo) *(示意位)*

---

## 🤝 贡献与二次开发 (Contributing)

我们非常欢迎对复杂系统、Agentic AI 和区块链交叉领域感兴趣的开发者提交 PR。你可以：
- 添加新的大模型策略 Prompt 变种。
- 引入新的共识机制机制（例如从 PoW 扩展模拟 PoS 罚没机制）。
- 增强前端可视化支持。

开发指南：
- 请优先阅读 [`docs/MODULE_GUIDE.md`](docs/MODULE_GUIDE.md) 了解事件总线与生命周期。
- 添加新模块需实现 `ComponentInterface` 并挂载于 `AgenticSimulation`。

---

## 📜 许可证 (License)

本项目采用 [MIT License](LICENSE) 开源。欢迎在学术研究与探索中使用并引用。