# Blockchain Sandbox 项目移交说明（结构与算法）

> 面向接手同学的技术说明。本文重点解释“项目结构 + 核心算法设计 + 当前实现边界”。

## 1. 项目目标

本项目是一个区块链仿真沙盒，目标不是复刻真实比特币客户端，而是提供可控实验环境，用于：

1. 研究 PoW 网络下的出块-传播-分叉行为。
2. 研究策略行为（诚实/自私/动态策略）对收益、孤块、链结构的影响。
3. 提供可导出、可复现实验数据（CSV/JSON/PNG）。

当前已支持两种运行模式：

1. `LLM Agent` 模式（事件触发决策，支持人格和舆情上下文）。
2. `No-LLM Honest` 基线模式（纯概率仿真，适合高规模 ratio 公平性验证）。

---

## 2. 目录结构（核心）

```text
D:\my
├─ blockchain_sandbox
│  ├─ core
│  │  ├─ config.py
│  │  ├─ entities.py
│  │  ├─ graph_model.py
│  │  ├─ persona.py
│  │  ├─ event_bus.py        <-- 引入事件总线解耦
│  │  ├─ interfaces.py       <-- 模块化接口定义
│  │  └─ agent_profile.py
│  ├─ llm
│  │  ├─ llm_backend.py
│  │  └─ agent.py
│  ├─ modules                 <-- 可插拔的扩展模块
│  │  ├─ forum_module.py      <-- 论坛与舆情
│  │  ├─ governance_module.py <-- 治理与封禁机制
│  │  ├─ network_attack_module.py <-- 网络打击/阻塞机制
│  │  └─ metrics_module.py    <-- 监控指标及快照计算
│  ├─ engine
│  │  ├─ agentic_simulation.py <-- 基于微内核与事件的主循环
│  │  ├─ mining_strategy.py
│  │  ├─ simulation.py
│  │  └─ strategies.py
│  ├─ reporting
│  │  ├─ agentic_metrics.py
│  │  ├─ persistence.py
│  │  └─ tree_visualization.py
│  └─ cli
│     ├─ run_llm_sandbox.py
│     └─ provider_config.py
├─ experiments
│  ├─ run_llm_sandbox.py
│  ├─ run_mvp.py
│  ├─ run_honest_no_llm.py
│  └─ run_social_warfare.py    <-- 全量特性的社交战争启动脚本
├─ configs
│  ├─ llm_provider.yaml
│  ├─ agent_profiles.toml
│  └─ agent_profiles_honest_only.toml
└─ outputs
```

---

## 3. 核心数据结构

### 3.1 区块与节点

文件：`blockchain_sandbox/core/entities.py`

1. `Block`
- `block_id`, `parent_id`, `height`, `miner_id`, `created_at_step`

2. `Node`
- `is_miner`, `hash_power`, `known_blocks`, `local_head_id`
- `observe_block(...)`：接收新区块后是否切换本地链头

### 3.2 网络图（图论基础）

文件：`blockchain_sandbox/core/graph_model.py`

1. 有向图 `DirectedGraph`
- 边 `Edge(src,dst,latency,reliability)`

2. 图算法用途
- `shortest_path_latencies`：估计传播优势（如 gamma）。
- `avg_shortest_latency`：网络效率指标。
- `apply_latency_multiplier`：模拟网络干扰/拥塞。

---

## 4. 时间与出块算法（DES + 泊松）

### 4.1 时间机制

当前主引擎为离散事件仿真（DES），而不是逐 step 全员轮询。

事件队列元素形态：
`(time, seq, kind, arg1, arg2, hops)`

1. `kind=mine`：全网下一次挖矿事件
2. `kind=receive`：区块传播到某节点的接收事件

### 4.2 出块机制

使用指数分布采样块间隔（泊松过程）：

1. 采样下一次出块时间间隔 `delta ~ Exp(lambda)`
2. 以算力占比加权抽样胜出矿工
3. 生成新区块并进入传播流程

其中 `lambda` 对应参数 `SANDBOX_BLOCK_DISCOVERY_CHANCE`（在 DES 中可理解为逻辑时间到达率）。

---

## 5. 策略接口与矿工行为

文件：`blockchain_sandbox/engine/mining_strategy.py`

统一策略钩子：

1. `on_block_mined(...)`
2. `on_block_received(...)`

当前实现：

1. `HonestMiningStrategy`
- 挖到块默认发布
- 接收到块后可选择是否 rebroadcast

2. `SelfishMiningStrategy`
- 维护私有链发布节奏（基础状态逻辑）

> 说明：为了公平性基线实验，诚实矿工在引擎内有行为约束，避免 LLM 输出对抗行为。

---

## 6. LLM Agent 设计

### 6.1 观测与 Prompt

文件：`blockchain_sandbox/llm/agent.py`

`AgentObservation` 包含：

1. 链状态：本地高度、竞争者头部、高度压力等
2. 人格：风险偏好、攻击性、耐心、社交性、投资风格
3. 舆情（通过模块注入）：全局情绪、个人 feed、声誉
4. 事件上下文：`event_kind`, `trigger_block_id`

LLM 返回 `LLMDecision`，再经过引擎归一化（honest/selfish 约束）。

### 6.2 稳定性机制

文件：`blockchain_sandbox/engine/agentic_simulation.py`

1. 决策失败重试（3次，退避）
2. 连续失败自动 fallback（不中断整场实验）
3. trace 中标记 `fallback` 和 `effective_decision`

---

## 7. 模块化插件架构（Modules）与微内核（Minimal Kernel）

项目在最新的演进中，将引擎核心（Kernel）与上层复杂功能（Modules）进行了彻底解耦，形成了“微内核 + 插件式模块”的设计理念。所有的非核心逻辑（如舆情、攻击、统计、治理）均不再硬编码到主引擎。

### 7.1 主引擎核心（Minimal Kernel）
文件：`blockchain_sandbox/engine/agentic_simulation.py`

主引擎目前只保留了最原始的诚实链功能：
1. **时间推进 (DES)**: 处理事件队列的时间流逝。
2. **区块机制**: 泊松出块、诚实链共识规则。
3. **P2P 网络流转**: 最短路径延迟计算与区块的节点间广播。
4. **事件总线 (EventBus)**: 向各模块广播 `SIMULATION_START`, `BLOCK_MINED`, `BLOCK_RECEIVED`, `AGENT_DECISION_MADE` 等生命周期事件。

### 7.2 可插拔扩展模块（Pluggable Modules）
这些模块放置在 `blockchain_sandbox/modules/` 目录下。均实现了 `ISimulationModule` 接口，它们通过订阅主引擎的事件执行逻辑，并通过 `augment_agent_observation`（向 AI 注入观测）或 `augment_system_prompt`（给 AI 添加系统规则）与大语言模型交互。

分类如下：

#### A. 社交与舆情模块 (`ForumModule`)
文件：`blockchain_sandbox/modules/forum_module.py`
- **定位**: 模拟链下社区（Tieba/Twitter）的情绪传播与声誉累计。
- **机制**: 监听 `AGENT_DECISION_MADE`，解析 LLM 决策输出的发帖意图（如 `post_fud`, `post_hype`, `call_truce`），并将当前全网舆情热点、情绪分布（Feed）作为 Context 反推给对应节点的大模型。

#### B. 网络攻击与对抗模块 (`NetworkAttackModule`)
文件：`blockchain_sandbox/modules/network_attack_module.py`
- **定位**: 处理直接干预底层图网络拓扑与通信质量的物理/协议级攻击。
- **机制**: 监听 AI 决策，如果大模型请求发动针对特定节点的 Jamming（网络阻断），该模块会调用底层 `DirectedGraph` 的修改接口，在指定时间窗口内成倍增加目标节点的 P2P 传播延迟（Latency）。

#### C. 治理模块 (`GovernanceModule`)
文件：`blockchain_sandbox/modules/governance_module.py`
- **定位**: 基于节点链下行为进行链上惩罚或物理隔离。
- **机制**: 依赖 `ForumModule` 计算的声誉分，当声誉分数跌破极低阈值（如 -10.0），触发治理共识，物理性切断该节点与其他节点的 P2P 连接（断网处理），并通过事件总线通告全网。

#### D. 指标与监控模块 (`MetricsObserverModule`)
文件：`blockchain_sandbox/modules/metrics_module.py`
- **定位**: 代替旧版主引擎中杂乱的统计收集代码。
- **机制**: 监听出块事件，自动截取时间窗口数据（BlockWindowSnapshot），计算诸如分叉深度、节点孤块率、Gamma（传播优势）及全局网络效率等统计指标。

---

## 8. 报告与导出

### 8.1 文本报告

文件：`blockchain_sandbox/reporting/agentic_metrics.py`

包含：

1. 全局链指标（孤块率、高度、网络效率）
2. 矿工明细（hash power、mined、canonical、orphans、ratio）
3. 奖励公平性指标（corr / MAE）
4. LLM稳定性指标（fallback率）

### 8.2 导出产物

文件：`blockchain_sandbox/reporting/persistence.py`

输出按目录结构进行存放，形如 `outputs/default/YYYY-MM-DD/run_HHMMSS/`，包含 `data/`，`reports/`，`visualizations/` 等层级。
典型输出：
1. `reports/summary.json`
2. `reports/window_snapshots.csv`
3. `reports/miner_details.csv`
4. `data/blocks.jsonl`
5. `data/forum_posts.jsonl`
6. `data/private_events.jsonl`
7. `data/prompt_traces.jsonl`（可选）
8. `visualizations/full_tree.png` + `window_XX_tree.png`

---

## 9. No-LLM 基线脚本（重点）

文件：`experiments/run_honest_no_llm.py`

用途：

1. 不依赖外部 LLM API
2. 支持大规模矿工和大量区块（如 100矿工、5000块）
3. 适用于验证 `ratio` 是否围绕 1

注意：

1. 该脚本也会自动导出树图 PNG
2. 已修复长链绘图递归深度问题（改为非递归遍历）

---

## 10. 已知边界与接手建议

1. `queue` 是事件队列长度，值大不一定异常，表示未来传播事件多。
2. 如果只做公平性验证，优先使用 No-LLM 模式。
3. 如果研究“策略与舆情耦合”，使用 LLM 模式并关注 fallback 比率。
4. 当前 CLI 主要基于环境变量，实验参数组合多时可读性一般。
5. 部分图网络配置（如 edge probability / latency / reliability）仍是“全局同分布”，对异构网络现实性有限。

---

## 11. 一句话总结

当前项目已经形成“图网络传播 + 泊松出块 + 事件总线驱动多模块协同 + 可复现实验导出”的完整闭环；  
基线验证建议走 `run_honest_no_llm.py`，复杂行为研究再通过配置组合不同模块开启 LLM Agent 模式。
