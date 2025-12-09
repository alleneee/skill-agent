"""Team orchestration for multi-agent collaboration."""

import asyncio
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi_agent.core.agent import Agent
from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.core.run_context import RunContext
from fastapi_agent.core.session_manager import UnifiedTeamSessionManager
from fastapi_agent.core.trace_logger import TraceLogger, get_current_trace, set_current_trace
from fastapi_agent.schemas.team import (
    TeamConfig,
    TeamMemberConfig,
    MemberRunResult,
    TeamRunResponse,
    TaskWithDependencies,
    DependencyRunResponse,
)
from fastapi_agent.tools.base import Tool
from fastapi_agent.tools.function_tool import create_tool_from_function
from fastapi_agent.tools.spawn_agent_tool import SpawnAgentTool


class Team:
    """Team of agents that can collaborate on tasks."""

    def __init__(
        self,
        config: TeamConfig,
        llm_client: LLMClient,
        available_tools: Optional[List[Tool]] = None,
        workspace_dir: str = "./workspace",
        session_manager: Optional[UnifiedTeamSessionManager] = None,
        enable_spawn_agent: bool = True,
        spawn_agent_max_depth: int = 3,
        spawn_agent_default_max_steps: int = 15,
        spawn_agent_token_limit: int = 50000,
        current_depth: int = 0,  # Depth tracking for nested Team/SpawnAgent
    ):
        self.config = config
        self.llm_client = llm_client
        self.available_tools = available_tools or []
        self.workspace_dir = workspace_dir
        self.team_id = str(uuid4())
        self.session_manager = session_manager or UnifiedTeamSessionManager()

        # Spawn Agent configuration
        self.enable_spawn_agent = enable_spawn_agent
        self.spawn_agent_max_depth = spawn_agent_max_depth
        self.spawn_agent_default_max_steps = spawn_agent_default_max_steps
        self.spawn_agent_token_limit = spawn_agent_token_limit
        self.current_depth = current_depth  # Team execution counts as depth

        # Track member runs (for current execution)
        self.member_runs: List[MemberRunResult] = []
        self.iteration_count = 0
        self._current_run_id: Optional[str] = None  # Track current leader run ID

    def _build_leader_system_prompt(self, history_context: str = "") -> str:
        """Build system prompt for team leader using structured format (inspired by agno).

        Args:
            history_context: Optional formatted history from previous runs

        Returns:
            Complete system prompt for the leader agent
        """
        # Build team members section
        members_desc = []
        for idx, member in enumerate(self.config.members, 1):
            tools_list = "\n    - ".join(member.tools) if member.tools else "(no tools)"

            member_entry = f""" - Agent {idx}:
   - ID: {member.id}
   - Name: {member.name}
   - Role: {member.role}"""

            if member.tools:
                member_entry += f"\n   - Member tools:\n    - {tools_list}"
            else:
                member_entry += f"\n   - Member tools: {tools_list}"

            if member.instructions:
                member_entry += f"\n   - Instructions: {member.instructions}"

            members_desc.append(member_entry)

        members_info = "\n".join(members_desc)

        # Build how_to_respond section
        if self.config.delegate_to_all:
            delegation_method = """- You cannot use a member tool directly. You can only delegate tasks to members.
- Use the `delegate_task_to_all_members` tool to send the task to ALL team members.
- When you delegate a task, provide a clear description of the task.
- You must always analyze the responses from members before responding to the user.
- After analyzing the responses from the members, if you feel the task has been completed, you can stop and respond to the user.
- If you are NOT satisfied with the responses from the members, you should re-assign the task."""
        else:
            delegation_method = """- Your role is to delegate tasks to members in your team with the highest likelihood of completing the user's request.
- Carefully analyze the tools available to the members and their roles before delegating tasks.
- You cannot use a member tool directly. You can only delegate tasks to members.
- When you delegate a task to another member, make sure to include:
  - member_id (str): The ID of the member to delegate the task to. Use only the ID of the member.
  - task (str): A clear description of the task. Determine the best way to describe the task to the member.
- You can delegate tasks to multiple members at once.
- You must always analyze the responses from members before responding to the user.
- After analyzing the responses from the members, if you feel the task has been completed, you can stop and respond to the user.
- If you are NOT satisfied with the responses from the members, you should re-assign the task to a different member.
- For simple greetings, thanks, or questions about the team itself, you should respond directly.
- For all work requests, tasks, or questions requiring expertise, route to appropriate team members."""

        # Build the structured prompt
        system_prompt = f"""You are the leader of a team of AI Agents.

Your task is to coordinate the team to complete the user's request.

<team_name>
{self.config.name}
</team_name>

<team_description>
{self.config.description or 'A collaborative team of specialized agents'}
</team_description>

<team_members>
{members_info}
</team_members>

<how_to_respond>
{delegation_method}
</how_to_respond>"""

        # Add custom leader instructions if provided
        if self.config.leader_instructions:
            system_prompt += f"""

<instructions>
{self.config.leader_instructions}
</instructions>"""

        # Add history context if available
        if history_context:
            system_prompt += f"""

<previous_interactions>
{history_context}

Use the previous interactions to maintain continuity and context.
</previous_interactions>"""

        return system_prompt

    async def _run_member(
        self,
        member_config: TeamMemberConfig,
        task: str,
        session_id: Optional[str] = None,
        depth: int = 1
    ) -> MemberRunResult:
        """Run a specific team member on a task."""
        trace = get_current_trace()
        if trace:
            trace.log_agent_start(
                member_config.name,
                member_config.role,
                task,
                parent_agent="Leader",
                depth=depth
            )

        try:
            member_tools = []
            if member_config.tools:
                for tool in self.available_tools:
                    if tool.name in member_config.tools:
                        member_tools.append(tool)

                # Add SpawnAgentTool if member has it in their tools and it's enabled
                if (self.enable_spawn_agent and
                    "spawn_agent" in member_config.tools and
                    self.current_depth < self.spawn_agent_max_depth):

                    # Create parent tools dict for spawn agent (member's other tools)
                    parent_tools = {t.name: t for t in member_tools}

                    spawn_tool = SpawnAgentTool(
                        llm_client=self.llm_client,
                        parent_tools=parent_tools,
                        workspace_dir=self.workspace_dir,
                        current_depth=self.current_depth + 1,  # Team member is depth + 1
                        max_depth=self.spawn_agent_max_depth,
                        default_max_steps=self.spawn_agent_default_max_steps,
                        default_token_limit=self.spawn_agent_token_limit,
                    )
                    member_tools.append(spawn_tool)

            # Create member-specific system prompt
            system_prompt = f"""You are {member_config.name}, a {member_config.role}.

{member_config.instructions or ''}

Focus on your area of expertise and provide clear, actionable responses.
"""

            # Create agent for this member
            member_agent = Agent(
                llm_client=self.llm_client,
                tools=member_tools,
                system_prompt=system_prompt,
                workspace_dir=self.workspace_dir,
                max_steps=10,  # Limit steps for members
                enable_logging=False  # Don't create separate logs for members
            )

            member_agent.add_user_message(task)
            response_content, logs = await member_agent.run()

            steps = len([log for log in logs if log.get("type") == "step"])
            max_steps_reached = any(log.get("type") == "max_steps_reached" for log in logs)
            llm_failed = response_content and response_content.startswith("LLM call failed")
            success = bool(response_content) and not max_steps_reached and not llm_failed

            input_tokens = 0
            output_tokens = 0
            for log in logs:
                if log.get("type") in ("completion", "max_steps_reached"):
                    input_tokens = log.get("total_input_tokens", 0)
                    output_tokens = log.get("total_output_tokens", 0)
                    break

            result = MemberRunResult(
                member_name=member_config.name,
                member_role=member_config.role,
                task=task,
                response=response_content,
                success=success,
                steps=steps,
                metadata={"input_tokens": input_tokens, "output_tokens": output_tokens}
            )

            if trace:
                trace.log_agent_end(member_config.name, success, response_content, steps, input_tokens, output_tokens)

            self.member_runs.append(result)

            # Save to session if session_id provided
            if session_id and self._current_run_id:
                member_run_record = RunRecord(
                    run_id=str(uuid4()),
                    parent_run_id=self._current_run_id,  # Link to leader run
                    runner_type="member",
                    runner_name=member_config.name,
                    task=task,
                    response=result.response,
                    success=result.success,
                    steps=result.steps,
                    timestamp=time.time(),
                    metadata={"role": member_config.role, "logs": logs}
                )
                await self.session_manager.add_run(session_id, member_run_record)

            return result

        except Exception as e:
            if trace:
                trace.log_agent_end(member_config.name, False, str(e), 0)

            result = MemberRunResult(
                member_name=member_config.name,
                member_role=member_config.role,
                task=task,
                response="",
                success=False,
                error=str(e),
                steps=0
            )
            self.member_runs.append(result)

            # Save error to session if session_id provided
            if session_id and self._current_run_id:
                member_run_record = RunRecord(
                    run_id=str(uuid4()),
                    parent_run_id=self._current_run_id,
                    runner_type="member",
                    runner_name=member_config.name,
                    task=task,
                    response=f"Error: {str(e)}",
                    success=False,
                    steps=0,
                    timestamp=time.time(),
                    metadata={"role": member_config.role, "error": str(e)}
                )
                await self.session_manager.add_run(session_id, member_run_record)

            return result

    async def run(
        self,
        message: str,
        max_steps: int = 50,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        num_history_runs: int = 3,
        run_context: Optional[RunContext] = None,
    ) -> TeamRunResponse:
        """Run the team on a task.

        Args:
            message: Task message for the team
            max_steps: Maximum steps for leader agent (default: 50)
            session_id: Session ID for conversation continuity (optional)
            user_id: User ID for tracking (optional)
            num_history_runs: Number of history runs to include in context (default: 3)
            run_context: Internal parameter for framework use only. Users should use
                session_id/user_id parameters instead. This is mainly used for internal
                context passing between Team and member Agents.

        Returns:
            TeamRunResponse with execution results

        Example:
            >>> # ✅ Recommended: Use independent parameters
            >>> response = await team.run(
            ...     message="Research Python asyncio and create documentation",
            ...     session_id="user-session-123",
            ...     user_id="user-456",
            ...     max_steps=50
            ... )

            >>> # ❌ Not recommended: Manually creating RunContext
            >>> # Users should not manually create RunContext
            >>> # The framework handles this automatically

        Note:
            - RunContext is created automatically from session_id/user_id if not provided
            - run_context parameter is mainly for internal framework use
            - See docs/RUNCONTEXT_DESIGN.md for design rationale
        """
        self.member_runs = []
        self.iteration_count = 0

        # Initialize or create run context
        if run_context is None:
            self._current_run_id = str(uuid4())
            run_context = RunContext(
                run_id=self._current_run_id,
                session_id=session_id or str(uuid4()),
                user_id=user_id,
            )
        else:
            self._current_run_id = run_context.run_id

        trace = TraceLogger()
        trace.start_trace("team", {
            "team_name": self.config.name,
            "members": [m.name for m in self.config.members]
        })
        set_current_trace(trace)

        try:
            trace.log_agent_start("Leader", "Team Leader", message, depth=0)

            history_context = ""
            if run_context.session_id:
                session = await self.session_manager.get_session(
                    session_id=run_context.session_id,
                    team_name=self.config.name,
                    user_id=run_context.user_id
                )
                history_context = session.get_history_context(num_runs=num_history_runs)

            # Create leader agent with history context
            system_prompt = self._build_leader_system_prompt(history_context=history_context)

            # Create delegation tool dynamically (closure captures run_context)
            if self.config.delegate_to_all:
                async def delegate_task_to_all_members(task: str) -> str:
                    """Delegate a task to ALL team members at once.

                    Use this to get diverse perspectives or brainstorm ideas by sending
                    the same task to all members simultaneously.

                    Args:
                        task: Clear description of the task to delegate

                    Returns:
                        Combined responses from all team members
                    """
                    results = []
                    for member in self.config.members:
                        member_result = await self._run_member(
                            member, task, session_id=run_context.session_id
                        )
                        results.append(f"{member.name}: {member_result.response}")
                    return "\n\n".join(results)

                delegate_tool = create_tool_from_function(delegate_task_to_all_members)
            else:
                async def delegate_task_to_member(member_id: str, task: str) -> str:
                    """Delegate a task to a specific team member by their ID.

                    Use this to assign work to the team member best suited for the task.
                    Available members and their IDs are listed in the team_members section.

                    Args:
                        member_id: ID of the team member to delegate to (e.g., 'hn_researcher', 'article_reader')
                        task: Clear description of the task to delegate

                    Returns:
                        The member's response to the delegated task
                    """
                    # Find member by ID
                    member_config = None
                    for m in self.config.members:
                        if m.id == member_id:
                            member_config = m
                            break

                    if not member_config:
                        return f"Error: Member with ID '{member_id}' not found in team. Available members: {', '.join([m.id for m in self.config.members])}"

                    # Execute member run
                    result = await self._run_member(
                        member_config, task, session_id=run_context.session_id
                    )

                    if result.success:
                        return f"{member_config.name} completed task:\n{result.response}"
                    else:
                        return f"{member_config.name} failed: {result.error}"

                delegate_tool = create_tool_from_function(
                    delegate_task_to_member,
                    parameters={
                        "type": "object",
                        "properties": {
                            "member_id": {
                                "type": "string",
                                "enum": [m.id for m in self.config.members],
                                "description": f"ID of the team member to delegate to. Available: {', '.join([f'{m.id} ({m.name})' for m in self.config.members])}"
                            },
                            "task": {
                                "type": "string",
                                "description": "Clear description of the task to delegate"
                            }
                        },
                        "required": ["member_id", "task"]
                    }
                )

            leader_tools = [delegate_tool]

            leader = Agent(
                llm_client=self.llm_client,
                tools=leader_tools,
                system_prompt=system_prompt,
                workspace_dir=self.workspace_dir,
                max_steps=max_steps,
                enable_logging=True
            )

            # Add task message and run the leader
            leader.add_user_message(message)
            response_content, logs = await leader.run()

            leader_steps = len([log for log in logs if log.get("type") == "step"])
            total_steps = leader_steps
            for member_run in self.member_runs:
                total_steps += member_run.steps

            leader_input_tokens = 0
            leader_output_tokens = 0
            for log in logs:
                if log.get("type") in ("completion", "max_steps_reached"):
                    leader_input_tokens = log.get("total_input_tokens", 0)
                    leader_output_tokens = log.get("total_output_tokens", 0)
                    break

            max_steps_reached = any(log.get("type") == "max_steps_reached" for log in logs)
            llm_failed = response_content and response_content.startswith("LLM call failed")
            success = bool(response_content) and not max_steps_reached and not llm_failed

            if run_context.session_id:
                leader_run_record = RunRecord(
                    run_id=self._current_run_id,
                    parent_run_id=None,  # Leader has no parent
                    runner_type="team_leader",
                    runner_name=self.config.name,
                    task=message,
                    response=response_content,
                    success=success,
                    steps=total_steps,
                    timestamp=time.time(),
                    metadata={
                        "logs": logs,
                        "member_count": len(self.member_runs)
                    }
                )
                await self.session_manager.add_run(run_context.session_id, leader_run_record)

            trace.log_agent_end("Leader", success, response_content, leader_steps, leader_input_tokens, leader_output_tokens)
            trace.end_trace(success=success, result=response_content)
            set_current_trace(None)

            return TeamRunResponse(
                success=success,
                team_name=self.config.name,
                message=response_content,
                member_runs=self.member_runs,
                total_steps=total_steps,
                iterations=len(self.member_runs),
                metadata={
                    "session_id": run_context.session_id,
                    "run_id": self._current_run_id,
                    "trace_id": trace.trace_id,
                    "input_tokens": leader_input_tokens,
                    "output_tokens": leader_output_tokens,
                }
            )

        except Exception as e:
            trace.log_agent_end("Leader", False, str(e), 0)
            trace.end_trace(success=False, result=str(e))
            set_current_trace(None)

            if run_context.session_id:
                error_run_record = RunRecord(
                    run_id=self._current_run_id,
                    parent_run_id=None,
                    runner_type="team_leader",
                    runner_name=self.config.name,
                    task=message,
                    response=f"Error: {str(e)}",
                    success=False,
                    steps=0,
                    timestamp=time.time(),
                    metadata={"error": str(e)}
                )
                await self.session_manager.add_run(run_context.session_id, error_run_record)

            return TeamRunResponse(
                success=False,
                team_name=self.config.name,
                message=f"Team execution failed: {str(e)}",
                member_runs=self.member_runs,
                total_steps=0,
                iterations=len(self.member_runs),
                metadata={"error": str(e), "run_id": self._current_run_id, "trace_id": trace.trace_id}
            )

    def _resolve_dependencies(
        self, tasks: List[TaskWithDependencies]
    ) -> List[List[TaskWithDependencies]]:
        """Resolve task dependencies using topological sort.

        Args:
            tasks: List of tasks with dependencies

        Returns:
            List of task layers (each layer can be executed in parallel)

        Raises:
            ValueError: If circular dependencies detected
        """
        task_map = {task.id: task for task in tasks}
        in_degree = {task.id: len(task.depends_on) for task in tasks}

        for task in tasks:
            for dep_id in task.depends_on:
                if dep_id not in task_map:
                    raise ValueError(f"Task '{task.id}' depends on non-existent task '{dep_id}'")

        layers = []
        remaining = set(task.id for task in tasks)

        while remaining:
            current_layer = [
                task_map[task_id]
                for task_id in remaining
                if in_degree[task_id] == 0
            ]

            if not current_layer:
                raise ValueError(f"Circular dependency detected among tasks: {remaining}")

            layers.append(current_layer)

            for task in current_layer:
                remaining.remove(task.id)
                for other_id in remaining:
                    if task.id in task_map[other_id].depends_on:
                        in_degree[other_id] -= 1

        return layers

    async def _execute_task_with_context(
        self,
        task: TaskWithDependencies,
        completed_results: Dict[str, str],
        session_id: Optional[str] = None,
        layer: int = 0,
    ) -> TaskWithDependencies:
        """Execute a single task with context from completed dependencies."""
        task.status = "running"
        start_time = time.time()

        try:
            member_config = None
            for m in self.config.members:
                if m.role == task.assigned_to:
                    member_config = m
                    break

            if not member_config:
                task.status = "failed"
                task.result = f"Error: No member with role '{task.assigned_to}' found"
                return task

            task_description = task.task
            if task.depends_on:
                context_parts = ["\n\n依赖任务结果:"]
                for dep_id in task.depends_on:
                    if dep_id in completed_results:
                        context_parts.append(f"\n[{dep_id}]: {completed_results[dep_id]}")
                task_description += "".join(context_parts)

            member_result = await self._run_member(
                member_config, task_description, session_id=session_id
            )

            if member_result.success:
                task.status = "completed"
                task.result = member_result.response
            else:
                task.status = "failed"
                task.result = member_result.error or "Unknown error"

            elapsed = time.time() - start_time
            task.metadata = {
                "member_name": member_result.member_name,
                "steps": member_result.steps,
                "logs": member_result.metadata.get("logs", []),
                "elapsed": elapsed,
            }

            trace = get_current_trace()
            if trace:
                trace.log_task_end(task.id, task.status, task.result, elapsed)

            return task

        except Exception as e:
            elapsed = time.time() - start_time
            task.status = "failed"
            task.result = f"Execution error: {str(e)}"

            trace = get_current_trace()
            if trace:
                trace.log_task_end(task.id, "failed", str(e), elapsed)

            return task

    async def run_with_dependencies(
        self,
        tasks: List[TaskWithDependencies],
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> DependencyRunResponse:
        """Execute tasks with dependency relationships."""
        self._current_run_id = str(uuid4())

        trace = TraceLogger()
        trace.start_trace("dependency_workflow", {
            "team_name": self.config.name,
            "task_count": len(tasks),
            "task_ids": [t.id for t in tasks]
        })
        set_current_trace(trace)

        try:
            layers = self._resolve_dependencies(tasks)
            execution_order = [[task.id for task in layer] for layer in layers]

            completed_results = {}
            total_steps = 0

            for layer_idx, layer in enumerate(layers):
                for task in layer:
                    trace.log_task_start(
                        task.id, task.task, task.assigned_to, task.depends_on, layer_idx
                    )

                layer_results = await asyncio.gather(*[
                    self._execute_task_with_context(task, completed_results, session_id, layer_idx)
                    for task in layer
                ])

                for task in layer_results:
                    completed_results[task.id] = task.result or ""
                    total_steps += task.metadata.get("steps", 0)

                    if task.status == "failed":
                        remaining_tasks = []
                        for remaining_layer in layers[layer_idx + 1:]:
                            remaining_tasks.extend(remaining_layer)

                        for remaining_task in remaining_tasks:
                            remaining_task.status = "skipped"
                            remaining_task.result = f"Skipped due to dependency failure: {task.id}"

                        final_message = f"执行失败：任务 '{task.id}' 执行失败\n\n失败详情:\n{task.result}"

                        trace.end_trace(success=False, result=final_message)
                        set_current_trace(None)

                        if session_id:
                            await self._save_dependency_run_to_session(
                                session_id=session_id,
                                tasks=tasks,
                                final_message=final_message,
                                success=False,
                                total_steps=total_steps,
                            )

                        return DependencyRunResponse(
                            success=False,
                            team_name=self.config.name,
                            message=final_message,
                            tasks=tasks,
                            execution_order=execution_order,
                            total_steps=total_steps,
                            metadata={"run_id": self._current_run_id, "failed_task": task.id, "trace_id": trace.trace_id},
                        )

            completed_tasks = [t for t in tasks if t.status == "completed"]
            final_message = f"所有任务执行完成 ({len(completed_tasks)}/{len(tasks)})\n\n执行结果:\n"
            for task in tasks:
                final_message += f"\n[{task.id}] {task.status}: {task.result[:200]}..."

            trace.end_trace(success=True, result=final_message)
            set_current_trace(None)

            if session_id:
                await self._save_dependency_run_to_session(
                    session_id=session_id,
                    tasks=tasks,
                    final_message=final_message,
                    success=True,
                    total_steps=total_steps,
                )

            return DependencyRunResponse(
                success=True,
                team_name=self.config.name,
                message=final_message,
                tasks=tasks,
                execution_order=execution_order,
                total_steps=total_steps,
                metadata={"run_id": self._current_run_id, "trace_id": trace.trace_id},
            )

        except Exception as e:
            error_message = f"依赖执行失败: {str(e)}"

            trace.end_trace(success=False, result=error_message)
            set_current_trace(None)

            if session_id:
                await self._save_dependency_run_to_session(
                    session_id=session_id,
                    tasks=tasks,
                    final_message=error_message,
                    success=False,
                    total_steps=0,
                )

            return DependencyRunResponse(
                success=False,
                team_name=self.config.name,
                message=error_message,
                tasks=tasks,
                execution_order=[],
                total_steps=0,
                metadata={"error": str(e), "run_id": self._current_run_id, "trace_id": trace.trace_id},
            )

    async def _save_dependency_run_to_session(
        self,
        session_id: str,
        tasks: List[TaskWithDependencies],
        final_message: str,
        success: bool,
        total_steps: int,
    ) -> None:
        """Save dependency run results to session."""
        run_record = RunRecord(
            run_id=self._current_run_id,
            parent_run_id=None,
            runner_type="team_dependency",
            runner_name=self.config.name,
            task=f"Dependency-based execution with {len(tasks)} tasks",
            response=final_message,
            success=success,
            steps=total_steps,
            timestamp=time.time(),
            metadata={
                "tasks": [task.model_dump() for task in tasks],
                "task_count": len(tasks),
            },
        )
        await self.session_manager.add_run(session_id, run_record)
