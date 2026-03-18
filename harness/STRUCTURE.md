# 仓库结构文档

## 目录树

```text
omni-agent/
+-- src/omni_agent/           # 源代码根目录
|   +-- api/                  # FastAPI 路由层
|   |   +-- deps.py           # 依赖注入 (LLM Client, Tools)
|   |   +-- v1/
|   |       +-- router.py     # 路由注册
|   |       +-- endpoints/    # API 端点
|   |           +-- agent.py  # Agent 执行端点
|   |           +-- team.py   # Team 多 Agent 端点
|   |           +-- acp.py    # ACP 协议端点
|   |           +-- health.py # 健康检查
|   |           +-- tools.py  # 工具列表
|   |           +-- knowledge.py # RAG 知识库
|   |           +-- memory.py # 记忆管理
|   |           +-- trace.py  # 追踪查看
|   +-- core/                 # 核心业务逻辑
|   |   +-- agent.py          # Agent 执行循环
|   |   +-- team.py           # Leader-Member 协作
|   |   +-- msghub.py         # 事件驱动广播
|   |   +-- ralph.py          # 迭代执行模式
|   |   +-- llm_client.py     # LLM 调用客户端
|   |   +-- token_manager.py  # Token 计数与压缩
|   |   +-- tool_executor.py  # 工具调度
|   |   +-- session.py        # 会话管理
|   |   +-- config.py         # 配置 (pydantic-settings)
|   |   +-- agent_logger.py   # 运行日志
|   |   +-- trace_logger.py   # 工作流追踪
|   |   +-- run_manager.py    # 运行取消管理
|   |   +-- memory.py         # 记忆系统
|   |   +-- graph.py          # 图执行引擎
|   |   +-- hooks.py          # 生命周期钩子
|   +-- tools/                # 工具实现
|   |   +-- base.py           # Tool 基类
|   |   +-- file_tools.py     # 文件读写工具
|   |   +-- bash_tool.py      # Shell 命令工具
|   |   +-- mcp_loader.py     # MCP 工具加载器
|   |   +-- spawn_agent_tool.py # 子 Agent 工具
|   |   +-- rag_tool.py       # RAG 搜索工具
|   |   +-- ralph_tools.py    # Ralph 模式工具
|   |   +-- note_tool.py      # 会话笔记工具
|   |   +-- memory_tools.py   # 记忆管理工具
|   +-- skills/               # 技能系统
|   |   +-- skill_tool.py     # 技能加载工具
|   |   +-- skill_loader.py   # 技能发现
|   |   +-- */SKILL.md        # 各技能定义
|   +-- rag/                  # RAG 知识库
|   |   +-- rag_service.py    # 搜索编排
|   |   +-- database.py       # PostgreSQL + pgvector
|   |   +-- embedding_service.py # 向量嵌入
|   |   +-- document_processor.py # 文档分块
|   +-- acp/                  # Agent Client Protocol
|   |   +-- schemas.py        # JSON-RPC 数据模型
|   |   +-- adapter.py        # 消息格式转换
|   |   +-- acp_server.py     # ACP 服务端
|   +-- sandbox/              # 沙箱执行环境
|   |   +-- manager.py        # 沙箱生命周期管理
|   |   +-- tools.py          # 沙箱工具
|   +-- cli/                  # CLI 交互界面
|   |   +-- main.py           # 入口点
|   |   +-- commands.py       # 命令注册
|   +-- schemas/              # 公共数据模型
|   +-- utils/                # 工具函数
|   +-- main.py               # FastAPI 应用入口
+-- tests/                    # 测试目录
|   +-- core/                 # Core 层测试
|   +-- tools/                # Tool 层测试
|   +-- api/                  # API 层测试
|   +-- integration/          # 集成测试
|   +-- conftest.py           # 全局测试 fixture
+-- harness/                  # 工程规范文档
+-- docs/                     # 扩展文档
+-- skills/                   # 外部技能目录
+-- workspace/                # Agent 文件操作默认目录
+-- .github/workflows/        # CI/CD 配置
+-- pyproject.toml            # 项目配置
+-- Makefile                  # 常用命令
+-- mcp.json                  # MCP 服务器配置
+-- .env                      # 环境变量 (不提交)
```

## 新增模块放置规则

| 类型 | 放置位置 | 示例 |
|------|----------|------|
| 新 API 端点 | `src/omni_agent/api/v1/endpoints/` | `webhooks.py` |
| 新核心组件 | `src/omni_agent/core/` | `planner.py` |
| 新工具 | `src/omni_agent/tools/` | `web_search_tool.py` |
| 新技能 | `src/omni_agent/skills/<skill-name>/` | `SKILL.md` |
| 新外部服务集成 | `src/omni_agent/services/` | `notification.py` |
| 新数据模型 | `src/omni_agent/schemas/` | `webhook.py` |
| 单元测试 | `tests/<layer>/` 对应源码层级 | `test_planner.py` |
| 集成测试 | `tests/integration/` | `test_full_workflow.py` |

## 关键文件索引

| 文件 | 说明 |
|------|------|
| `src/omni_agent/main.py` | 应用入口，FastAPI lifespan |
| `src/omni_agent/api/deps.py` | 依赖注入，工具注册 |
| `src/omni_agent/core/config.py` | 所有配置项定义 |
| `src/omni_agent/core/agent.py` | Agent 核心执行循环 |
| `pyproject.toml` | 项目元数据、依赖、工具配置 |
| `Makefile` | 开发常用命令 |
| `mcp.json` | MCP 服务器配置 |
| `CLAUDE.md` | Claude Code 工作指导 |
