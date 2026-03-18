"""记忆系统 Hook，集成到 Agent 执行流程。"""

import json
import logging
import uuid
from typing import Any, Optional

from omni_agent.core.hooks import AgentHook, HookContext
from omni_agent.core.memory import Memory
from omni_agent.core.memory_vector import MemoryVectorStore

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = """分析以下对话，提取需要长期记忆的信息。

对话内容：
用户: {user_msg}
助手: {assistant_msg}

当前用户画像：
{current_profile}

当前用户习惯：
{current_habit}

提取规则：
1. profile_update (用户画像增量): 用户的职业、背景、技能、偏好、身份等新信息
   - 不要重复已有画像中的内容
   - 只提取新发现的信息
   - 用 markdown 列表格式，每条以 "- " 开头

2. habit_update (习惯增量): 用户的工作流程、操作习惯等新信息
   - 不要重复已有习惯中的内容
   - 用 markdown 列表格式，每条以 "- " 开头

3. context_update (会话上下文): 本轮对话的关键信息摘要
   - 简要记录本轮做了什么、结论是什么

要求：
- 只提取明确提到的信息
- 与已有内容重复的不要提取
- 没有新信息的字段返回 null

返回JSON格式：
{{
  "profile_update": "- 新条目1\\n- 新条目2" | null,
  "habit_update": "- 新条目1" | null,
  "context_update": "简要摘要文本" | null
}}

只返回JSON。"""


class MemoryHook(AgentHook):
    """记忆 Hook，在 Agent 执行前后自动处理记忆。

    - before_run: 加载记忆上下文
    - after_run: 提取 profile/habit/context 增量并写入 .md 文件
    """

    priority: int = 50
    SIMILARITY_THRESHOLD: float = 0.75

    def __init__(
        self,
        user_id: str,
        session_id: str,
        base_dir: str = "./.agent_memories",
        llm_client: Any | None = None,
        enable_vector_dedup: bool = True,
    ) -> None:
        self.memory = Memory(user_id, session_id, base_dir)
        self._user_id = user_id
        self._session_id = session_id
        self._last_user_msg = ""
        self._llm_client = llm_client
        self._enable_vector_dedup = enable_vector_dedup
        self._embedding_service: Any | None = None
        self._vector_store: MemoryVectorStore | None = None

    def _get_embedding_service(self) -> Any | None:
        if self._embedding_service is None and self._enable_vector_dedup:
            try:
                from omni_agent.rag.embedding_service import embedding_service
                self._embedding_service = embedding_service
            except Exception as e:
                logger.warning(f"加载 embedding 服务失败: {e}")
                self._enable_vector_dedup = False
        return self._embedding_service

    def _get_vector_store(self) -> MemoryVectorStore | None:
        if self._vector_store is None and self._enable_vector_dedup:
            try:
                self._vector_store = MemoryVectorStore(self._user_id, self._session_id)
            except Exception as e:
                logger.warning(f"创建向量存储失败: {e}")
                self._enable_vector_dedup = False
        return self._vector_store

    async def before_run(self, ctx: HookContext) -> None:
        if not self.memory.exists():
            task = ""
            if hasattr(ctx, "state") and ctx.state.messages:
                for msg in ctx.state.messages:
                    if msg.role == "user":
                        content = msg.content
                        if isinstance(content, str):
                            task = content[:200]
                        break
            self.memory.init_memory(task=task)

    async def on_step(self, ctx: HookContext, step_data: dict[str, Any]) -> None:
        pass

    async def after_run(self, ctx: HookContext, result: str, success: bool) -> None:
        logger.info(f"MemoryHook.after_run called, success={success}")
        if not hasattr(ctx, "state"):
            logger.warning("MemoryHook: ctx has no state")
            return

        user_msg = ""
        for msg in reversed(ctx.state.messages):
            if msg.role == "user" and msg.content:
                user_msg = msg.content if isinstance(msg.content, str) else str(msg.content)
                break

        if user_msg and user_msg != self._last_user_msg:
            self._last_user_msg = user_msg
            self.memory.increment_round()

            if self._llm_client:
                await self._extract_and_store_memories(user_msg, result)

    async def _index_to_vector(self, memory_type: str, content: str) -> None:
        embedding_service = self._get_embedding_service()
        vector_store = self._get_vector_store()

        if not embedding_service or not vector_store or not self._enable_vector_dedup:
            return

        try:
            embedding = await embedding_service.embed_text(content)

            similar = await vector_store.find_similar(
                embedding=embedding,
                memory_type=memory_type,
                threshold=self.SIMILARITY_THRESHOLD,
                top_k=1,
            )
            if similar:
                logger.debug(f"跳过重复 {memory_type} 记忆: {content[:50]}")
                return

            memory_id = uuid.uuid4().hex[:12]
            session_id = "__user__" if memory_type in ("profile", "habit") else self._session_id
            store = MemoryVectorStore(self._user_id, session_id)
            await store.add(memory_id, content, memory_type, embedding)

        except Exception as e:
            logger.warning(f"向量索引失败: {e}")

    async def _extract_and_store_memories(self, user_msg: str, assistant_msg: str) -> None:
        try:
            from omni_agent.schemas.message import Message

            current_profile = self.memory.read_profile().strip() or "无"
            current_habit = self.memory.read_habit().strip() or "无"

            prompt = EXTRACT_PROMPT.format(
                user_msg=user_msg[:500],
                assistant_msg=assistant_msg[:500],
                current_profile=current_profile[:500],
                current_habit=current_habit[:500],
            )

            response = await self._llm_client.generate(
                messages=[Message(role="user", content=prompt)],
                tools=None,
            )

            if not response.content:
                return

            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()

            extracted = json.loads(content)

            profile_update = extracted.get("profile_update")
            if profile_update:
                self.memory.append_profile(profile_update)
                await self._index_to_vector("profile", profile_update)

            habit_update = extracted.get("habit_update")
            if habit_update:
                self.memory.append_habit(habit_update)
                await self._index_to_vector("habit", habit_update)

            context_update = extracted.get("context_update")
            if context_update:
                round_count = self.memory.round_count
                self.memory.append_context(f"\n## Round {round_count}\n\n{context_update}")

        except Exception as e:
            logger.debug(f"记忆提取失败: {e}")

    def get_context_for_prompt(self) -> str:
        return self.memory.get_context_for_prompt()

    def get_memory(self) -> Memory:
        return self.memory


def create_memory_hook(
    user_id: str | None,
    session_id: str | None,
    base_dir: str = "./.agent_memories",
    llm_client: Any | None = None,
    enable_vector_dedup: bool = True,
) -> Optional["MemoryHook"]:
    if not user_id or not session_id:
        return None
    return MemoryHook(
        user_id,
        session_id,
        base_dir,
        llm_client,
        enable_vector_dedup,
    )
