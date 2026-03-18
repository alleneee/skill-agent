# DeerFlow (bytedance/deer-flow) v2.0 架构要点

## 定位
SuperAgent Harness -- 不是 Agent Framework，而是 Agent Runtime。给 Agent 提供完整运行时基础设施（文件系统、沙盒、记忆、技能、子代理）。

## 技术栈
- 后端: Python + LangGraph + FastAPI + LangChain
- 前端: Next.js 16 + React 19 + Tailwind + Shadcn
- 沙盒: Local / Docker / K8s 三种模式

## 核心架构
- 双进程部署: Gateway (FastAPI:8001) + LangGraph Server (:2024)，nginx 统一代理
- 11 层中间件管道（ThreadData → Uploads → Sandbox → DanglingToolCall → Summarization → Todo → Title → Memory → ViewImage → SubagentLimit → Clarification）
- ThreadState 扩展 AgentState，混入 sandbox/artifacts/thread_data/todos/viewed_images
- 反射式 DI: config.yaml 的 `use` 字段通过 resolve_class()/resolve_variable() 动态加载任意实现

## Subagent 机制
- Lead Agent + Sub-Agent 模式，通过 task_tool 触发
- 三层并发控制: SubagentLimitMiddleware(截断) + 双层ThreadPoolExecutor(各3) + 系统提示限制
- 上下文隔离: 子代理只接收 task prompt，复用父 agent 的 sandbox 和 thread_data
- 防递归: 子代理不持有 task 工具

## Memory 系统
- JSON 文件存储: User Context + History + Facts (带 confidence)
- TF-IDF 余弦相似度评分注入 top-15 facts (score = similarity*0.6 + confidence*0.4)
- 防抖队列 + 后台 LLM 提取 + 原子写入

## Skill 系统
- 三层渐进加载: 元数据(始终) → SKILL.md(触发时) → 资源(按需)
- YAML frontmatter + Markdown 格式
- 内置: deep-research, ppt/podcast/video-generation, chart, bootstrap 等

## 扩展点
- Tool: config.yaml tools 数组 + resolve_variable
- MCP: extensions_config.json mcpServers
- Skill: skills/public 或 skills/custom 下创建 SKILL.md
- Subagent: subagents/builtins/ 下新建 + BUILTIN_SUBAGENTS dict
- Sandbox: config.yaml sandbox.use 指向新 SandboxProvider
- Model: config.yaml models 数组 + resolve_class
- Channel: 实现 Channel ABC + _CHANNEL_REGISTRY

## 项目地址
https://github.com/bytedance/deer-flow
