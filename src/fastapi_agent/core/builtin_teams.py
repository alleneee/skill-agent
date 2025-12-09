"""Builtin team configurations for common use cases."""

from typing import List

from fastapi_agent.core.llm_client import LLMClient
from fastapi_agent.core.team import Team
from fastapi_agent.schemas.team import TeamConfig, TeamMemberConfig
from fastapi_agent.tools.base import Tool


def create_web_research_team(
    llm_client: LLMClient,
    available_tools: List[Tool],
    workspace_dir: str = "./workspace",
) -> Team:
    """Create a builtin web research team with search and spider capabilities.

    This team consists of two specialized agents:
    1. Web Search Agent - Uses exa MCP tools for web searching
    2. Web Spider Agent - Uses firecrawl MCP tools for web crawling

    Args:
        llm_client: LLM client instance
        available_tools: All available tools (including MCP tools)
        workspace_dir: Workspace directory for file operations

    Returns:
        Configured Team instance

    Example:
        >>> team = create_web_research_team(llm_client, mcp_tools)
        >>> response = await team.run(
        ...     message="Search for AI news and crawl the top article",
        ...     session_id="user-123"
        ... )
    """
    # Filter tools by name prefix or type
    exa_tools = [t.name for t in available_tools if "exa" in t.name.lower() or "search" in t.name.lower()]
    firecrawl_tools = [t.name for t in available_tools if "firecrawl" in t.name.lower() or "crawl" in t.name.lower()]

    config = TeamConfig(
        name="Web Research Team",
        description="A specialized team for web searching and content extraction",
        members=[
            TeamMemberConfig(
                id="web_search_agent",
                name="Web Search Agent",
                role="Web Search Specialist",
                instructions=(
                    "You are a web search specialist. Use the exa search tools to find "
                    "relevant web content, articles, and information. Provide clear summaries "
                    "of search results with URLs."
                ),
                tools=exa_tools,
            ),
            TeamMemberConfig(
                id="web_spider_agent",
                name="Web Spider Agent",
                role="Web Crawling Specialist",
                instructions=(
                    "You are a web crawling specialist. Use firecrawl tools to extract "
                    "content from web pages. Provide clean, structured content from the "
                    "crawled pages."
                ),
                tools=firecrawl_tools,
            ),
        ],
        leader_instructions=(
            "Coordinate the web research team efficiently:\n"
            "1. For search queries, delegate to the Web Search Agent\n"
            "2. For content extraction from URLs, delegate to the Web Spider Agent\n"
            "3. You can delegate to both agents for comprehensive research:\n"
            "   - First search for relevant content\n"
            "   - Then crawl specific URLs to extract detailed information"
        ),
    )

    return Team(
        config=config,
        llm_client=llm_client,
        available_tools=available_tools,
        workspace_dir=workspace_dir,
    )
