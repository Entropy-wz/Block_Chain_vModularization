# 区块链沙盘单元测试指南 (Testing Guide)

本文档旨在说明 `Agentic Blockchain Sandbox` 项目中的测试结构、运行方法以及如何在二次开发中编写并运行回归测试。我们的单元测试不仅检查代码级别的崩溃情况，更重点验证了区块链共识的概率分布、网络连通性以及系统间模块交互的鲁棒性。

## 1. 测试目录结构

所有的单元测试均存放在根目录的 `tests/` 文件夹中，遵循与源代码对应的分层结构：

```text
tests/
├── conftest.py                   # Pytest 全局 fixtures (如注入确定的随机数种子)
├── core/
│   └── test_topology.py          # 图网络拓扑生成与属性验证测试
├── engine/
│   └── test_mining.py            # 核心离散事件仿真(DES)的出块概率分布测试
├── llm/
│   └── test_llm_parser.py        # LLM 输出容错解析器防崩溃测试
└── modules/
    └── test_tokenomics.py        # 模块化代币经济学跨组件事件流验证
```

---

## 2. 核心测试解析与覆盖范围

### 2.1 P2P 拓扑验证 (`test_topology.py`)
- **目标**：确保底层的拓扑网络结构在极端参数下依然具备连通性和所需的图学特征。
- **代表用例 (`test_barabasi_albert_topology_connectivity`)**：
  验证 `Barabasi-Albert` (无标度网络) 算法能否正确生成图结构。它不仅检查是否有“孤岛节点”（所有节点度是否大于0），同时也验证是否诞生了高连通度的“超级节点(Hub)”。如果在开发中不慎改坏了 `TopologyGenerator` 算法，该测试会立即报错。

### 2.2 共识公平性分布测试 (`test_mining.py`)
- **目标**：验证在离散事件主循环中，泊松随机出块能否在大量样本下收敛于节点的算力(Hash Power)比例。
- **代表用例 (`test_hash_power_distribution`)**：
  构建了具有差异算力的多矿工网络（如 100算力 vs 10算力），循环模拟抽签 1000 次，检查各节点出块次数是否严格落在统计学置信区间内。
  > **注意**：测试通过注入 `Dummy` 的 LLM API 参数越过了引擎对模型的真实校验，从而加快本地运行速度而不消耗 API Token。

### 2.3 LLM 输出鲁棒性测试 (`test_llm_parser.py`)
- **目标**：测试与大模型对接时的“防暴走”兜底机制。真实的 LLM 极不稳定，常输出被 Markdown 包裹的文本或无关废话。
- **覆盖点**：
  - `valid_json`：验证正常输出。
  - `markdown_blocks`：验证能否利用正则剔除 ```json ... ```。
  - `invalid_json_fallback`：验证当大语言模型产生严重幻觉输出非结构化垃圾内容时，解析器是否能安全回落至空字典兜底 (`fallback`)，而非触发应用级崩溃。

### 2.4 事件总线与模块测试 (`test_tokenomics.py`)
- **目标**：验证“微内核”下，解耦的插件化模块是否能正常接收 `EventBus` 的广播并执行自身逻辑。
- **代表用例 (`test_tokenomics_block_reward`)**：
  使用一个假造的仿真上下文 (`DummyContext`) 向系统直接投喂 `on_block_mined` 事件。验证监听此事件的 `TokenomicsModule` 是否能够根据协议正确地增加挖矿者的账本余额。

---

## 3. 运行方法与常用参数

在项目根目录下，确保你已安装依赖 `pytest`：

```bash
# 运行所有用例 (推荐在提交代码前执行)
python -m pytest tests/

# 查看详细的通过信息 (包括标准输出)
python -m pytest tests/ -v -s

# 仅运行指定目录/文件的测试
python -m pytest tests/engine/
python -m pytest tests/core/test_topology.py

# 快速失败模式 (一遇到错误即刻停止运行)
python -m pytest tests/ -x
```

> **提示**：测试的执行速度应当在秒级（< 3 秒）内完成。为确保效率，测试不会真实调用外部网络或 LLM 接口，所有外部依赖已被 Mock 化或短路处理。

---

## 4. 编写新模块测试的指南

当你编写了新的策略模块（如新增“贿赂模块”或调整共识规则）时，建议通过 **TDD (Test-Driven Development)** 流程先建立对应测试防踩坑：

1. **新建测试文件**：在对应的 `tests/` 子目录下新建 `test_xxx.py`。
2. **避免实例化完整引擎**：
   完整的 `AgenticSimulation` 往往包含海量的图操作和日志。进行测试时，推荐像 `test_tokenomics.py` 中那样构建一个极简的 **DummyContext**，从而孤立地测试某一方法的确定性行为。
3. **注入 Dummy 参数**：
   如果被迫需要实例化带有校验的类，确保为其提供 `dummy_key` 以绕过网络认证。
4. **清理临时句柄**：
   如果有触发过 `BlockStorage` 或者落盘 I/O，必须在测试结尾执行 `sim.block_storage.cleanup()` 以避免 Windows 系统抛出 `PermissionError` 文件锁被占用异常。
