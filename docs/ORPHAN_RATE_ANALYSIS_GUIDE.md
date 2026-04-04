# Blockchain Sandbox - 孤块率归因与对抗消融实验指南

本文档记录了一组针对“为什么沙盒中孤块率异常偏高”的归因对照实验。本实验旨在帮助新接手此项目的人员理解：**系统中的高孤块率（高达20%~40%）并非由于基础的P2P物理网络延迟引起，而是由于LLM驱动的智能体采用“自私挖矿(Selfish Mining)”与“网络阻断(Jamming)”等对抗策略导致的。**

通过执行以下三组由简入繁的对照实验，你可以非常直观地观察到这一结论。

---

## ✅ 本次已落盘的实际运行结果速查表

| 实验 | 运行模式 | 关键参数 | 孤块数 | 孤块率 | 产物目录 |
|---|---|---|---:|---:|---|
| A | No-LLM / 纯诚实 | `BA m=4, reliability=1.0, max_hops=15` | 1 | 0.83% | `outputs/expA_pure_baseline/run_no_llm_20260404_014408/` |
| B | No-LLM / 纯诚实 | `BA m=2, reliability=0.85~0.98, max_hops=6` | 1 | 0.83% | `outputs/expB_physical_constraints/run_no_llm_20260404_014432/` |
| C | LLM + Forum + Jamming + Tokenomics | `BA m=2, reliability=0.85~0.98, max_hops=6` | 34 | 28.33% | `outputs/expC_llm_social_warfare/default/2026-04-04/run_014637/` |

> 新人建议：先看 A，再看 B，最后看 C，并对比各自目录中的 `full_tree.png`、`summary.json` / `reports/summary.json`、`miner_details.csv` / `reports/miner_details.csv`。

---

## 🔬 实验矩阵概览

我们固定了全网总算力节点数（15个矿工，30个全节点，共120个出块目标，使用BA网络拓扑），逐步引入物理网络限制和AI对抗策略。

### 【实验 A】 绝对纯净基线 (纯诚实算法 + 0延迟 + 完美连通)
**核心假设**：在没有任何物理阻碍与恶意节点的完美比特币网络中，孤块率应当趋近于 0。

**可复现命令**：
```powershell
cd D:\my

$env:SANDBOX_TOTAL_STEPS='3500'
$env:SANDBOX_TARGET_MINED_BLOCKS='120'
$env:SANDBOX_NUM_MINERS='15'
$env:SANDBOX_NUM_FULL_NODES='30'
$env:SANDBOX_TOPOLOGY_TYPE='barabasi_albert'
$env:SANDBOX_TOPOLOGY_BA_M='4' # 高连通度

# 物理网络：完美无瑕
$env:SANDBOX_MIN_LATENCY='0.0'
$env:SANDBOX_MAX_LATENCY='0.01'
$env:SANDBOX_MIN_RELIABILITY='1.0' # 不丢包
$env:SANDBOX_MAX_RELIABILITY='1.0'
$env:SANDBOX_MAX_HOPS='15' # 全网穿透

$env:SANDBOX_BLOCK_DISCOVERY_CHANCE='0.035'

# 关闭所有对抗与LLM策略，使用纯算法诚实节点
$env:SANDBOX_ENABLE_FORUM='0'
$env:SANDBOX_ENABLE_ATTACK_JAMMING='0'
$env:SANDBOX_ENABLE_TOKENOMICS='0'
$env:SANDBOX_OUTPUT_ROOT='outputs\expA_pure_baseline'

python -m experiments.run_honest_no_llm
```
**实验结果**：
- 孤块数：1 个
- **孤块率：0.83%**
- **结论**：完美符合真实比特币网络的预期表现。算力份额与出块份额呈现出极高的公平线性关系（MAE仅 0.0145）。通过查看 `outputs\expA_pure_baseline\...\full_tree.png`，你会看到一条几乎没有分叉的直线。

---

### 【实验 B】 物理网络约束 (引入轻微丢包与跳数限制)
**核心假设**：测试真实的 P2P 网络物理限制（如少量丢包和跳数限制导致的传播不全）是否是导致孤块率暴增的主要原因。

**可复现命令**：
```powershell
cd D:\my

$env:SANDBOX_TOTAL_STEPS='3500'
$env:SANDBOX_TARGET_MINED_BLOCKS='120'
$env:SANDBOX_NUM_MINERS='15'
$env:SANDBOX_NUM_FULL_NODES='30'
$env:SANDBOX_TOPOLOGY_TYPE='barabasi_albert'
$env:SANDBOX_TOPOLOGY_BA_M='2' # 降低连通度

# 物理网络：引入真实限制
$env:SANDBOX_MIN_LATENCY='0.0'
$env:SANDBOX_MAX_LATENCY='0.01'
$env:SANDBOX_MIN_RELIABILITY='0.85' # 15% 丢包率
$env:SANDBOX_MAX_RELIABILITY='0.98'
$env:SANDBOX_MAX_HOPS='6' # 限制传播跳数

$env:SANDBOX_BLOCK_DISCOVERY_CHANCE='0.035'

# 依然保持纯算法诚实节点
$env:SANDBOX_ENABLE_FORUM='0'
$env:SANDBOX_ENABLE_ATTACK_JAMMING='0'
$env:SANDBOX_ENABLE_TOKENOMICS='0'
$env:SANDBOX_OUTPUT_ROOT='outputs\expB_physical_constraints'

python -m experiments.run_honest_no_llm
```
**实验结果**：
- 孤块数：1 个
- **孤块率：0.83%**
- **结论非常反直觉但合理**：说明在 `m=2` 这种带有跳数限制和 15% 丢包率的环境下，因为诚实节点存在P2P重传机制，依然几乎不会造出孤块！这证明：**单纯的物理网络劣质，不足以引爆高达 30% 甚至 40% 的孤块率。**

---

### 【实验 C】 Agentic 社会博弈网络 (大模型驱动 + 自私挖矿 + Jam网络攻击)
**核心假设**：高孤块率的核心原因，是 LLM 智能体采用“自私挖矿扣块”与“DDos 断网攻击阻断竞争对手”等“尔虞我诈”的社会博弈行为导致的。

**可复现命令**：
```powershell
cd D:\my

$env:SANDBOX_TOTAL_STEPS='3500'
$env:SANDBOX_TARGET_MINED_BLOCKS='120'
$env:SANDBOX_NUM_MINERS='15'
$env:SANDBOX_NUM_FULL_NODES='30'
$env:SANDBOX_TOPOLOGY_TYPE='barabasi_albert'
$env:SANDBOX_TOPOLOGY_BA_M='2'

$env:SANDBOX_MIN_LATENCY='0.0'
$env:SANDBOX_MAX_LATENCY='0.01'
$env:SANDBOX_MIN_RELIABILITY='0.85'
$env:SANDBOX_MAX_RELIABILITY='0.98'
$env:SANDBOX_MAX_HOPS='6'
$env:SANDBOX_BLOCK_DISCOVERY_CHANCE='0.035'

# 开启 LLM Agent 及全量对抗博弈模块
$env:SANDBOX_ENABLE_FORUM='1'
$env:SANDBOX_ENABLE_ATTACK_JAMMING='1'
$env:SANDBOX_ENABLE_TOKENOMICS='1'
$env:SANDBOX_LLM_MAX_WORKERS='2'

$env:SANDBOX_OUTPUT_ROOT='outputs\expC_llm_social_warfare'

python -m experiments.run_llm_sandbox
```
**实验结果**：
- 本次实际运行孤块数：34 个
- **本次实际运行孤块率：28.33%**
- **结论**：结果真相大白。高孤块率并非由于代码Bug或网络差，而是**Agentic 社会达尔文对抗网络**的必然结果。通过检查 `outputs/expC_llm_social_warfare/default/2026-04-04/run_014637/` 下的数据，你会发现部分节点疯狂执行 `jam_target`（断掉别人网线）和 `publish_private`（扣块截胡）。这是社会工程与算力攻击的综合体现。

---

## 📊 如何阅读结论

对于后续开发和测试的新人：
1. **如果你想验证共识算法和拓扑结构的纯数学物理特性**：请使用 `experiments.run_honest_no_llm`，它不受LLM幻觉和自私策略干扰，能够准确评估P2P底层逻辑。
2. **正常比特币网络的孤块率极低**：如果你的实验没有开启 `Selfish Mining`，孤块率却飙高，那请检查是否是 `MIN_LATENCY` 被设置成了十几秒这种极其夸张的不合理数值。
3. **分叉树的可视化**：请始终利用每组实验输出目录中的 `full_tree.png`，它能让你在一秒钟内感受到“纯洁的数学链”与“充满心机的AI树”之间的震撼对比。