# quant_factors — 项目目标与定位

本文档描述项目的**目标、技术架构与环境**。开发方法论见 `.trae/rules/methodology.md`，硬性工程规则见 `.trae/rules/project-rules.md`。

## 项目定位

- **名称**: quant_factors（因子 Loop Engineering 系统）
- **目标**: 搭建**本地大模型驱动、7×24 小时全自动闭环**的因子 Loop Engineering 系统，摆脱人工因子研发瓶颈，实现量化因子的**自动化挖掘 → Qlib 校验 → 负反馈迭代 → 私有因子库沉淀**。
- **核心原则**:
  - 全程**本地化私有化部署**：数据、模型、因子资产无外泄。
  - 数据保存在本地，不依赖每次联网；方案服从 `.env` 指向的真实数据情况。
  - 所有日志与产物只写入项目 `data/` 内，不写项目目录外。

## 环境

- **Conda 环境**: `jaycode`（本机位于 `/home/chinapost/.conda/envs/jaycode`）。
- **已装**: Qlib 0.9.7（pip 包名 `pyqlib`）、openai SDK、pandas/numpy。
- **本地大模型**: Qwen3.8-Flash（OpenAI 兼容接口，由 `.env` 的 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` 指定）。
- **本地数据目录**: `data/cn_data`（由 `.env` 的 `QLIB_URI` 指定）；产物 `data/bt_export/`。

## 技术架构（三大牛鼻子）

1. **本地大模型适配 + Prompt 工程标准化**（解决挖掘质量）
   - `llm_client.py`：OpenAI 兼容调用封装，指向本地私有 API。
   - `factor_miner.py`：结构化 Prompt 约束，强制输出「因子假设 + Qlib 表达式 + 逻辑」，拒绝未来函数。
2. **Qlib 标准化 IC/IR 评估 + 五层过拟合防御**（解决因子真伪）
   - `factor_eval.py`：IC / RankIC / ICIR 评估 + 截面缩尾稳健标准化（无未来函数）。
3. **闭环调度 + 安全沙箱工程加固**（解决系统稳定，后续 Phase3）
   - Prefect 工作流调度 + Docker 沙箱（规划中）。

## 目录规划（二区隔离）

代码遵循「`research/`(引擎工作区) → `src/`(正式区)」的递进路径：

| 目录 | 性质 | 是否入库 | 说明 |
|------|------|---------|------|
| `research/` | 引擎工作区 | ✅ | Loop 工程核心代码（提炼/验证层） |
| `src/` | 正式区 | ✅ | 运行验证稳定后从 research 提升至此 |
| `data/` | 数据区 | ❌ gitignore | 由 `.env` 的 `QLIB_URI` 指向，含全部产物与日志 |

> 详细目录规则见 `.trae/rules/project-rules.md` 第 4 节。
