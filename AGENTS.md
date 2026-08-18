# AGENTS.md — 量化因子项目 AI 协作指南

本文件是项目级 AI 协作指南，Trae 会在每次会话中自动加载。所有编码行为必须遵循本文件的方法论与约束。

---

## 项目定位（Project-Specific Guidelines for quant_factors）

### 项目概述
- **名称**: quant_factors（量化因子开发系统）
- **目标**: **RD-Agent（自动化因子挖掘）+ Qlib（数据 / 因子 / 研究）+ Backtrader（策略回测）三者联合应用**，构建"数据 → 因子挖掘 → 回测验证"的完整闭环。
- **核心原则**: 下载的数据**最好保存在本地**，不依赖每次联网，方案要服从本地数据与环境的真实情况。
- **环境**: Conda 环境 `qlib_rdagent`（Python 3.10）；Qlib 0.9.7、RD-Agent 已装，**Backtrader 尚未安装**（需要时安装）。
- **本地数据目录**: `C:/Users/jay/qlib_data/cn_data`（已有 calendars / features / instruments）。

### 技术分工（抓主要矛盾）
- **Qlib**: 负责数据加载、因子表达式计算、因子研究（IC/IR）。
- **RD-Agent**: 负责自动化因子挖掘与迭代。
- **Backtrader**: 负责策略回测与绩效分析。
- 三者以"Qlib 数据 → 因子 → 回测"为主线串联，避免职责混乱。

### 代码风格规则
- **Python**: 遵循 PEP 8，公开 API 使用类型注解与 docstring。
- **命名**: 统一 `snake_case`。
- **注释**: 中文项目使用中文注释。
- **配置**: 环境变量与路径配置集中在 `.env` / 配置文件中，不硬编码。

### 测试与验证期望
- 新功能需有可验证的成功标准（见下方第 4 条）。
- 使用 pytest 编写测试；外部服务（网络下载、API）进行 mock 或本地化。

### 部署 / 运行
- 保持数据本地化，方案服从 `C:/Users/jay/qlib_data/cn_data` 的真实数据情况。
- 配置尽量使用环境变量。

---

## 0. 毛选方法论（工作总纲）

以《实践论》《矛盾论》《论持久战》为指导思想，贯穿所有开发任务：

1. **没有调查就没有发言权** — 动手编码前必先调研现状（读数据、看代码、摸环境），掌握一手资料，不做无根据假设。
2. **抓主要矛盾与主要方面** — 面对复杂任务，先分析哪是主要矛盾、哪是矛盾的主要方面，集中资源优先解决，避免平均用力、胡子眉毛一把抓。
3. **集中优势兵力打歼灭战** — 聚焦单一目标，逐个击破，打一个歼灭一个；不铺开战线、不做半途而废。
4. **实事求是、一切从实际出发** — 方案服从于数据与环境的真实情况，不套模板、不空谈理论。
5. **动态规划与闭环管理** — 制定可验证的阶段性目标，执行中依据反馈动态调整；每个阶段以"实践→认识→再实践"循环闭环，验证通过才进入下一阶段。
6. **具体问题具体分析** — 每个任务结合其上下文判断，不机械照搬规则。

> 总纲：先调研 → 抓主要矛盾 → 聚焦歼灭 → 动态闭环。与下方 1-4 条细则配合使用。

---

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- ✅ **State your assumptions explicitly**. If uncertain, ask.
- ✅ **Present multiple interpretations**. Don't pick silently.
- ✅ **Push back when warranted**. If a simpler approach exists, say so.
- ✅ **Stop and ask**. If something is unclear, name what's confusing.

**Anti-patterns to avoid**:

- ❌ Making assumptions without checking
- ❌ Hiding confusion and proceeding anyway
- ❌ Picking one interpretation without surfacing alternatives
- ❌ Continuing when confused instead of asking

---

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- ✅ Write only the code needed to solve the stated problem
- ✅ No features beyond what was asked
- ✅ No abstractions for single-use code
- ✅ No "flexibility" or "configurability" that wasn't requested
- ✅ No error handling for impossible scenarios
- ✅ If you write 200 lines and it could be 50, rewrite it

**The senior engineer test**:
Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

**Anti-patterns to avoid**:

- ❌ Adding "nice-to-have" features not requested
- ❌ Building abstractions for code that will only run once
- ❌ Adding configuration options nobody asked for
- ❌ Handling edge cases that can't happen in this context
- ❌ Over-engineering simple problems

---

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- ✅ **Touch only what's necessary**. Focus on the specific task.
- ✅ **Don't "improve" adjacent code**. Leave comments, formatting alone.
- ✅ **Don't refactor things that aren't broken**.
- ✅ **Match existing style**. Even if you'd do it differently.
- ✅ **Mention dead code**. If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:

- ✅ **Clean up YOUR mess**. Remove imports/variables/functions that YOUR changes made unused.
- ❌ **Don't delete pre-existing dead code** unless explicitly asked.

**The test**: Every changed line should trace directly to the user's request.

**Anti-patterns to avoid**:

- ❌ "While I'm here, let me also fix..." (scope creep)
- ❌ Reformatting code you didn't write
- ❌ Renaming things to match your preferences
- ❌ Deleting dead code you noticed but didn't create
- ❌ Changing comments you don't fully understand

---

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform vague tasks into verifiable goals:

| Vague Task            | Verifiable Goal                                       |
| --------------------- | ----------------------------------------------------- |
| "Add validation"      | "Write tests for invalid inputs, then make them pass" |
| "Fix the bug"         | "Write a test that reproduces it, then make it pass"  |
| "Refactor X"          | "Ensure tests pass before and after"                  |
| "Improve performance" | "Measure baseline, optimize, verify 2x improvement"   |

For multi-step tasks, state a brief plan:

```
1. [Step 1] → verify: [how to check]
2. [Step 2] → verify: [how to check]
3. [Step 3] → verify: [how to check]
```

**Strong success criteria** let you loop independently.
**Weak criteria** ("make it work") require constant clarification.

---

## How to Know These Guidelines Are Working

✅ **Good signs**:

- Clarifying questions appear BEFORE implementation
- PRs are smaller and more focused
- AI stops "improving" things that were fine
- Changes are surgical and traceable to requests
- Fewer rewrites due to overcomplication

❌ **Bad signs**:

- AI charges ahead without asking questions
- Large diffs with unrelated changes
- "While I'm here" scope creep
- Over-engineered solutions for simple problems
- Code style changes unrelated to the task

---

**Remember**: These guidelines are working if you see fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
