"""
多 Agent 协调系统核心类

支持多个 Agent 协作完成复杂任务,提供灵活的任务分配和协调机制。
"""

import asyncio
import json
import time
from enum import Enum
from typing import List, Dict, Any, Optional, Union, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from fastapi_agent.core.agent import Agent
from fastapi_agent.core.agent_logger import AgentLogger
from fastapi_agent.utils.logger import logger


class CoordinationStrategy(Enum):
    """协调策略枚举"""
    LEADER_WORKER = "leader_worker"  # 领导者-工作者模式
    BROADCAST = "broadcast"  # 广播模式(所有成员并行)
    SEQUENTIAL = "sequential"  # 顺序模式(pipeline)
    ROUND_ROBIN = "round_robin"  # 轮询模式


@dataclass
class MemberInteraction:
    """成员交互记录"""
    member_name: str
    input_message: str
    output_message: str
    timestamp: str
    step: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "member_name": self.member_name,
            "input": self.input_message,
            "output": self.output_message,
            "timestamp": self.timestamp,
            "step": self.step,
            "metadata": self.metadata
        }


@dataclass
class TeamRunResult:
    """团队运行结果"""
    success: bool
    final_output: str
    member_outputs: Dict[str, Any]
    interactions: List[MemberInteraction]
    steps: int
    logs: List[Dict[str, Any]]
    shared_state: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "final_output": self.final_output,
            "member_outputs": self.member_outputs,
            "interactions": [i.to_dict() for i in self.interactions],
            "steps": self.steps,
            "logs": self.logs,
            "shared_state": self.shared_state,
            "metadata": self.metadata
        }


class AgentTeam:
    """
    多 Agent 协调器

    支持多种协调策略:
    - LEADER_WORKER: 领导者分析任务并分配给工作者
    - BROADCAST: 将任务发送给所有成员
    - SEQUENTIAL: 按顺序执行,前一个输出作为后一个输入
    - ROUND_ROBIN: 轮询分配任务给各个成员
    """

    def __init__(
        self,
        members: List[Agent],
        strategy: CoordinationStrategy = CoordinationStrategy.LEADER_WORKER,
        coordinator: Optional[Agent] = None,
        name: str = "AgentTeam",
        shared_state: Optional[Dict[str, Any]] = None,
        share_interactions: bool = False,
        max_steps: int = 50,
        enable_logging: bool = True,
        workspace_dir: Optional[str] = None,
    ):
        """
        初始化 AgentTeam

        Args:
            members: 团队成员列表
            strategy: 协调策略
            coordinator: 协调者 Agent (仅在 LEADER_WORKER 策略时使用)
            name: 团队名称
            shared_state: 共享状态字典
            share_interactions: 是否在成员间共享交互记录
            max_steps: 最大执行步数
            enable_logging: 是否启用日志
            workspace_dir: 工作空间目录
        """
        if not members:
            raise ValueError("Team must have at least one member")

        if strategy == CoordinationStrategy.LEADER_WORKER and not coordinator:
            raise ValueError("LEADER_WORKER strategy requires a coordinator")

        self.members = members
        self.strategy = strategy
        self.coordinator = coordinator
        self.name = name
        self.shared_state = shared_state or {}
        self.share_interactions = share_interactions
        self.max_steps = max_steps
        self.enable_logging = enable_logging
        self.workspace_dir = workspace_dir or "./workspace"

        # 初始化成员名称映射
        self.member_map = {agent.name or f"Agent_{i}": agent for i, agent in enumerate(members)}

        # 交互历史
        self.interactions: List[MemberInteraction] = []

        # 日志器
        self.logger: Optional[AgentLogger] = None
        if enable_logging:
            self._init_logger()

    def _init_logger(self):
        """初始化团队日志器"""
        try:
            log_dir = Path.home() / ".fastapi-agent" / "log"
            log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            log_file = log_dir / f"team_run_{timestamp}.log"
            self.logger = AgentLogger(str(log_file))
            self.logger.log_event("TEAM_INIT", {
                "team_name": self.name,
                "strategy": self.strategy.value,
                "num_members": len(self.members),
                "member_names": list(self.member_map.keys())
            })
        except Exception as e:
            logger.warning(f"Failed to initialize team logger: {e}")

    def _log_interaction(
        self,
        member_name: str,
        input_msg: str,
        output_msg: str,
        step: int,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """记录成员交互"""
        interaction = MemberInteraction(
            member_name=member_name,
            input_message=input_msg,
            output_message=output_msg,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            step=step,
            metadata=metadata or {}
        )
        self.interactions.append(interaction)

        if self.logger:
            self.logger.log_event("MEMBER_INTERACTION", {
                "member": member_name,
                "step": step,
                "input_length": len(input_msg),
                "output_length": len(output_msg)
            })

    def _get_interaction_context(self) -> str:
        """获取交互历史上下文(用于成员间共享)"""
        if not self.share_interactions or not self.interactions:
            return ""

        context_lines = ["\n=== 团队成员交互历史 ===\n"]
        for interaction in self.interactions[-5:]:  # 只取最近5条
            context_lines.append(
                f"[{interaction.timestamp}] {interaction.member_name}:\n"
                f"输入: {interaction.input_message[:100]}...\n"
                f"输出: {interaction.output_message[:100]}...\n"
            )
        return "\n".join(context_lines)

    async def _run_agent_async(self, agent: Agent, message: str) -> Dict[str, Any]:
        """异步运行 Agent

        Args:
            agent: Agent 实例
            message: 任务消息

        Returns:
            包含 message 和 logs 的字典
        """
        # 添加用户消息
        agent.add_user_message(message)

        # 运行异步 agent
        result, logs = await agent.run()
        return {
            "message": result,
            "logs": logs
        }

    async def run(
        self,
        message: str,
        workspace_dir: Optional[str] = None,
        **kwargs
    ) -> TeamRunResult:
        """
        执行团队任务 (非流式)

        Args:
            message: 任务描述
            workspace_dir: 工作空间目录(可选)
            **kwargs: 其他参数

        Returns:
            TeamRunResult: 团队运行结果
        """
        workspace = workspace_dir or self.workspace_dir

        if self.logger:
            self.logger.log_event("TEAM_RUN_START", {
                "message": message,
                "strategy": self.strategy.value
            })

        try:
            if self.strategy == CoordinationStrategy.LEADER_WORKER:
                result = await self._run_leader_worker(message, workspace, **kwargs)
            elif self.strategy == CoordinationStrategy.BROADCAST:
                result = await self._run_broadcast(message, workspace, **kwargs)
            elif self.strategy == CoordinationStrategy.SEQUENTIAL:
                result = await self._run_sequential(message, workspace, **kwargs)
            elif self.strategy == CoordinationStrategy.ROUND_ROBIN:
                result = await self._run_round_robin(message, workspace, **kwargs)
            else:
                raise ValueError(f"Unsupported strategy: {self.strategy}")

            if self.logger:
                self.logger.log_event("TEAM_RUN_COMPLETE", {
                    "success": result.success,
                    "steps": result.steps,
                    "num_interactions": len(result.interactions)
                })

            return result

        except Exception as e:
            logger.error(f"Team run failed: {e}")
            if self.logger:
                self.logger.log_event("TEAM_RUN_ERROR", {"error": str(e)})
            raise

    async def _run_leader_worker(
        self,
        message: str,
        workspace_dir: str,
        **kwargs
    ) -> TeamRunResult:
        """执行 Leader-Worker 策略"""
        if not self.coordinator:
            raise ValueError("Coordinator is required for LEADER_WORKER strategy")

        member_outputs = {}
        step = 0

        # 1. 协调者分析任务并制定计划
        step += 1
        coordinator_prompt = f"""
你是团队协调者。请分析以下任务,并制定执行计划。

任务: {message}

可用团队成员:
{self._format_member_info()}

请返回 JSON 格式的执行计划:
{{
    "analysis": "任务分析",
    "plan": [
        {{
            "member": "成员名称",
            "task": "具体子任务描述",
            "dependencies": []
        }}
    ],
    "final_synthesis": "如何汇总各成员输出"
}}
"""

        coordinator_result = await self._run_agent_async(self.coordinator, coordinator_prompt)

        self._log_interaction(
            member_name=self.coordinator.name or "Coordinator",
            input_msg=coordinator_prompt,
            output_msg=coordinator_result.get("message", ""),
            step=step,
            metadata={"role": "coordinator", "phase": "planning"}
        )

        # 解析计划
        plan = self._parse_coordination_plan(coordinator_result.get("message", ""))
        logger.info(f"Coordination plan: {plan}")

        # 2. 按计划执行子任务
        for task_item in plan.get("plan", []):
            step += 1
            member_name = task_item.get("member", "")
            task_desc = task_item.get("task", "")

            if member_name not in self.member_map:
                logger.warning(f"Member {member_name} not found, skipping")
                continue

            member = self.member_map[member_name]

            # 构建成员任务(包含交互上下文)
            member_input = self._build_member_input(task_desc, task_item)

            # 执行成员任务
            member_result = await self._run_agent_async(member, member_input)
            member_output = member_result.get("message", "")
            member_outputs[member_name] = member_output

            self._log_interaction(
                member_name=member_name,
                input_msg=member_input,
                output_msg=member_output,
                step=step,
                metadata={"task": task_desc}
            )

            if step >= self.max_steps:
                logger.warning(f"Reached max steps: {self.max_steps}")
                break

        # 3. 协调者汇总结果
        step += 1
        synthesis_prompt = f"""
请汇总以下团队成员的工作成果,生成最终响应。

原始任务: {message}

成员输出:
{self._format_member_outputs(member_outputs)}

请提供完整、连贯的最终答案。
"""

        final_result = await self._run_agent_async(self.coordinator, synthesis_prompt)
        final_output = final_result.get("message", "")

        self._log_interaction(
            member_name=self.coordinator.name or "Coordinator",
            input_msg=synthesis_prompt,
            output_msg=final_output,
            step=step,
            metadata={"role": "coordinator", "phase": "synthesis"}
        )

        # 构建结果
        return TeamRunResult(
            success=True,
            final_output=final_output,
            member_outputs=member_outputs,
            interactions=self.interactions,
            steps=step,
            logs=[],  # AgentLogger 日志写入文件,不使用内存日志
            shared_state=self.shared_state,
            metadata={"plan": plan}
        )

    async def _run_broadcast(
        self,
        message: str,
        workspace_dir: str,
        **kwargs
    ) -> TeamRunResult:
        """执行 Broadcast 策略 - 将任务发送给所有成员"""
        member_outputs = {}
        step = 0

        # 1. 所有成员并行处理相同任务
        for member_name, member in self.member_map.items():
            step += 1
            member_input = self._build_member_input(message, {})

            member_result = await self._run_agent_async(member, member_input)
            member_output = member_result.get("message", "")
            member_outputs[member_name] = member_output

            self._log_interaction(
                member_name=member_name,
                input_msg=member_input,
                output_msg=member_output,
                step=step
            )

        # 2. 汇总所有成员的输出
        step += 1
        final_output = self._synthesize_outputs(message, member_outputs)

        return TeamRunResult(
            success=True,
            final_output=final_output,
            member_outputs=member_outputs,
            interactions=self.interactions,
            steps=step,
            logs=[],  # AgentLogger 日志写入文件,不使用内存日志
            shared_state=self.shared_state
        )

    async def _run_sequential(
        self,
        message: str,
        workspace_dir: str,
        **kwargs
    ) -> TeamRunResult:
        """执行 Sequential 策略 - 按顺序执行,前一个输出作为后一个输入"""
        member_outputs = {}
        current_input = message
        step = 0

        for member_name, member in self.member_map.items():
            step += 1
            member_input = self._build_member_input(current_input, {})

            member_result = await self._run_agent_async(member, member_input)
            member_output = member_result.get("message", "")
            member_outputs[member_name] = member_output

            self._log_interaction(
                member_name=member_name,
                input_msg=member_input,
                output_msg=member_output,
                step=step
            )

            # 下一个成员的输入是当前成员的输出
            current_input = member_output

        # 最后一个成员的输出就是最终输出
        final_output = current_input

        return TeamRunResult(
            success=True,
            final_output=final_output,
            member_outputs=member_outputs,
            interactions=self.interactions,
            steps=step,
            logs=[],  # AgentLogger 日志写入文件,不使用内存日志
            shared_state=self.shared_state
        )

    async def _run_round_robin(
        self,
        message: str,
        workspace_dir: str,
        **kwargs
    ) -> TeamRunResult:
        """执行 Round-Robin 策略 - 轮询分配任务"""
        # 简化实现: 类似顺序执行,但可以扩展为更复杂的轮询逻辑
        return self._run_sequential(message, workspace_dir, **kwargs)

    def _build_member_input(self, task: str, task_item: Dict[str, Any]) -> str:
        """构建成员输入(包含上下文)"""
        parts = []

        if self.share_interactions:
            interaction_context = self._get_interaction_context()
            if interaction_context:
                parts.append(interaction_context)

        parts.append(f"\n你的任务: {task}\n")

        return "\n".join(parts)

    def _format_member_info(self) -> str:
        """格式化成员信息"""
        lines = []
        for name, member in self.member_map.items():
            # 获取成员的工具信息
            tools = getattr(member, 'tools', [])
            tool_names = [getattr(t, 'name', str(t)) for t in tools] if tools else []
            lines.append(f"- {name}: {', '.join(tool_names) if tool_names else '通用助手'}")
        return "\n".join(lines)

    def _format_member_outputs(self, outputs: Dict[str, Any]) -> str:
        """格式化成员输出"""
        lines = []
        for member, output in outputs.items():
            lines.append(f"\n{member}:\n{output}\n")
        return "\n".join(lines)

    def _parse_coordination_plan(self, coordinator_output: str) -> Dict[str, Any]:
        """解析协调计划"""
        try:
            # 尝试从输出中提取 JSON
            if "```json" in coordinator_output:
                json_str = coordinator_output.split("```json")[1].split("```")[0].strip()
            elif "```" in coordinator_output:
                json_str = coordinator_output.split("```")[1].split("```")[0].strip()
            else:
                json_str = coordinator_output

            plan = json.loads(json_str)
            return plan
        except Exception as e:
            logger.warning(f"协调计划解析失败: {e}, 使用回退方案")
            # 回退: 顺序分配给所有成员
            return {
                "analysis": "自动生成的计划",
                "plan": [
                    {"member": name, "task": "协助完成任务", "dependencies": []}
                    for name in self.member_map.keys()
                ],
                "final_synthesis": "汇总所有成员输出"
            }

    def _synthesize_outputs(self, original_task: str, outputs: Dict[str, Any]) -> str:
        """简单汇总输出(不使用 LLM)"""
        lines = [f"团队完成任务: {original_task}\n", "\n成员贡献:\n"]
        for member, output in outputs.items():
            lines.append(f"\n{member}: {output}\n")
        return "\n".join(lines)
