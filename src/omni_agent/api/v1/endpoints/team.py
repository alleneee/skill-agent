"""
团队 API 端点，用于多 Agent 协调。

使用团队系统，其中 Leader Agent 智能地将任务委派给成员。
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from omni_agent.api.deps import get_llm_client, get_session_manager, get_tools
from omni_agent.core.session_manager import UnifiedTeamSessionManager
from omni_agent.core.team import Team
from omni_agent.schemas.team import (
    DependencyRunRequest,
    DependencyRunResponse,
    TeamConfig,
    TeamMemberConfig,
)
from omni_agent.schemas.team import (
    TeamRunResponse as TeamRunResponseSchema,
)
from omni_agent.utils.logger import logger

router = APIRouter(prefix="/team", tags=["team"])


# 预定义的角色配置
ROLE_CONFIGS = {
    "researcher": {
        "role": "Research Specialist",
        "instructions": "你是研究员，擅长搜索信息、阅读资料并总结要点。专注于收集准确、全面的信息。",
        "tools": ["read", "bash"],
    },
    "writer": {
        "role": "Writing Expert",
        "instructions": "你是写作专家，擅长将信息组织成清晰、结构化的文档。注重内容的逻辑性和可读性。",
        "tools": ["write", "edit"],
    },
    "coder": {
        "role": "Programming Expert",
        "instructions": "你是编程专家，擅长编写代码和解决技术问题。注重代码质量和最佳实践。",
        "tools": ["write", "edit", "read", "bash"],
    },
    "reviewer": {
        "role": "Quality Reviewer",
        "instructions": "你是审阅专家，负责检查内容的质量、准确性和完整性。提供建设性的反馈。",
        "tools": ["read"],
    },
    "analyst": {
        "role": "Data Analyst",
        "instructions": "你是数据分析专家，擅长分析数据、提取洞察并生成报告。",
        "tools": [],  # 将获取所有工具
    },
}


class TeamRunRequest(BaseModel):
    """团队运行请求模型。"""

    message: str = Field(..., description="任务描述")
    members: list[str] = Field(
        default=["researcher", "writer"],
        description="成员角色列表: researcher, writer, coder, reviewer, analyst",
    )
    delegate_to_all: bool = Field(
        default=False, description="是否将任务广播给所有成员（而不是由 Leader 选择性委派）"
    )
    team_name: str | None = Field(default="AI Team", description="团队名称")
    team_description: str | None = Field(default=None, description="团队描述")
    leader_instructions: str | None = Field(default=None, description="Leader 的额外指令")
    workspace_dir: str | None = Field(default="./workspace", description="工作空间目录")
    max_steps: int = Field(default=50, description="最大执行步数")
    session_id: str | None = Field(default=None, description="会话ID（用于多轮对话）")


class TeamRunResponse(BaseModel):
    """团队运行响应模型。"""

    success: bool
    team_name: str
    message: str
    member_runs: list[dict[str, Any]] = Field(default_factory=list)
    total_steps: int = 0
    iterations: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


def _build_team_config(request: TeamRunRequest, available_tools: list) -> TeamConfig:
    """根据请求和可用工具构建 TeamConfig。"""

    # 获取所有工具名称用于过滤
    all_tool_names = [getattr(t, "name", "") for t in available_tools]

    # 构建成员配置
    members = []
    for role_name in request.members:
        role_config = ROLE_CONFIGS.get(role_name.lower())

        if role_config:
            # 过滤出存在于可用工具中的工具
            if role_config["tools"]:
                member_tools = [t for t in role_config["tools"] if t in all_tool_names]
            else:
                # 空列表表示所有工具（用于 analyst）
                member_tools = all_tool_names

            members.append(
                TeamMemberConfig(
                    name=role_name.capitalize(),
                    role=role_config["role"],
                    instructions=role_config["instructions"],
                    tools=member_tools,
                )
            )
        else:
            # 自定义角色
            members.append(
                TeamMemberConfig(
                    name=role_name.capitalize(),
                    role=role_name,
                    instructions=f"你是{role_name}，请协助完成任务。",
                    tools=all_tool_names,  # 给自定义角色分配所有工具
                )
            )

    return TeamConfig(
        name=request.team_name or "AI Team",
        description=request.team_description,
        members=members,
        leader_instructions=request.leader_instructions,
        delegate_to_all=request.delegate_to_all,
    )


@router.post("/run", response_model=TeamRunResponse)
async def run_team(
    request: TeamRunRequest,
    llm_client=Depends(get_llm_client),
    tools=Depends(get_tools),
    session_manager: UnifiedTeamSessionManager | None = Depends(get_session_manager),
) -> TeamRunResponse:
    """执行多 Agent 团队任务。

    团队系统使用 Leader Agent 智能分析任务并将工作委派给合适的成员。

    **工作流程:**
    1. Leader 接收任务并分析需要完成的工作
    2. Leader 使用委派工具将工作分配给成员
    3. 成员执行任务并返回结果
    4. Leader 综合结果并提供最终答案

    **委派模式:**
    - `delegate_to_all=false` (默认): Leader 选择委派给哪个成员
    - `delegate_to_all=true`: 任务发送给所有成员获取多元视角

    **可用角色:**
    - `researcher`: 信息收集和研究
    - `writer`: 内容创作和文档编写
    - `coder`: 编程和技术任务
    - `reviewer`: 质量审查和反馈
    - `analyst`: 数据分析和洞察

    **会话支持:**
    - 提供 `session_id` 启用带历史上下文的多轮对话
    - 会话会持久化并可跨请求恢复

    **示例:**
    ```json
    {
        "message": "研究 Python 异步编程并撰写技术文章",
        "members": ["researcher", "writer", "reviewer"],
        "delegate_to_all": false,
        "session_id": "user-123"
    }
    ```
    """
    try:
        if not request.members:
            raise HTTPException(status_code=400, detail="At least one member is required")

        # 构建团队配置
        team_config = _build_team_config(request, tools)

        # 使用全局会话管理器创建团队
        team = Team(
            config=team_config,
            llm_client=llm_client,
            available_tools=tools,
            workspace_dir=request.workspace_dir or "./workspace",
            session_manager=session_manager,  # 使用注入的全局会话管理器
        )

        # 执行任务
        logger.info(
            f"Running team '{team_config.name}' with members={request.members}, session_id={request.session_id}"
        )
        result: TeamRunResponseSchema = await team.run(
            message=request.message, max_steps=request.max_steps, session_id=request.session_id
        )

        # 转换为响应
        return TeamRunResponse(
            success=result.success,
            team_name=result.team_name,
            message=result.message,
            member_runs=[mr.model_dump() for mr in result.member_runs],
            total_steps=result.total_steps,
            iterations=result.iterations,
            metadata=result.metadata,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Team run failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/roles")
async def list_roles() -> dict[str, Any]:
    """列出可用的团队成员角色。

    返回每个预定义角色的信息及其能力。
    """
    return {
        "roles": [
            {
                "name": name,
                "role": config["role"],
                "description": config["instructions"],
                "default_tools": config["tools"] if config["tools"] else ["all"],
            }
            for name, config in ROLE_CONFIGS.items()
        ],
        "note": "You can also use custom role names. Custom roles will have access to all tools.",
    }


@router.get("/health")
async def team_health() -> dict[str, str]:
    """团队端点的健康检查。"""
    return {"status": "healthy", "service": "team"}


@router.post("/run-with-dependencies", response_model=DependencyRunResponse)
async def run_team_with_dependencies(
    request: DependencyRunRequest,
    llm_client=Depends(get_llm_client),
    tools=Depends(get_tools),
    session_manager: UnifiedTeamSessionManager | None = Depends(get_session_manager),
) -> DependencyRunResponse:
    """执行带明确依赖关系的团队任务。

    此端点允许定义任务的 DAG (有向无环图)，每个任务可以依赖其他任务的完成。

    **工作流程:**
    1. 任务根据依赖关系自动排序 (拓扑排序)
    2. 无依赖的任务先执行
    3. 同一依赖层的任务并行执行
    4. 每个任务会收到其依赖任务的结果作为上下文
    5. 如果任何任务失败，依赖它的任务将被跳过

    **优势:**
    - 明确控制任务执行顺序
    - 自动并行化独立任务
    - 依赖任务的结果作为上下文传递
    - 清晰的执行流程可视化

    **请求格式:**
    ```json
    {
        "tasks": [
            {
                "id": "research",
                "task": "研究 Python 异步编程",
                "assigned_to": "researcher",
                "depends_on": []
            },
            {
                "id": "analyze",
                "task": "分析研究结果",
                "assigned_to": "analyst",
                "depends_on": ["research"]
            },
            {
                "id": "write",
                "task": "撰写技术文章",
                "assigned_to": "writer",
                "depends_on": ["analyze"]
            },
            {
                "id": "code",
                "task": "编写示例代码",
                "assigned_to": "coder",
                "depends_on": ["analyze"]
            }
        ],
        "team_config": {
            "name": "Research Team",
            "members": [
                {"name": "Researcher", "role": "researcher", "tools": ["read", "bash"]},
                {"name": "Analyst", "role": "analyst", "tools": []},
                {"name": "Writer", "role": "writer", "tools": ["write", "edit"]},
                {"name": "Coder", "role": "coder", "tools": ["write", "edit", "bash"]}
            ]
        },
        "session_id": "user-123"
    }
    ```

    **执行顺序:**
    - 层 1: research (无依赖)
    - 层 2: analyze (依赖 research)
    - 层 3: write + code (并行，都依赖 analyze)

    **使用场景:**
    - 复杂的多步骤工作流
    - 研究 -> 分析 -> 报告生成
    - 数据收集 -> 处理 -> 可视化
    - 需求 -> 设计 -> 实现 -> 测试
    """
    try:
        if not request.tasks:
            raise HTTPException(status_code=400, detail="At least one task is required")

        team_config = request.team_config
        if not team_config:
            raise HTTPException(
                status_code=400, detail="team_config is required for dependency-based execution"
            )

        team = Team(
            config=team_config,
            llm_client=llm_client,
            available_tools=tools,
            workspace_dir=request.workspace_dir or "./workspace",
            session_manager=session_manager,
        )

        logger.info(
            f"Running team '{team_config.name}' with {len(request.tasks)} tasks in dependency mode, "
            f"session_id={request.session_id}"
        )

        result = await team.run_with_dependencies(
            tasks=request.tasks, session_id=request.session_id, user_id=request.user_id
        )

        return result

    except ValueError as e:
        logger.error(f"Dependency validation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Team dependency run failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
