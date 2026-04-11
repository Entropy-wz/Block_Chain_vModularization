# No-LLM 自私挖矿链指南（Eyal & Sirer 对照）

这条链用于**快速研究理论基础上的自私挖矿**，不依赖外部模型接口。  
运行一次即可同时得到“仿真结果”和“理论结果”，方便直接对照。

---

## 1. 启动命令

```bash
python -m experiments.run_selfish_no_llm
```

---

## 2. 参数说明

第三链专用参数：

- `SANDBOX_SELFISH_ALPHA`：自私方算力占比（默认 `0.35`）
- `SANDBOX_SELFISH_GAMMA`：同高竞争时自私方优势概率（默认 `0.5`）
- `SANDBOX_SELFISH_TARGET_BLOCKS`：目标主链区块数（默认 `5000`）
- `SANDBOX_SELFISH_RANDOM_SEED`：随机种子（默认继承 `SANDBOX_RANDOM_SEED`，再默认 `11`）
- `SANDBOX_SELFISH_STRATEGY`：自私策略名（`classic` / `stubborn` / `social`，默认 `classic`）
- `SANDBOX_THEORY_GAP_THRESHOLD`：理论匹配阈值（默认 `0.03`）

通用输出参数（复用）：

- `SANDBOX_OUTPUT_ROOT`：输出根目录（默认 `outputs`）
- `SANDBOX_EXPERIMENT_GROUP`：实验分组目录（默认 `selfish_no_llm`）

---

## 3. 三组一键配方

### A. 基线区（alpha=0.20）

```powershell
$env:SANDBOX_SELFISH_ALPHA='0.20'
$env:SANDBOX_SELFISH_GAMMA='0.50'
$env:SANDBOX_SELFISH_STRATEGY='classic'
$env:SANDBOX_SELFISH_TARGET_BLOCKS='5000'
python -m experiments.run_selfish_no_llm
```

### B. 临界区（alpha=0.25）

```powershell
$env:SANDBOX_SELFISH_ALPHA='0.25'
$env:SANDBOX_SELFISH_GAMMA='0.50'
$env:SANDBOX_SELFISH_STRATEGY='classic'
$env:SANDBOX_SELFISH_TARGET_BLOCKS='5000'
python -m experiments.run_selfish_no_llm
```

### C. 强攻击区（alpha=0.35）

```powershell
$env:SANDBOX_SELFISH_ALPHA='0.35'
$env:SANDBOX_SELFISH_GAMMA='0.50'
$env:SANDBOX_SELFISH_STRATEGY='classic'
$env:SANDBOX_SELFISH_TARGET_BLOCKS='5000'
python -m experiments.run_selfish_no_llm
```

---

## 4. 报告怎么读

关键字段在 `reports/summary.json`：

- `simulated_selfish_share`：仿真得到的自私方主链份额
- `theoretical_selfish_share`：理论计算得到的自私方份额
- `theory_gap_abs`：两者绝对差
- `theory_match`：是否在阈值内（由 `SANDBOX_THEORY_GAP_THRESHOLD` 控制）

建议用法：

1. 先固定 `gamma`，把 `alpha` 从低到高跑三组。  
2. 检查 `simulated_selfish_share` 是否随 `alpha` 上升。  
3. 用 `theory_gap_abs` 判断这组仿真是否接近理论期望。  

说明：

- 只有 `classic` 策略会输出理论对照字段；  
- `stubborn` / `social` 主要用于策略间仿真比较（理论字段为 `null`）。

---

## 5. 产物目录

运行后产物默认在：

`outputs/selfish_no_llm/YYYY-MM-DD/run_HHMMSS/`

包含：

- `reports/summary.json`
- `reports/miner_details.csv`
- `reports/lead_histogram.csv`
- `data/steps.jsonl`
- `visualizations/selfish_share_curve.png`
- `visualizations/lead_distribution.png`

---

## 6. Ratio口径与对比基准（2026-04-11）

本项目里用于比较“自私挖矿收益是否占优”的口径是：

`ratio = simulated_selfish_share / selfish_alpha`

解释：
- `ratio > 1`：自私方主链份额高于其算力占比
- `ratio = 1`：与算力占比持平
- `ratio < 1`：低于算力占比

同一组参数（`gamma=0.5`、`target_blocks=10000`、`seed=11`）下，三策略对比如下：

| alpha | strategy | simulated_selfish_share | ratio(simulated_selfish_share / alpha) |
|---|---|---:|---:|
| 0.20 | classic | 0.1859 | 0.9295 |
| 0.20 | stubborn | 0.1828 | 0.9140 |
| 0.20 | social | 0.1859 | 0.9295 |
| 0.25 | classic | 0.2562 | 1.0248 |
| 0.25 | stubborn | 0.2557 | 1.0228 |
| 0.25 | social | 0.2562 | 1.0248 |
| 0.35 | classic | 0.4227 | 1.2077 |
| 0.35 | stubborn | 0.4459 | 1.2740 |
| 0.35 | social | 0.4227 | 1.2077 |

补充：
- `alpha=0.35` 区间里，`stubborn` 的 ratio 最高。
- `social` 在 no-LLM 条件下与 `classic` 接近（没有论坛反馈时差异较小）。
