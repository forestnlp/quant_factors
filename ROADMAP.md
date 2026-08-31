# quant_factors — 目标与开发路线图

> 本文档记录项目的**总目标、分阶段里程碑（Phase1-4）与当前进度（Todo）**。环境与定位见 [PROJECT.md](./PROJECT.md)，方法论见 `.trae/rules/methodology.md`，工程规则见 `.trae/rules/project-rules.md`。

## 一、项目总目标

搭建**本地 DeepSeek 驱动、7×24 小时全自动闭环**的因子 Loop Engineering 系统：

1. **自动挖掘**：本地 DeepSeek 批量产出差异化候选因子（月产千级）。
2. **Qlib 校验**：IC / RankIC / ICIR 标准化评估 + 五层过拟合防御（训练集挖掘→验证集筛选→全样本校验→稳定性校验→相关性去重）。
3. **负反馈迭代**：每轮成功/失败数据反向输入模型，越挖越精准。
4. **私有因子库**：向量知识库沉淀，语义+数值双重去重，形成专属资产。

---

## 二、分阶段里程碑

### ✅ Phase0：项目重构与底座（已完成）
- [x] 清理全部历史实验代码（playground / TPD 策略 / 手工脚本），归集为二区结构。
- [x] 本地 DeepSeek 接入验证（`LLMClient` 连接 + 生成正常）。
- [x] Qlib 数据底座就绪（`data/cn_data`，全市场日线）。
- [x] 单轮评估链验证（`factor_miner.py smoke`：IC/ICIR 计算正常）。

### 🔄 Phase1：原型打通（进行中）
- [x] `llm_client.py`：OpenAI 兼容客户端封装。
- [x] `factor_miner.py`：结构化 Prompt → 生成因子 → 批量 Qlib 回测的最小闭环。
- [ ] 单轮链路稳定产出可回测因子（修复 DeepSeek 连接问题后验证）。
- [ ] 统计模型常见错误（未来函数/数据错位/代码异常），固化基础 Prompt 约束。
- [ ] **阶段目标**：单轮链路 100% 通畅，无致命 bug，可稳定产出因子。

### ⏳ Phase2：闭环迭代（8-21 天）
- [ ] 向量知识库 + 结构化数据库，沉淀成功/失败因子全量数据。
- [ ] 失败复盘反馈链路：失效原因、缺陷逻辑反向输入模型。
- [ ] AlphaMiner 五层过拟合过滤体系。
- [ ] 因子去重、相似度判定、稳定性筛选。

### ⏳ Phase3：工程化加固（22-35 天）
- [ ] Prefect 工作流调度：任务队列、断点续跑、并发限流。
- [ ] Docker 沙箱隔离 LLM 生成代码（防死循环/内存泄漏/OOM）。
- [ ] GPU、磁盘、任务状态监控告警。

### ⏳ Phase4：优化进化（36 天+）
- [ ] 基于成败样本垂直微调 DeepSeek。
- [ ] Prompt 多样性策略，多维度因子探索。
- [ ] 优质因子变异迭代 + 人工审核后台。

---

## 三、核心研究结论（历史沉淀）

1. **当前 A股环境（近3年震荡市）下，有效信号方向为「负向」**：放量 / 高波动的股票未来收益反而偏低（短期反转特征）。
2. **最强量价因子是「放量类」**：`turnover_ratio_5`（量能比）RankICIR ≈ -0.48，优于动量/波动率。
3. **重要警示**：单因子 IC 绝对值普遍 <0.03 属微弱水平，需多因子合成；历史回测年化基于乐观假设，不可当实盘预期。

---

## 四、当前目录速览

代码遵循「`research/`(引擎工作区) → `src/`(正式区)」递进路径。

| 文件 | 作用 |
|---|---|
| `research/config.py` | .env / QLIB_URI / LLM 配置统一读取 |
| `research/llm_client.py` | 本地 DeepSeek OpenAI 兼容客户端（自动剥离 reasoning） |
| `research/factor_miner.py` | 单轮挖掘闭环：Prompt→DeepSeek→批量 Qlib 回测→结果落盘 |
| `research/factor_eval.py` | 因子评估层：IC/RankIC/ICIR + 截面缩尾标准化 |
| `research/data_fetcher.py` | 数据采集层：qlib 全市场日线初始化 + 东财标的分钟/日线K |
| `src/README.md` | 正式区占位说明 |

> 本文件为项目路线图，随开发进度持续更新。完成一项 Todo 后在对应复选框打勾。
