"""Token management for message history with automatic summarization."""

from typing import Any

import tiktoken

from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.schemas.message import Message


class TokenManager:
    """Manages token counting and message history summarization.

    Features:
    - Accurate token counting using tiktoken (cl100k_base encoder)
    - Automatic message history summarization when rounds exceed threshold
    - Preserves user messages while summarizing agent execution rounds
    - Extracts core memory for context continuity
    - Fallback to character-based estimation if tiktoken is unavailable
    """

    def __init__(
        self,
        llm_client: LLMClient,
        token_limit: int = 120000,  # Default for claude-3-5-sonnet (200k context)
        enable_summarization: bool = True,
        summarize_after_rounds: int = 2,  # 超过 N 轮后触发压缩
    ):
        """Initialize Token Manager.

        Args:
            llm_client: LLM client for generating summaries
            token_limit: Maximum tokens before triggering summarization
            enable_summarization: Whether to enable automatic summarization
            summarize_after_rounds: Number of rounds after which to trigger compression
        """
        self.llm = llm_client
        self.token_limit = token_limit
        self.enable_summarization = enable_summarization
        self.summarize_after_rounds = summarize_after_rounds
        
        # 核心记忆存储（跨轮次保持）
        self.core_memory: str = ""

        # Initialize tiktoken encoder
        try:
            self.encoding = tiktoken.get_encoding("cl100k_base")
            self.tiktoken_available = True
        except Exception:
            self.encoding = None
            self.tiktoken_available = False

    def estimate_tokens(self, messages: list[Message]) -> int:
        """Accurately calculate token count for message history using tiktoken.

        Uses cl100k_base encoder (GPT-4/Claude/MiniMax compatible).
        Falls back to character-based estimation if tiktoken is unavailable.

        Args:
            messages: List of messages to count tokens for

        Returns:
            Estimated token count
        """
        if not self.tiktoken_available:
            return self._estimate_tokens_fallback(messages)

        total_tokens = 0

        for msg in messages:
            # Count text content
            if isinstance(msg.content, str):
                total_tokens += len(self.encoding.encode(msg.content))
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict):
                        # Convert dict to string for calculation
                        total_tokens += len(self.encoding.encode(str(block)))

            # Count thinking (if present)
            if msg.thinking:
                total_tokens += len(self.encoding.encode(msg.thinking))

            # Count tool_calls (if present)
            if msg.tool_calls:
                total_tokens += len(self.encoding.encode(str(msg.tool_calls)))

            # Metadata overhead per message (approximately 4 tokens)
            total_tokens += 4

        return total_tokens

    def _estimate_tokens_fallback(self, messages: list[Message]) -> int:
        """Fallback token estimation method (when tiktoken is unavailable).

        Uses character-based estimation: ~2.5 characters = 1 token

        Args:
            messages: List of messages to count tokens for

        Returns:
            Estimated token count
        """
        total_chars = 0
        for msg in messages:
            if isinstance(msg.content, str):
                total_chars += len(msg.content)
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict):
                        total_chars += len(str(block))

            if msg.thinking:
                total_chars += len(msg.thinking)

            if msg.tool_calls:
                total_chars += len(str(msg.tool_calls))

        # Rough estimation: average 2.5 characters = 1 token
        return int(total_chars / 2.5)

    async def maybe_summarize_messages(self, messages: list[Message]) -> list[Message]:
        """Summarize message history based on rounds or token limit.

        触发条件（满足任一即触发）：
        1. 对话轮次超过 summarize_after_rounds（默认 2 轮）
        2. Token 数量超过 token_limit

        策略：
        - 压缩早期轮次，提取核心记忆
        - 保留最近 1 轮的完整对话
        - 核心记忆作为上下文传递

        Args:
            messages: Current message history

        Returns:
            Summarized message history (or original if no summarization needed)
        """
        if not self.enable_summarization:
            return messages

        # 统计对话轮次（user 消息数量，排除 system）
        user_indices = [i for i, msg in enumerate(messages) if msg.role == "user" and i > 0]
        num_rounds = len(user_indices)
        estimated_tokens = self.estimate_tokens(messages)

        # 检查是否需要压缩：轮次超过阈值 或 token 超限
        need_compress = (
            num_rounds > self.summarize_after_rounds or 
            estimated_tokens > self.token_limit
        )

        if not need_compress:
            return messages

        print(f"\n📊 对话轮次: {num_rounds}, Token: {estimated_tokens}/{self.token_limit}")
        print("🔄 触发记忆压缩...")

        # 至少需要 2 轮才能压缩
        if num_rounds < 2:
            return messages

        # 压缩策略：保留最近 1 轮完整对话，压缩之前的轮次为核心记忆
        rounds_to_compress = num_rounds - 1  # 压缩除最后一轮外的所有轮次
        
        # 收集需要压缩的消息
        compress_end_idx = user_indices[-1]  # 最后一个 user 消息之前的所有内容
        messages_to_compress = messages[1:compress_end_idx]  # 排除 system prompt
        
        if not messages_to_compress:
            return messages

        # 生成核心记忆
        core_memory = await self._extract_core_memory(messages_to_compress, rounds_to_compress)
        
        if core_memory:
            self.core_memory = core_memory  # 保存核心记忆
        
        # 构建新的消息列表
        new_messages = [messages[0]]  # system prompt
        
        # 注入核心记忆
        if self.core_memory:
            memory_message = Message(
                role="user",
                content=f"[对话历史核心记忆]\n{self.core_memory}\n\n请基于以上历史上下文继续对话。",
            )
            new_messages.append(memory_message)
            # 添加一个确认消息
            new_messages.append(Message(
                role="assistant",
                content="好的，我已了解之前的对话内容，请继续。",
            ))
        
        # 添加最近一轮的完整对话
        new_messages.extend(messages[compress_end_idx:])

        new_tokens = self.estimate_tokens(new_messages)
        print(f"✓ 记忆压缩完成: {estimated_tokens} → {new_tokens} tokens")
        print(f"  压缩了 {rounds_to_compress} 轮对话，保留最近 1 轮")

        return new_messages
    
    async def _extract_core_memory(self, messages: list[Message], num_rounds: int) -> str:
        """从历史消息中提取核心记忆.

        Args:
            messages: 需要压缩的消息列表
            num_rounds: 轮次数量

        Returns:
            核心记忆文本
        """
        # 构建对话内容
        conversation_text = ""
        for msg in messages:
            if msg.role == "user":
                conversation_text += f"用户: {msg.content}\n"
            elif msg.role == "assistant":
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                # 截断过长内容
                if len(content) > 500:
                    content = content[:500] + "..."
                conversation_text += f"助手: {content}\n"
                if msg.tool_calls:
                    tool_names = [tc.function.name for tc in msg.tool_calls]
                    conversation_text += f"  [调用工具: {', '.join(tool_names)}]\n"
            elif msg.role == "tool":
                result = msg.content if isinstance(msg.content, str) else str(msg.content)
                if len(result) > 200:
                    result = result[:200] + "..."
                conversation_text += f"  [工具结果: {result}]\n"

        # 调用 LLM 提取核心记忆
        try:
            extract_prompt = f"""请从以下 {num_rounds} 轮对话中提取核心记忆，用于后续对话的上下文理解。

<对话历史>
{conversation_text}
</对话历史>

请提取并整理：
1. **用户意图**: 用户想要完成什么任务？
2. **关键信息**: 提到的重要事实、数据、文件名、位置等
3. **已完成操作**: 助手已经做了什么？
4. **待处理事项**: 还有什么没完成？

要求：
- 简洁明了，控制在 300 字以内
- 只保留对后续对话有用的信息
- 使用中文"""

            response = await self.llm.generate(
                messages=[
                    Message(role="system", content="你是一个擅长总结和提取关键信息的助手。"),
                    Message(role="user", content=extract_prompt),
                ]
            )

            return response.content if response.content else ""

        except Exception as e:
            print(f"⚠️ 核心记忆提取失败: {e}")
            # 失败时返回简单摘要
            return f"[{num_rounds} 轮对话历史，提取失败]"

