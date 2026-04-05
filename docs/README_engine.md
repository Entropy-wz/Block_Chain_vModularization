# Blockchain Sandbox 引擎使用手册（参数与命令）

> 本文是“可执行操作手册”。接手人只看这份也能跑通。

## 1. 运行模式

支持两种模式：

1. `LLM Agent` 模式  
命令：`python -m experiments.run_llm_sandbox`  
或 `python -m experiments.run_social_warfare`（启用了所有社交与攻击特性的预设脚本）

2. `No-LLM Honest` 模式（推荐做 ratio 基线）  
命令：`python -m experiments.run_honest_no_llm`

---

## 2. 快速启动

## 2.1 LLM Agent 模式（有外部 API）

```powershell
cd D:\my
$env:SANDBOX_LLM_CONFIG_FILE='D:\my\configs\llm_provider.yaml'
$env:SANDBOX_AGENT_PROFILE_FILE='D:\my\configs\agent_profiles.toml'
python -m experiments.run_llm_sandbox
```

## 2.2 No-LLM 模式（无 API，速度快）

```powershell
cd D:\my
python -m experiments.run_honest_no_llm
```

## 2.3 Live Dashboard 快速模式（新标签页 Summary + 可随时按键退出）

```powershell
cd D:\my
python -m experiments.run_live_dashboard --miners 6 --nodes 0 --steps 100 --block-chance 0.1 --auto-open --keep-alive 90
```

说明：
- 仿真结束后，Dashboard 会在 **新标签页** 自动打开 `/summary`（默认约 5 秒延迟），主看板保留用于对照。
- `summary` 页面新增 **Back to Live Dashboard** 与 **Close This Summary Tab** 按钮。
- 即使设置了 `--keep-alive`，也可在终端随时按 `q`（或 `--exit-key` 指定键）提前优雅退出。

---

## 3. 参数总表

## 3.1 通用仿真参数（两种模式都用）

1. `SANDBOX_TOTAL_STEPS`（默认：LLM=320，No-LLM=480）
- 逻辑时间地平线

2. `SANDBOX_RANDOM_SEED`（默认 11）
- 随机种子，保证可复现

3. `SANDBOX_NUM_MINERS`（默认：LLM=12，No-LLM=40）
- 矿工数量

4. `SANDBOX_NUM_FULL_NODES`（默认：LLM=24，No-LLM=120）
- 全节点数量

5. `SANDBOX_TOPOLOGY_TYPE` (默认：`random`)
- 网络拓扑生成算法。支持 `random` 与 `barabasi_albert` (无标度网络模型)。

6. `SANDBOX_TOPOLOGY_BA_M` (默认：3)
- Barabasi-Albert 网络的参数 m（每次添加新节点连入的边数）。仅在拓扑为 barabasi_albert 时生效。

7. `SANDBOX_EDGE_PROB`（默认：LLM=0.24，No-LLM=0.60）
- 随机有向边生成概率。仅在拓扑为 random 时生效。

8. `SANDBOX_MIN_LATENCY`（默认：LLM=1.0，No-LLM=0.15）
9. `SANDBOX_MAX_LATENCY`（默认：LLM=5.0，No-LLM=0.70）
- 边传播延迟范围

10. `SANDBOX_MIN_RELIABILITY`（默认：LLM=0.9，No-LLM=0.997）
11. `SANDBOX_MAX_RELIABILITY`（默认：1.0）
- 边可靠性范围

12. `SANDBOX_BLOCK_DISCOVERY_CHANCE`（默认：LLM=0.02，No-LLM=0.02）
- 泊松出块事件到达率 `lambda`。默认采用高延迟/低并发配置以降低自然孤块。

11. `SANDBOX_MAX_HOPS`（默认：LLM=5，No-LLM=12）
- 单次传播最大跳数

12. `SANDBOX_PROGRESS_INTERVAL_STEPS`（默认：LLM=20，No-LLM=20）
- 进度日志打印间隔

13. `SANDBOX_SNAPSHOT_INTERVAL_BLOCKS`（默认：LLM=10，No-LLM=20）
- 每 N 个挖出块生成一个窗口（同时导出窗口树图）

14. `SANDBOX_OUTPUT_ROOT`（默认 `outputs`）
- 导出目录根路径，实际输出目录结构如 `outputs/default/2026-04-02/run_120000/`。

## 3.2 LLM 模式专用参数

1. `SANDBOX_LLM_CONFIG_FILE`（默认 `configs/llm_provider.yaml`）
- LLM配置文件路径

2. `LLM_MAX_CONCURRENT_REQUESTS`（在 `llm_provider.yaml` 或环境变量中设置，默认 5）
- LLM 调度器并发请求数上限，控制并行访问 API 的速度。

3. `LLM_TIMEOUT_SECONDS`（在 `llm_provider.yaml` 中设置，默认 30.0）
- LLM 调度器单次请求超时时间。

4. `decision_cooldown_steps`（在 `core/config.py` 中的 `LLMConfig` 中设置，默认 10）
- （新）智能短路路由：在未触发强事件时，若连续 N 步没有请求 LLM，才会允许发送全局周期探测。减少空等时间调用，降低 Token 开销。

5. `force_llm_on_fork`（默认 True）
- （新）智能短路路由：强制开启发生等高或更高分叉事件时，不管是否在冷却期都唤醒大模型。

2. `SANDBOX_AGENT_PROFILE_FILE`（默认 `configs/agent_profiles.toml`）
- 矿工人格与阵营配置

3. `SANDBOX_PREFLIGHT_LLM`（默认 1）
- 是否启动前连通性检查

4. `SANDBOX_PREFLIGHT_STRICT`（默认 1）
- 预检查失败是否中断

5. `SANDBOX_VERBOSE_LLM_LOG`（默认 0）
- 打开详细 LLM 请求日志

6. `SANDBOX_LIVE_WINDOW_SUMMARY`（默认 1）
- 实时输出窗口面板

7. `SANDBOX_SAVE_ARTIFACTS`（默认 1）
- 是否导出数据文件

8. `SANDBOX_EXPORT_PROMPTS`（默认 1）
- 是否导出 `prompt_traces.jsonl`

9. `SANDBOX_ENABLE_FORUM` (默认 1)
- 是否开启论坛舆情与声誉治理。

10. `SANDBOX_ENABLE_ATTACK_JAMMING`（默认 1）
- 是否允许大模型使用 `jam_target` 动作对目标矿工发动物理断网/降速攻击。

11. `SANDBOX_ENABLE_TOKENOMICS`（默认 0）
- 是否启用代币经济学模块。开启后，挖矿将消耗模拟资金，成功出块将奖励 Token（随网络孤块率浮动）。大模型可执行 `economic_action='power_off'` 关机止损。

## 3.3 No-LLM 模式专用参数

1. `SANDBOX_TARGET_MINED_BLOCKS`（默认 5000）
- 目标挖出块数（达到后提前结束）

---

## 4. 常用预设实验配方（Launch Recipes）

以下提供了 4 个预设好的命令行启动脚本。直接复制到 Powershell 即可运行。

### 实验 1：绝对公平的零延迟基线 (No-LLM, 全诚实)
**目的**：测试在“瞬间网络传播”的乌托邦下，系统算力与出块率是否严格围绕 1.0 (绝对公平)。没有孤块干扰。
**参数**：80 人，2000 块，无延迟，无论坛。
```powershell
cd D:\my
$env:SANDBOX_TOTAL_STEPS='100000'
$env:SANDBOX_TARGET_MINED_BLOCKS='2000'
$env:SANDBOX_NUM_MINERS='80'
$env:SANDBOX_NUM_FULL_NODES='160'
# 零延迟配置
$env:SANDBOX_MIN_LATENCY='0.0'
$env:SANDBOX_MAX_LATENCY='0.0'
$env:SANDBOX_EDGE_PROB='1.0'
$env:SANDBOX_BLOCK_DISCOVERY_CHANCE='0.15'
$env:SANDBOX_MAX_HOPS='12'
$env:SANDBOX_SNAPSHOT_INTERVAL_BLOCKS='50'
$env:SANDBOX_PROGRESS_INTERVAL_STEPS='200'
$env:SANDBOX_OUTPUT_ROOT='D:\my\outputs\exp1_baseline'
python -m experiments.run_honest_no_llm
```

### 实验 2：自然孤块率基线 (No-LLM, 全诚实)
**目的**：测试在有正常 P2P网络传播延迟的情况下，自然分叉与孤块产生的概率，以及对小算力矿工的公平性影响。
**参数**：80 人，2000 块，有延迟，无论坛。
```powershell
cd D:\my
$env:SANDBOX_TOTAL_STEPS='100000'
$env:SANDBOX_TARGET_MINED_BLOCKS='2000'
$env:SANDBOX_NUM_MINERS='80'
$env:SANDBOX_NUM_FULL_NODES='160'
# 正常传播延迟与拓扑
$env:SANDBOX_MIN_LATENCY='0.2'
$env:SANDBOX_MAX_LATENCY='1.5'
$env:SANDBOX_EDGE_PROB='0.2'
$env:SANDBOX_BLOCK_DISCOVERY_CHANCE='0.15'
$env:SANDBOX_MAX_HOPS='12'
$env:SANDBOX_SNAPSHOT_INTERVAL_BLOCKS='50'
$env:SANDBOX_PROGRESS_INTERVAL_STEPS='200'
$env:SANDBOX_OUTPUT_ROOT='D:\my\outputs\exp2_orphan_baseline'
python -m experiments.run_honest_no_llm
```

### 实验 3：自私挖矿攻击干扰 (LLM, 禁用论坛)
**目的**：启用大模型代理的自私矿工，观察他们如何不依赖社交机制，纯靠算力与延迟差通过自私挖矿（withhold & release）争夺主链。
**参数**：6 人，30 块，有延迟，禁用论坛，使用包含自私阵营的人格配置。
```powershell
cd D:\my
$env:SANDBOX_TOTAL_STEPS='150'
$env:SANDBOX_NUM_MINERS='6'
$env:SANDBOX_NUM_FULL_NODES='10'
$env:SANDBOX_MIN_LATENCY='1.0'
$env:SANDBOX_MAX_LATENCY='4.0'
$env:SANDBOX_EDGE_PROB='0.3'
$env:SANDBOX_BLOCK_DISCOVERY_CHANCE='0.05'
# 核心控制：启用混杂阵营配置，禁用论坛
$env:SANDBOX_AGENT_PROFILE_FILE='D:\my\configs\agent_profiles.toml'
$env:SANDBOX_ENABLE_FORUM='0'
$env:SANDBOX_VERBOSE_LLM_LOG='1'
$env:SANDBOX_SNAPSHOT_INTERVAL_BLOCKS='10'
$env:SANDBOX_OUTPUT_ROOT='D:\my\outputs\exp3_selfish_no_forum'
python -m experiments.run_llm_sandbox
```

### 实验 4：全量社交战争 (LLM, 启用论坛与治理)
**目的**：开启最完整的沙盒特性。观察自私矿工与诚实矿工如何在 Tieba 上进行互相指责、舆论造势，以及极端声誉低下导致被全网断网（Jamming / Banned）。也可以直接运行 `python -m experiments.run_social_warfare`。
**参数**：6 人，30 块，有延迟，启用论坛与治理体系。
```powershell
cd D:\my
$env:SANDBOX_TOTAL_STEPS='150'
$env:SANDBOX_NUM_MINERS='6'
$env:SANDBOX_NUM_FULL_NODES='10'
$env:SANDBOX_MIN_LATENCY='1.0'
$env:SANDBOX_MAX_LATENCY='4.0'
$env:SANDBOX_EDGE_PROB='0.3'
$env:SANDBOX_BLOCK_DISCOVERY_CHANCE='0.05'
# 核心控制：启用所有特性
$env:SANDBOX_AGENT_PROFILE_FILE='D:\my\configs\agent_profiles.toml'
$env:SANDBOX_ENABLE_FORUM='1'
$env:SANDBOX_VERBOSE_LLM_LOG='1'
$env:SANDBOX_SNAPSHOT_INTERVAL_BLOCKS='10'
$env:SANDBOX_OUTPUT_ROOT='D:\my\outputs\exp4_social_warfare'
python -m experiments.run_llm_sandbox
```

### 4.5 四组实验速查汇总表

| 编号 | 模式 | 论坛 | 传播延迟 | 规模 | 入口命令 |
|---|---|---|---|---|---|
| 实验1 | No-LLM 诚实链 | 禁用 | 无（0.0/0.0） | 80矿工 / 2000块 | `python -m experiments.run_honest_no_llm` |
| 实验2 | No-LLM 诚实链 | 禁用 | 有（0.2~1.5） | 80矿工 / 2000块 | `python -m experiments.run_honest_no_llm` |
| 实验3 | LLM 自私挖矿 | 禁用 | 有（1.0~4.0） | 6矿工 / 30块（建议） | `python -m experiments.run_llm_sandbox` |
| 实验4 | LLM 自私 + 论坛 + 声誉 | 启用 | 有（1.0~4.0） | 6矿工 / 30块（建议） | `python -m experiments.run_llm_sandbox` 或者 `experiments.run_social_warfare`|

> 说明：实验 3/4 都建议先确认 `configs/llm_provider.yaml` 可连通；若网络不稳定，可临时设置 `SANDBOX_PREFLIGHT_STRICT=0` 避免启动前中断。

### 实验 5：Tokenomics 对自私挖矿的抑制测试
包含两个对比实验（开启/关闭代币经济学），用于研究经济惩罚与币价绑定机制如何改变矿工的作恶策略。
**详细实验参数与分析方法请参阅：** [`docs/EXPERIMENT_CASES.md`](./EXPERIMENT_CASES.md)

---

## 5. 输出文件说明

无论 LLM 还是 No-LLM 模式，引擎运行结束后，会自动在 `outputs/<group>/<date>/run_<time>/` 目录下生成分类组织的日志：

- `reports/summary.json`: 全量核心指标
- `reports/miner_details.csv`: 各节点胜率与表现
- `reports/window_snapshots.csv`: 时序指标面板
- `reports/scheduler_metrics.json`: LLM 独立调度器性能指标 (仅限 LLM 模式)
- `data/blocks.jsonl`: 链历史
- `data/forum_posts.jsonl`: 论坛发言 (如开启)
- `data/prompt_traces.jsonl`: LLM 交互与回退日志
- `visualizations/full_tree.png`: 整棵区块树

---

## 6. 结果判读建议

1. 看孤块率：`summary.json -> orphan_ratio`
- 越低越接近稳定网络

2. 看 ratio 公平性：`miner_details.csv -> canonical_vs_hp_ratio`
- 理想围绕 1 波动
- 小算力矿工波动会更大

3. 看总体一致性：
- `corr(hash_power, canonical_share)` 越接近 1 越好
- `mae(hash_power vs canonical_share)` 越小越好

---

## 7. 常见问题

1. `queue=xxxx` 是什么？
- 事件队列长度（未来待处理的传播/出块事件数），不是报错。

2. 运行看起来“卡住”？
- 大概率在生成大量 PNG（窗口很多时）。

3. LLM 模式连接报错？
- 第三方网关波动常见。当前引擎已带重试与 fallback，不会轻易中断整场。

---

## 8. 交接建议

1. 做公平性/性能基线：优先用 `run_honest_no_llm.py`
2. 做策略/舆情行为研究：再用 `run_llm_sandbox.py` 或 `run_social_warfare.py`
3. 先小规模试跑，再开大规模参数，避免长时间无效等待