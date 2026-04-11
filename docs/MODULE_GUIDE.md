# Blockchain Sandbox 模块化使用与开发指南

本文档旨在介绍如何使用和扩展 Blockchain Sandbox 中的**可插拔模块 (Pluggable Modules)**。

在最新的架构中，沙盒被拆分为极简的**事件驱动引擎 (Minimal Kernel)**和一组**独立的功能模块 (Modules)**。通过将不同的模块传入引擎，你可以在不修改核心代码的情况下，赋予沙盒复杂的社交舆情、指标监控、治理惩罚与网络攻击能力。

---

## 1. 如何启用和组合模块

模块的装载通常在实验启动脚本（如 `experiments/run_social_warfare.py` 或 `blockchain_sandbox/cli/run_llm_sandbox.py`）中进行。

你只需要实例化需要的模块，并将它们放入一个列表中，传递给 `AgenticBlockchainSimulation`。

### 代码示例：全量启用所有功能

```python
from blockchain_sandbox.engine.agentic_simulation import AgenticBlockchainSimulation
from blockchain_sandbox.modules.metrics_module import MetricsObserverModule
from blockchain_sandbox.modules.forum_module import ForumModule
from blockchain_sandbox.modules.network_attack_module import NetworkAttackModule
from blockchain_sandbox.modules.governance_module import GovernanceModule

# 1. 准备一个模块列表
modules = []

# 2. 挂载社交与治理模块
forum_mod = ForumModule()
modules.append(forum_mod)

# 治理模块需要查询节点的声誉，因此我们将 forum_mod 的获取声誉函数注入给它
governance_mod = GovernanceModule(
    ban_reputation_threshold=-10.0,
    reputation_provider=forum_mod.forum.reputation_of
)
modules.append(governance_mod)

# 3. 挂载网络攻击模块（允许节点发起 Jamming）
attack_mod = NetworkAttackModule(max_steps_of_jam_effect=6)
modules.append(attack_mod)

# 4. 挂载指标观测模块（负责生成 Window Snapshot 和最终报告指标）
metrics_mod = MetricsObserverModule(snapshot_interval_blocks=10)
modules.append(metrics_mod)

# 5. 将模块列表传递给引擎
sim = AgenticBlockchainSimulation(
    config=sim_cfg,
    # ... 其他参数
    modules=modules  # <--- 注入模块
)

sim.run()
```

---

## 2. 现有模块列表与可调参数汇总

### 📊 1. 指标与监控模块 (`MetricsObserverModule`)
*路径：`blockchain_sandbox/modules/metrics_module.py`*

负责从引擎中独立出所有图表数据抓取和树形结构的构建。
- **可调参数:**
  - `snapshot_interval_blocks` (int, 默认: 10) —— 每挖出多少个区块生成一次时间窗口快照（Snapshot）。如果设置太大，会导致快照生成稀疏；太小则增加计算开销。
  - `snapshot_callback` (Callable) —— 可以在快照生成时传入的回调函数，用于实时在控制台打印 `Window Summary`。

### 🗣️ 2. 社交与舆情模块 (`ForumModule`)
*路径：`blockchain_sandbox/modules/forum_module.py`*

使矿工具备在虚拟 Tieba/Twitter 发帖、互相攻击或平息争端的能力。
- **关联的 LLM 决策输出键:**
  - `social_action`: 行为类型（`none`, `post_fud`, `post_hype`, `call_truce`）。
  - `social_target`: 攻击或发帖的目标节点 ID。
  - `social_tone`: 情绪值 `[-1.0, 1.0]`，负数代表敌意，正数代表友善。
  - `social_content`: 帖子文本内容。
- **使用说明:** 这个模块内部维护了 `ForumState`。如果启用了该模块，它会自动向所有大语言模型矿工的环境观测 (`AgentObservation`) 中注入当前的热门板块和个人声誉，引导 AI 根据舆情做决策。

### ⚔️ 3. 网络攻击模块 (`NetworkAttackModule`)
*路径：`blockchain_sandbox/modules/network_attack_module.py`*

允许节点向底层图网络 `DirectedGraph` 发起干预。
- **可调参数:**
  - `max_steps_of_jam_effect` (int, 默认: 6) —— 限制大语言模型单次阻断攻击（Jamming）所能持续的最长仿真步数。
- **关联的 LLM 决策输出键:**
  - `jam_steps`: LLM 期望阻断持续的步数。
  - `target_miner`: LLM 期望攻击的节点 ID。
- **使用说明:** 当 LLM 决定执行 `action="jam_target"` 时，该模块会暂时成倍放大目标节点（及其邻居）的网络延迟。

### ⚖️ 4. 治理模块 (`GovernanceModule`)
*路径：`blockchain_sandbox/modules/governance_module.py`*

对恶劣行径的节点执行硬性制裁。
- **可调参数:**
  - `ban_reputation_threshold` (float, 默认: -10.0) —— 触发全网封禁的声誉底线。
  - `reputation_provider` (Callable) —— 一个函数指针，由于治理需要知道声誉，而声誉在 `ForumModule` 中，你需要将 `forum_mod.forum.reputation_of` 传给这个参数，以保持两个模块的轻度解耦。
- **使用说明:** 每个 tick 该模块会检查节点声誉，若达标则调用 `graph.ban_node()` 在图拓扑层面上对其进行物理级断网处理，并发送通告事件。

### 💰 5. 代币经济学模块 (`TokenomicsModule`)
*路径：`blockchain_sandbox/modules/tokenomics_module.py`*

模拟区块链底层的经济激励博弈系统。
- **关联的 LLM 决策输出键:**
  - `economic_action`: 经济行为指令（`none`, `power_off`）。
- **使用说明:** 
  - 开启后，矿工每参与一步挖矿都会按其算力（Hash Power）比例消耗 `fiat` (法币/电费)。
  - 当其挖出的块上链时，会获得 `tokens`。而 `tokens` 的法币价格受到全网孤块率的动态影响（网络混乱时币价暴跌）。
  - 大模型可以评估其投入产出比（ROI），当亏本严重时，可以选择主动执行 `power_off` 以关闭算力停止亏损。

### 🖥️ 6. 实时可视化看板模块 (`LiveDashboardModule`)
*路径：`blockchain_sandbox/modules/dashboard_module.py`*

一个完全可插拔的前端后端结合模块。在独立线程挂载 FastAPI 与静态 HTML（Vue3+ECharts），利用 EventBus 推送事件，绝不阻塞底层离散模拟循环。
- **可调参数:**
  - `host` (str, 默认 `"127.0.0.1"`)
  - `port` (int, 默认 `8000`)
- **使用说明:**
  - 加入引擎后，自动提供 `http://127.0.0.1:8000/` 浏览器访问。
  - 此模块**没有**关联的 LLM 决策输出键，也不会往 LLM Prompt 里注入任何规则，它纯粹是个 **Listener**（只读）。
  - 在入口脚本 `experiments/run_live_dashboard.py` 里，你可以通过传参决定在模拟结束后是 `无限期等待指定按键关闭 (exit-key)` 还是 `固定倒计时关闭 (keep-alive)`，为自动化实验与屏幕演示提供完美闭环。


---

## 3. 开发者教程：如何编写一个新模块

所有的模块都必须实现 `ISimulationModule` 接口（定义于 `blockchain_sandbox/core/interfaces.py`）。

以下是一个简单的 **HelloWorld 模块** 例子。假设我们想做一个“空投记录模块”，每当有新块产生，我们就在控制台打印一个欢呼。

```python
from typing import Any, Dict
from blockchain_sandbox.core.interfaces import EventTypes, IEventBus, ISimulationContext, ISimulationModule

class AirdropCheerModule(ISimulationModule):
    def __init__(self):
        self.cheer_count = 0
        self.ctx = None

    def setup(self, ctx: ISimulationContext, bus: IEventBus) -> None:
        """ 模块被挂载时调用，用于保存上下文和订阅事件 """
        self.ctx = ctx
        # 订阅区块挖出事件
        bus.subscribe(EventTypes.BLOCK_MINED, self._on_block_mined)

    def on_step_start(self, ctx: ISimulationContext) -> None:
        """ 每个时间步（Tick）开始时调用，适合做定时检查 """
        pass

    def _on_block_mined(self, payload: Dict[str, Any]) -> None:
        """ 自定义的事件处理逻辑 """
        block = payload.get("block")
        miner_id = payload.get("miner_id")
        self.cheer_count += 1
        print(f"[Airdrop Module] Hooray! {miner_id} mined block {block.block_id}. Total cheers: {self.cheer_count}")

    # ==========================================
    # 下方是 LLM 交互接口（如果你不需要影响 LLM，返回空即可）
    # ==========================================

    def augment_agent_observation(self, miner_id: str, ctx: ISimulationContext) -> Dict[str, Any]:
        """ 将模块的状态注入到 AI 的上下文中 """
        return {
            "total_cheers_so_far": self.cheer_count
        }

    def augment_system_prompt(self, miner_id: str, ctx: ISimulationContext) -> str:
        """ 在大模型的 System Prompt 中添加额外的指导规则 """
        return "If the total_cheers_so_far is greater than 10, you should feel very happy."

    def expected_decision_keys(self) -> Dict[str, str]:
        """ 如果你的模块期望大模型在 JSON 里输出特定的 Key，在这里声明，避免被 Pydantic 过滤 """
        return {}
```

### 事件总线 (EventBus) 支持的信号
当前引擎对外抛出的标准事件类型 (位于 `EventTypes`) 包括：
- `SIMULATION_START`: 模拟开始。
- `SIMULATION_END`: 模拟结束。
- `BLOCK_MINED`: 节点挖出了一个新块。
- `BLOCK_RECEIVED`: 节点从网络中接收到了一个块。
- `AGENT_DECISION_MADE`: 大模型节点刚刚做出了一个决策（包含原始决策和归一化后的决策）。
- `PRIVATE_CHAIN_PUBLISHED`: 自私矿工向全网释放了一串私有块。
- `NODE_BANNED`: 有节点被执行了封禁断网（通常由治理模块发出）。

通过订阅这些事件，你可以任意扩展沙盒的统计、攻击、干预与可视化能力。

---

## 7. Selfish Mining Strategy Module（新增）

自私挖矿能力现已解耦为独立策略模块层，用于支持“策略可插拔”和“LLM/no-LLM 共用”。

### 模块目标

- 把固定自私逻辑从主流程中抽离。
- 通过策略名切换行为，不修改主引擎循环。
- 让 LLM 链和 no-LLM 自私链复用同一策略执行层。

### 当前内置策略

- `classic`
- `stubborn`
- `social`

### 统一参数

- `SANDBOX_SELFISH_STRATEGY=classic|stubborn|social`

适用入口：

- `python -m experiments.run_llm_sandbox`
- `python -m experiments.run_selfish_no_llm`

### 共用方式

1. LLM链：先执行策略默认动作，再允许LLM在白名单内覆盖；越界覆盖自动回退默认动作。  
2. no-LLM自私链：直接执行策略默认动作；`classic` 保留理论对照，其他策略用于仿真对比。

### 扩展新策略（约定）

新增策略只需：

1. 实现统一输入/输出接口  
2. 在策略注册表注册名字  
3. 通过 `SANDBOX_SELFISH_STRATEGY` 选择

这样不需要改主循环。
