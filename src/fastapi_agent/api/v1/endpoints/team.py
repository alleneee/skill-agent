"""
Team API endpoints for multi-agent coordination
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends

from fastapi_agent.core.agent import Agent
from fastapi_agent.core.agent_team import AgentTeam, CoordinationStrategy, TeamRunResult
from fastapi_agent.api.deps import get_llm_client, get_tools
from fastapi_agent.utils.logger import logger

router = APIRouter(prefix="/team", tags=["team"])


class TeamRunRequest(BaseModel):
    """Team run request"""
    message: str = Field(..., description="任务描述")
    strategy: str = Field(default="leader_worker", description="协调策略: leader_worker, broadcast, sequential, round_robin")
    members: List[str] = Field(default=["researcher", "writer"], description="成员角色列表")
    coordinator_role: Optional[str] = Field(default="coordinator", description="协调者角色(仅leader_worker策略)")
    share_interactions: bool = Field(default=False, description="是否共享成员间交互")
    workspace_dir: Optional[str] = Field(default="./workspace", description="工作空间目录")
    max_steps: int = Field(default=50, description="最大执行步数")


class TeamRunResponse(BaseModel):
    """Team run response"""
    success: bool
    final_output: str
    member_outputs: Dict[str, Any]
    interactions: List[Dict[str, Any]]
    steps: int
    logs: List[Dict[str, Any]]
    shared_state: Dict[str, Any]
    metadata: Dict[str, Any] = Field(default_factory=dict)


def _create_agent_by_role(role: str, llm_client, tools: List) -> Agent:
    """根据角色创建 Agent"""

    role_configs = {
        "coordinator": {
            "name": "Coordinator",
            "system_prompt": "你是团队协调者,负责分析任务、制定计划并分配给合适的团队成员。你需要理解每个成员的能力并合理分工。",
            "tools": []  # 协调者通常不需要工具
        },
        "researcher": {
            "name": "Researcher",
            "system_prompt": "你是研究员,擅长搜索信息、阅读资料并总结要点。",
            "tools": [t for t in tools if getattr(t, 'name', '') in ['read', 'bash']]
        },
        "writer": {
            "name": "Writer",
            "system_prompt": "你是写作专家,擅长将信息组织成清晰、结构化的文档。",
            "tools": [t for t in tools if getattr(t, 'name', '') in ['write', 'edit']]
        },
        "coder": {
            "name": "Coder",
            "system_prompt": "你是编程专家,擅长编写代码和解决技术问题。",
            "tools": [t for t in tools if getattr(t, 'name', '') in ['write', 'edit', 'read', 'bash']]
        },
        "reviewer": {
            "name": "Reviewer",
            "system_prompt": "你是审阅专家,负责检查内容的质量、准确性和完整性。",
            "tools": [t for t in tools if getattr(t, 'name', '') in ['read']]
        },
        "analyst": {
            "name": "Analyst",
            "system_prompt": "你是数据分析专家,擅长分析数据、提取洞察并生成报告。",
            "tools": tools  # 分析师可能需要所有工具
        }
    }

    config = role_configs.get(role.lower(), {
        "name": role.capitalize(),
        "system_prompt": f"你是{role},请协助完成任务。",
        "tools": tools
    })

    return Agent(
        llm_client=llm_client,
        name=config["name"],
        system_prompt=config["system_prompt"],
        tools=config["tools"],
        max_steps=20  # 单个成员的最大步数限制
    )


@router.post("/run", response_model=TeamRunResponse)
async def run_team(
    request: TeamRunRequest,
    llm_client=Depends(get_llm_client),
    tools=Depends(get_tools)
) -> TeamRunResponse:
    """
    Execute a multi-agent team task

    This endpoint coordinates multiple agents to work together on a complex task.

    **Strategies:**
    - `leader_worker`: A coordinator analyzes the task and delegates to workers
    - `broadcast`: All members work on the same task in parallel
    - `sequential`: Members work in sequence, each using previous output
    - `round_robin`: Tasks are distributed evenly across members

    **Example:**
    ```json
    {
        "message": "Research Python async programming and write a technical article",
        "strategy": "leader_worker",
        "members": ["researcher", "writer", "reviewer"],
        "share_interactions": true
    }
    ```
    """
    try:
        # 解析策略
        try:
            strategy = CoordinationStrategy(request.strategy.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid strategy: {request.strategy}. "
                       f"Valid options: leader_worker, broadcast, sequential, round_robin"
            )

        # 创建成员 agents
        members = []
        for role in request.members:
            agent = _create_agent_by_role(role, llm_client, tools)
            members.append(agent)

        if not members:
            raise HTTPException(status_code=400, detail="At least one member is required")

        # 创建协调者 (如果需要)
        coordinator = None
        if strategy == CoordinationStrategy.LEADER_WORKER:
            if not request.coordinator_role:
                raise HTTPException(
                    status_code=400,
                    detail="coordinator_role is required for leader_worker strategy"
                )
            coordinator = _create_agent_by_role(request.coordinator_role, llm_client, tools)

        # 创建团队
        team = AgentTeam(
            members=members,
            strategy=strategy,
            coordinator=coordinator,
            name=f"Team-{strategy.value}",
            share_interactions=request.share_interactions,
            max_steps=request.max_steps,
            enable_logging=True,
            workspace_dir=request.workspace_dir
        )

        # 执行任务
        logger.info(f"Running team with strategy={strategy.value}, members={request.members}")
        result: TeamRunResult = team.run(
            message=request.message,
            workspace_dir=request.workspace_dir
        )

        # 转换结果
        return TeamRunResponse(**result.to_dict())

    except Exception as e:
        logger.error(f"Team run failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies")
async def list_strategies() -> Dict[str, Any]:
    """
    List available coordination strategies

    Returns information about each strategy and when to use it.
    """
    return {
        "strategies": [
            {
                "name": "leader_worker",
                "description": "A coordinator analyzes the task and delegates to appropriate workers",
                "use_cases": ["Complex tasks requiring intelligent decomposition", "Tasks with diverse skill requirements"],
                "requires_coordinator": True
            },
            {
                "name": "broadcast",
                "description": "All members work on the same task in parallel",
                "use_cases": ["Tasks requiring multiple perspectives", "Brainstorming sessions"],
                "requires_coordinator": False
            },
            {
                "name": "sequential",
                "description": "Members work in sequence, each building on previous output",
                "use_cases": ["Pipeline workflows", "Iterative refinement tasks"],
                "requires_coordinator": False
            },
            {
                "name": "round_robin",
                "description": "Tasks are distributed evenly across members in rotation",
                "use_cases": ["Balanced workload distribution", "Independent subtasks"],
                "requires_coordinator": False
            }
        ],
        "available_roles": [
            "coordinator", "researcher", "writer", "coder", "reviewer", "analyst"
        ]
    }


@router.get("/health")
async def team_health() -> Dict[str, str]:
    """Health check for team endpoints"""
    return {"status": "healthy", "service": "team"}
