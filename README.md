# Agentic Blockchain Sandbox 

<div align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python Version">
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
- **(New!) 智能路由与短路拦截机制 (DecisionRouter)**：内建智能冷却与短路模块。当处于无事发生的平稳期或落后无竞争时，自动进行 Fallback 兜底响应；而在发生分叉、声誉受损、受到网络攻击时立刻唤醒大模型。在保证沙盘复杂性的同时，降低至少 60% 的无意义 Token API 消耗与等待时间！

### 🌐 基于泊松分布的 DES P2P 网络
- 高度可调的网络延迟（Latency）与拓扑连接算法 (支持 `Random`、`Barabasi-Albert`、`Watts-Strogatz` 小世界网络 及 `Core-Periphery` 核心边缘网络，支持模块化 Registry 扩展)。
- **(New!) 规模分级缓存与批缓冲机制**：内建 `GraphAnalyticsCache` 以 O(1) 或 O(k) 时间复杂度应对千节点级别图分析；引擎内置 Hub 节点扩散的 $\delta t$ 微小偏移量分批，完美平滑 heapq 并发风暴。
- 真实的自然孤块（Natural Orphans）模拟与传播冲突检测。

### 🗣️ 论坛舆论与社会动力学 (Tieba/Forum Module)
- 内置一个去中心化的匿名矿工论坛，矿工在出块/收块时可以在论坛发帖造势或互相攻击。
- LLM 实时进行情感分析（Tone Analysis）并对矿工打分，形成网络范围的**公共声誉系统（Reputation System）**。
- 支持基于舆论锁定的“协同攻击”，再现社区分裂与舆论战。

### ⚔️ 网络攻击与治理 (Jamming & Governance)
- 矿工可以通过 `jam_target` 动作对竞争对手发起 DDoS 风格的网络封锁，延缓目标节点的区块传播。
- 集成治理惩罚机制：声誉低落或被检测出严重作恶的节点，会被整个网络发起“社交驱逐（Banned）”。

### 📊 Live Web Dashboard (实时可视化与数据总览)
- 本项目包含一个支持实时绘图与监控的 **可选模块** `LiveDashboardModule`，可在终端和网页端提供动态交互反馈。
- 该 Dashboard 作为标准 `ISimulationModule` 设计，完全解耦。你可以通过在运行 `run_live_dashboard.py` 时添加 `--no-dashboard` 参数来禁用它，退回到无后端纯命令行模式。
- 当仿真运行结束后，仪表盘会在新标签页自动弹出 `/summary` 页面，展示可视化的最终统计指标（如孤块率、各矿工份额分布、封禁情况）。主看板页保留原样以供对照，并可以通过页面新增的返回/关闭按钮进行灵活切换。

### 🚀 真实还原的分叉(Fork)与“同高度竞争块”现象
- 如果你观察到“两条链上都有 H:5 的节点”，请注意：图上节点标签的 `H:5` 代表**“区块高度为 5”**，而非“节点名称 H5”。
- 在本沙盘中，当多个矿工因为网络延迟（Latency）几乎同时基于高度 4 挖出区块时，会自然出现**两个 height=5 的块分属不同分支的合法现象**。这不是 Bug，而是 P2P 网络异步传播的真实常态。

### ⚔️ 网络社会学攻击与“强者吸火”机制 (Target Concentration)
- 如果你观察到“某个无辜的节点（如 M2 / M5）承担了全网绝大部分攻击”，这往往是因为 **LLM 攻击策略的收敛效应**。
- `NetworkAttackModule` 提供的观测数据中，会把全网最强（算力高）或声望最稳的“头部诚实节点”暴露给大模型。处于下风的自私节点为了消除领先者的优势，会**自主涌现出“抱团打击同一个最强目标”的行为**。

---

## 📁 架构与目录概览

本沙盘遵循高度模块化的设计，支持从极简纯网络基线测试，到复杂的全功能社会实验无缝切换。

```text
blockchain_sandbox/
├── core/               # 核心层：离散事件引擎、图模型、基础实体 (Block/Node)
├── engine/             # 引擎层：事件调度、策略接口、沙盒主控循环
├── llm/                # LLM 层：独立的异步调度器 (Scheduler)、API 网关、Prompt 模板
├── modules/            # 扩展模块：论坛(Forum)、治理(Governance)、攻击(Jamming)
├── reporting/          # 分析报告层：数据持久化、调度性能指标、JSONL日志导出、时序统计
├── social/             # 社交动力学：(遗留支持/可与扩展模块组合)
└── cli/                # 命令行入口
configs/                # 配置文件 (LLM 密钥, Agent 人格设置)
experiments/            # 开箱即用的实验脚本配方 (Recipes)
outputs/                # 生成的区块树图(PNG)、详细实验数据(CSV/JSONL)
docs/                   # 详细的技术原理与模块开发者文档
```

> 💡 **项目文档导航**：
> - **想了解核心机制与代码架构？** 👉 请参阅 [`docs/README_structure.md`](docs/README_structure.md) (离散事件引擎、模块交互机制与参数设计)
> - **想调整参数、运行命令行实验？** 👉 请参阅 [`docs/README_engine.md`](docs/README_engine.md) (CLI 参数列表、预设实验配方与输出说明)
> - **想进行二次开发或编写新模块？** 👉 请参阅 [`docs/MODULE_GUIDE.md`](docs/MODULE_GUIDE.md) (EventBus 事件订阅与 Pluggable Module 开发指南)
> - **想了解如何运行与编写回归测试？** 👉 请参阅 [`docs/TESTING_GUIDE.md`](docs/TESTING_GUIDE.md) (单元测试模块说明与防崩溃开发指南)

---

## 🧪 单元测试 (Testing)

我们使用 `pytest` 作为单元测试框架，目前的测试用例覆盖了核心模块、大模型解析器、数学概率模型等易损环节。测试代码均放置于 `tests/` 目录下。

### 运行测试

请确保你已经安装了 `pytest`（可以通过 `pip install pytest` 或直接通过 `requirements.txt` 安装）。

```bash
# 运行全部测试
python -m pytest tests/

# 运行特定模块的测试
python -m pytest tests/core/
python -m pytest tests/engine/
python -m pytest tests/llm/
python -m pytest tests/modules/
```

---

## 🖥️ Live Web Dashboard (实时可视化看板)

沙盘内置了一个 **可插拔的前端可视化看板 (Vue3 + ECharts)**，支持实时渲染拓扑结构、算力比例、阻塞攻击动效与事件流！

![Live Dashboard Demo](https://via.placeholder.com/600x300?text=Live+Dashboard+Preview) *(示意图)*

### 启动带大屏的仿真
你可以直接使用以下命令启动全量可视化环境（运行后自动在 `http://127.0.0.1:8000/` 或 `/dashboard` 提供服务，无需手动双击文件）：

```bash
python -m experiments.run_live_dashboard
```

**命令行控制参数：**
- `--keep-alive <秒数>`: 仿真跑完后，自动保持服务并于指定秒数后退出（用于自动化脚本或无头展示）。不论设置多少秒，期间随时可在终端按 `--exit-key` (默认 `q`) 提前优雅关闭。
- `--exit-key <按键>`: 默认 `q`，在仿真结束后，按该键可优雅关闭后台服务并断开浏览器连接。
- `--no-dashboard`: 若想以纯净无后端模式跑这个预设实验，可以加上该参数跳过 Dashboard。
- `--host` / `--port`: 自定义 Web 挂载服务的地址，默认为 `127.0.0.1:8000`。

---

## 🚀 5 分钟快速上手 (5-Minute Quickstart)

我们提供了“开箱即用”的体验。**你不需要立刻配置大模型 API Key 即可看到沙盘的震撼效果。**

### Step 1: 环境准备

```bash
git clone https://github.com/Entropy-wz/Block_Chain_vModularization.git
cd Block_Chain_vModularization
pip install -r requirements.txt
```

### Step 2: 跑通你的第一场实验（无需 API Key，2秒出图！）

我们内置了一个不需要大模型即可运行的“纯数学基线验证脚本”，专门用来测试拥堵网络下的自然孤块与分叉。
执行以下命令：

```bash
python -m experiments.run_honest_no_llm
```

等待大约 2-3 秒，引擎会处理完毕。现在打开 `outputs/default/` 目录中最新生成的文件夹，你会获得你的**第一份沙盒报告**：
- 📊 **数据统计** (`reports/summary.json`)：查看全网节点的孤块率、实际算力收益占比。
- 🌳 **可视化分叉树** (`visualizations/full_tree.png`)：你将直观地看到一条主链（蓝色），以及因为网络延迟产生的各种孤立分叉（红色/灰色区块）。

如果你想做“理论自私挖矿”快速验证（同样无需 API Key），可以直接运行：

```bash
python -m experiments.run_selfish_no_llm
```

该模式会在同一份报告里同时给出“仿真收益占比”和“理论收益占比（Eyal & Sirer）”。

### Step 3: 进阶体验 - 注入灵魂（开启多智能体社会）

当你准备好体验拥有独立人格的矿工、Tieba 论坛舆论战以及自私网络攻击时，配置你的大模型 API。
在 `configs/llm_provider.yaml` 中修改为你自己的配置（推荐使用低成本且快速的模型如 `gpt-4o-mini` 或 `claude-3-haiku`）：

```yaml
provider: openai
model: gpt-4o-mini
base_url: https://api.openai.com/v1
api_key: sk-your-api-key-here
```
配置完成后，尝试运行下方的“全量社会战争实验”。

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

### 🟣 实验 4: Tokenomics 代币经济博弈对抗
观察在大模型面临算力开销、市场币价崩塌时，是否会减缓其恶意的自私分叉行为。
> **详细参数设计与结果分析方法请参阅**：[docs/EXPERIMENT_CASES.md](docs/EXPERIMENT_CASES.md)

### 🔵 实验 5: No-LLM 自私挖矿理论对照 (Eyal & Sirer)
不依赖大模型，直接使用 `alpha`（自私算力占比）和 `gamma`（同高竞争优势）进行经典自私挖矿仿真，并自动输出理论对照。
```powershell
$env:SANDBOX_SELFISH_ALPHA='0.35'
$env:SANDBOX_SELFISH_GAMMA='0.5'
$env:SANDBOX_SELFISH_STRATEGY='classic' # classic / stubborn / social
$env:SANDBOX_SELFISH_TARGET_BLOCKS='5000'
python -m experiments.run_selfish_no_llm
```
输出会包含以下核心字段：
- `selfish_alpha`
- `selfish_gamma`
- `simulated_selfish_share`
- `theoretical_selfish_share`
- `theory_gap_abs`
- `theory_match`

> **三组预设配方与分析方法请参阅**：[docs/SELFISH_NO_LLM_GUIDE.md](docs/SELFISH_NO_LLM_GUIDE.md)

---

## 📊 结果分析与可视化

引擎在运行结束后（包含自动资源 `cleanup` 的保障阶段结束时），会自动在 `outputs/` 生成极其丰富的实验数据包：

1. `summary.json`：全量核心指标，包含算力与主链出块份额的相关性 `corr(hash_power, canonical_share)`。
2. `blocks.jsonl` / `forum_posts.jsonl` / `jam_events.jsonl`：详细的追溯日志。
3. `miner_details.csv`：各矿工孤块率、实际收益比例分析表。
4. `scheduler_metrics.json`：LLM 调度器的并发性能与延迟统计。
5. **区块树图 (PNG)**：直观展现主链与分叉孤块的树状演化结构。

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
