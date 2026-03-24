---
name: self-improvement
description: 当任务中出现非预期失败、用户纠正、缺失能力请求，或发现值得复用的项目模式时使用。负责把高价值经验沉淀到 `.learnings/`，并决定是否提升为项目规则或独立 skill。
---

# 自改进

把一次性对话中的高价值经验，转成项目内可复用资产。

## Quick Reference

| 情况 | 动作 |
|------|------|
| 命令/工具失败 | 记录到 `.learnings/ERRORS.md` |
| 用户纠正你 | 记录到 `.learnings/LEARNINGS.md`，类别 `correction` |
| 用户要求缺失能力 | 记录到 `.learnings/FEATURE_REQUESTS.md` |
| 外部 API 失败 | 记录到 `.learnings/ERRORS.md`，含集成细节 |
| 知识已过时 | 记录到 `.learnings/LEARNINGS.md`，类别 `knowledge_gap` |
| 发现更好做法 | 记录到 `.learnings/LEARNINGS.md`，类别 `best_practice` |
| 与已有条目相似 | 用 `See Also` 关联，考虑提升优先级 |
| 广泛适用的经验 | 提升到 `CLAUDE.md` / `AGENTS.md` |

## 文件结构

```text
.learnings/
├── LEARNINGS.md
├── ERRORS.md
└── FEATURE_REQUESTS.md
```

## 何时记录

优先记录这些情况：

1. 用户纠正了你的判断、假设或实现方式
2. 工具、命令、运行环境出现了非显然失败
3. 用户要求当前系统不直接支持的能力
4. 你发现了值得复用的项目约束、工作流或最佳实践
5. 你的知识已过时或与实际行为不符

不要记录这些情况：

1. 明显且一次性的错误
2. 无需复盘即可解决的小问题
3. 与当前项目无关的泛泛常识

## 记录原则

1. 只保留高信号信息，避免把 `.learnings/` 变成噪音堆积区
2. 先写"为什么以后还会有用"，再写"这次发生了什么"
3. 如果是错误，明确复现线索和建议修复方向
4. 如果是用户纠正，明确原假设哪里错了
5. 记录前先搜索已有条目，重复的用 See Also 关联
6. 如果模式已经稳定，考虑提升到 `AGENTS.md` 或抽出新 skill

## 记录格式

### Learning

~~~markdown
## [LRN-YYYYMMDD-XXXXXX] correction | knowledge_gap | best_practice

**Logged**: 2026-03-23T10:00:00+00:00
**Priority**: low | medium | high | critical
**Status**: pending
**Area**: frontend | backend | infra | tests | docs | config | runtime

### Summary
一句话说明学到了什么

### Details
说明当时的错误假设、触发条件和正确做法

### Suggested Action
以后应如何避免再次犯错

### Metadata
- Source: user_feedback | error | conversation
- Related Files: path/to/file.py
- Tags: tag1, tag2
- See Also: LRN-20260320-001 (如果与已有条目相关)
- Pattern-Key: correction.api_format (可选，用于重复模式追踪)
- Recurrence-Count: 1 (可选)

---
~~~

### Error

~~~markdown
## [ERR-YYYYMMDD-XXXXXX] auto_logged_error

**Logged**: 2026-03-23T10:00:00+00:00
**Priority**: medium | high
**Status**: pending
**Area**: runtime

### Summary
一句话说明哪里失败了

### Error
```text
具体错误内容
```

### Context
- Step: 3
- Tool: `bash`
- Task: 当前任务摘要

### Suggested Fix
说明后续应怎么复盘或修正

### Metadata
- Reproducible: yes | no | unknown
- Related Files: N/A
- Pattern-Key: tool_error.bash (可选)
- Recurrence-Count: 2 (可选)

---
~~~

### Feature Request

~~~markdown
## [FEAT-YYYYMMDD-XXXXXX] capability_name

**Logged**: 2026-03-23T10:00:00+00:00
**Priority**: medium
**Status**: pending
**Area**: runtime

### Requested Capability
用户需要什么能力

### User Context
为什么需要它

### Complexity Estimate
simple | medium | complex

### Suggested Implementation
可行的最小实现思路

### Metadata
- Frequency: first_time | recurring
- Related Features: N/A

---
~~~

## 条目生命周期

| Status | 含义 |
|--------|------|
| `pending` | 新记录，待处理 |
| `in_progress` | 正在处理中 |
| `resolved` | 已修复/已解决 |
| `promoted` | 已提升到 CLAUDE.md / AGENTS.md / 新 skill |
| `wont_fix` | 决定不处理（在 Resolution 中说明原因） |

解决条目时，追加 Resolution 块：

~~~markdown
### Resolution
- **Resolved**: 2026-03-24T09:00:00Z
- **Commit/PR**: abc123 or #42
- **Notes**: 简述做了什么
~~~

## 重复模式检测

记录前先搜索已有条目：

```bash
grep -r "keyword" .learnings/
```

如果找到相似条目：
1. 用 `See Also` 关联
2. 考虑提升优先级
3. 如果 Recurrence-Count >= 3，强烈建议提升到项目规则

## Priority 指引

| Priority | 适用场景 |
|----------|---------|
| `critical` | 阻塞核心功能、数据丢失风险、安全问题 |
| `high` | 显著影响、常见工作流受阻、反复出现 |
| `medium` | 中等影响、有 workaround |
| `low` | 轻微不便、边缘场景 |

## Area 标签

| Area | 范围 |
|------|------|
| `frontend` | UI、组件、客户端代码 |
| `backend` | API、服务、服务端代码 |
| `infra` | CI/CD、部署、Docker、云 |
| `tests` | 测试文件、测试工具 |
| `docs` | 文档、注释 |
| `config` | 配置文件、环境变量 |
| `runtime` | Agent 运行时、工具执行 |

## 提升路径

当某条 learning 被多次验证、具有跨任务价值时：

| Learning 类型 | 提升目标 | 示例 |
|--------------|---------|------|
| 项目约定 | `CLAUDE.md` | "包管理器用 uv，不要用 pip" |
| 工作流规则 | `AGENTS.md` | "API 变更后必须重新生成客户端" |
| 可复用模式 | 新 skill | 复杂到需要专门指导的模式 |

提升后更新原条目 Status 为 `promoted`，并注明 `**Promoted**: CLAUDE.md`。

## Skill 提取标准

当 learning 满足以下任一条件时，可以提取为独立 skill：

- 有 2+ 条 See Also 关联（反复出现）
- Status 为 resolved 且修复方案经过验证
- 非显而易见，需要实际调试才能发现
- 不限于特定项目，跨代码库可用
- 用户明确要求 "把这个存为 skill"

## 与原生 Hook 的关系

项目内的 `SelfImprovementHook` 自动做这些事：

1. 运行前提醒你在必要时使用本 skill
2. 工具失败时自动往 `ERRORS.md` 记一条基础记录
3. 同一工具反复失败时自动提升优先级并追踪 Pattern-Key
4. 用户 reject/edit 反馈时自动往 `LEARNINGS.md` 记录
5. feature_request 反馈时自动往 `FEATURE_REQUESTS.md` 记录

自动记录只是保底。真正高质量的 learning 仍然需要你在任务结束前主动整理。

## 定期回顾

在以下时机回顾 `.learnings/`：

- 开始新的大型任务前
- 完成一个功能后
- 在有历史 learning 的区域工作时

```bash
grep -h "Status\*\*: pending" .learnings/*.md | wc -l
grep -B5 "Priority\*\*: high" .learnings/*.md | grep "^## \["
```
