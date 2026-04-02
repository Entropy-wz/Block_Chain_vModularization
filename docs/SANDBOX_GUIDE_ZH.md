# Blockchain Sandbox (模块化版本) 架构与使用文档

## 1. 系统核心概述

Blockchain Sandbox 是一个通过 **离散事件仿真（Discrete Event Simulation, DES）** 与 **LLM 智能体代理（LLM Agents）** 相结合的区块链网络沙盘模拟工具。它的目标不是完全模拟比特币协议的底层细节，而是提供一个可控、可干预的网络环境，用于研究**出块、传播、分叉以及策略行为（诚实/自私/网络拥塞/社交操纵）**对链结构和节点收益的影响。

**近期重大架构升级：**
引入了 **模块化插件系统 (Module System)** 和 **核心事件总线 (Event Bus)**，将硬编码在引擎中的网络攻击、论坛模块解耦，支持更方便地扩展新玩法和机制。

---

## 2. 核心架构设计

### 2.1 底层引擎架构 (DES + 图论)

- **离散事件循环**: `agentic_simulation.py` 通过优先队列管理时间线。核心事件是 `mine`（泊松分布生成的出块事件）和 `receive`（区块通过图结构传播的到达事件）。
- **图网络拓扑**: `graph_model.py` 维护了一个有向图。网络结构包含 `latency`（延迟）和 `reliability`（可靠性/丢包率）。网络攻击（Jamming）会直接修改局部图边权重。

### 2.2 LLM Agent 决策机制

- 引擎为每一个矿工包装了 `MinerAgent` (`agent.py`)。它通过整合当前网络状态（区块高度、竞争者头部、私有链优势）、自身矿工人格（`MinerPersona`，风险/攻击性/耐心）、以及各插件系统（Modules）提供的增强上下文（如论坛情绪），向 LLM 请求下一步的行动。
- 允许 LLM 自定义返回扩展字段（如 `jam_steps`, `social_action` 等），引擎利用一套宽容的反序列化器 (`llm_backend.py`) 抓取所有这些指令，并封装成 `LLMDecision` 触发相应的策略和事件。
- 如果 LLM 断连、拒绝回答，引擎会使用算法 `fallback` 保证仿真正常继续。

### 2.3 模块化机制 (Modules)

任何外围机制实现 `ISimulationModule` 接口（详见 `core/interfaces.py`）。

- **生命周期钩子**:
  - `setup`: 初始化并订阅全局事件总线。
  - `on_step_start`: 每个逻辑时间步开始时执行维护任务（如解禁节点，恢复网络）。
  - `augment_agent_observation`: 将自定义模块的状态打包成特征发给 LLM。
  - `augment_system_prompt`: 向 LLM 的系统级 Prompt 中注入专门的模块规则。
  - `expected_decision_keys`: 通知解析器应当抓取哪些 JSON 键。
  
- **当前包含的官方模块**:
  1. **ForumModule** (`forum_module.py`): 模拟矿工暗网论坛。LLM可选择发帖吹捧/造谣。如果节点的声誉跌破阈值（默认 -10），会被系统自动物理断网（断绝所有边）。
  2. **NetworkAttackModule** (`network_attack_module.py`): 允许节点发起定向的网络延迟攻击（Jamming），动态成倍拉高目标节点的图边延迟，抑制其区块传播能力。

---

## 3. 支持的实验模式与脚本

### 模式 A: LLM Agent 混合策略仿真 (策略与舆情攻防)
命令: `python experiments/run_social_warfare.py` 或直接调用 `run_llm_sandbox`  
**特点**:
- 需要配置 `llm_provider.yaml` 提供有效的 API Key。
- 激活 Forum 和 Network 模块。
- 重点观测 AI 的动态策略选择和舆情/阵营对抗。

### 模式 B: No-LLM 纯算法基准验证 (大规模公平性基线)
命令: `python experiments/run_honest_no_llm.py`  
**特点**:
- 不需要外部 API。
- 可轻松扩展至几百节点、几千个区块。
- 主要用于统计网络孤块率、网络延迟效率、以及算法收益比率的合理性。

---

## 4. 参数配置与命令行调参

所有参数均可通过环境变量覆盖，也可以直接修改 `configs/` 或对应的 `config.py`。

### 4.1 通用物理与网络参数

- `SANDBOX_TOTAL_STEPS`: 仿真总逻辑时间步长 (默认: 320)。
- `SANDBOX_NUM_MINERS`: 矿工数量。
- `SANDBOX_NUM_FULL_NODES`: 不参与挖矿的纯验证全节点数。
- `SANDBOX_EDGE_PROB`: 生成随机有向图的边概率 (0~1)。越低网络越稀疏，孤块率越高。
- `SANDBOX_MIN_LATENCY` / `SANDBOX_MAX_LATENCY`: 边延迟。
- `SANDBOX_MIN_RELIABILITY` / `SANDBOX_MAX_RELIABILITY`: 边可靠性 (0~1)。
- `SANDBOX_BLOCK_DISCOVERY_CHANCE`: 泊松出块参数 (到达率 $\lambda$)。此值决定了出块的频繁度。

### 4.2 模块化相关参数

- `SANDBOX_ENABLE_FORUM`: (1/0) 启用论坛模块。
- `SANDBOX_AGENT_PROFILE_FILE`: TOML文件，定义矿工人格。
- （未来可通过传参扩充自定义模块）。

### 4.3 报告与可视化参数

- `SANDBOX_SNAPSHOT_INTERVAL_BLOCKS`: 树形快照的时间间隔 (默认: 每20个块)。
- `SANDBOX_VERBOSE_LLM_LOG`: 打开控制台打印的详细 prompt 日志。
- `SANDBOX_OUTPUT_ROOT`: 数据导出根目录。

---

## 5. 快速排错指南

1. **`TypeError: get_rep() missing 1 required positional argument...`**
   - **原因**: 策略引擎尝试从模块请求声誉，但签名不匹配。
   - **修复**: 当前已将 `get_rep` 闭包与 `mid` 参数对齐，该问题在核心框架已解决。

2. **LLM 解析提示字段缺失**
   - `llm_backend.py` 已更新为不严格类型的解析器。只要 LLM 返回了 `action`, `reason` 和其他额外 JSON，模块化接口会自动捕获未知的 `kwargs` 并传入事件总线。

3. **仿真运行时控制台卡顿无输出**
   - 若出现大量的 `queue=xxxx` 不是报错，表示存在巨量被阻塞的区块传播事件。降低节点规模或增加 `SANDBOX_BLOCK_DISCOVERY_CHANCE`（拉长间隔）可缓解。若长时间卡顿可能是由于 `generate_tree_pngs` 在处理深链时画图缓慢。

4. **节点被判定离线**
   - 当矿工在论坛上遭受过量 `post_fud` 导致名誉极低时，`ForumModule` 会调用 `graph.ban_node`。这是预期中的机制。