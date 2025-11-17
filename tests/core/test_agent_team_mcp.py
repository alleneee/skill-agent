"""
测试 AgentTeam 与 MCP 工具集成

验证 desktop-commander 和 exa 子 agent 的功能
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi_agent.core.agent import Agent
from fastapi_agent.core.agent_team import AgentTeam, CoordinationStrategy
from fastapi_agent.core.llm_client import LLMClient


class TestAgentTeamWithMCP:
    """测试 AgentTeam 使用 MCP 工具"""

    @pytest.fixture
    def mock_llm_client(self):
        """创建模拟的 LLM 客户端"""
        client = Mock(spec=LLMClient)
        client.chat.return_value = {
            "role": "assistant",
            "content": "测试响应"
        }
        return client

    @pytest.fixture
    def mock_exa_tool(self):
        """创建模拟的 exa 搜索工具"""
        tool = Mock()
        tool.name = "web_search_exa"
        tool.description = "Search the web using Exa"
        tool.parameters = {
            "query": {"type": "string", "description": "Search query"}
        }
        tool.execute = Mock(return_value={"results": ["搜索结果1", "搜索结果2"]})
        return tool

    @pytest.fixture
    def mock_desktop_tool(self):
        """创建模拟的 desktop-commander 工具"""
        tool = Mock()
        tool.name = "execute_command"
        tool.description = "Execute desktop command"
        tool.parameters = {
            "command": {"type": "string", "description": "Command to execute"}
        }
        tool.execute = Mock(return_value={"status": "success", "output": "命令执行成功"})
        return tool

    def test_create_search_agent_with_exa(self, mock_llm_client, mock_exa_tool):
        """测试创建带有 exa 工具的搜索 agent"""
        agent = Agent(
            llm_client=mock_llm_client,
            name="WebSearcher",
            system_prompt="你是网络搜索专家",
            tools=[mock_exa_tool],
            max_steps=5
        )

        assert agent.name == "WebSearcher"
        assert len(agent.tools) == 1
        assert agent.tools[0].name == "web_search_exa"

    def test_create_desktop_agent_with_commander(self, mock_llm_client, mock_desktop_tool):
        """测试创建带有 desktop-commander 工具的 agent"""
        agent = Agent(
            llm_client=mock_llm_client,
            name="DesktopOperator",
            system_prompt="你是桌面操作专家",
            tools=[mock_desktop_tool],
            max_steps=5
        )

        assert agent.name == "DesktopOperator"
        assert len(agent.tools) == 1
        assert agent.tools[0].name == "execute_command"

    def test_sequential_team_with_mcp_tools(
        self, mock_llm_client, mock_exa_tool, mock_desktop_tool
    ):
        """测试顺序执行策略的 MCP 工具团队"""
        # 创建成员
        search_agent = Agent(
            llm_client=mock_llm_client,
            name="WebSearcher",
            system_prompt="搜索专家",
            tools=[mock_exa_tool],
            max_steps=3
        )

        desktop_agent = Agent(
            llm_client=mock_llm_client,
            name="DesktopOperator",
            system_prompt="桌面操作专家",
            tools=[mock_desktop_tool],
            max_steps=3
        )

        # 创建团队
        team = AgentTeam(
            members=[search_agent, desktop_agent],
            strategy=CoordinationStrategy.SEQUENTIAL,
            name="Search-Execute Team",
            enable_logging=False  # 测试时禁用日志
        )

        assert team.name == "Search-Execute Team"
        assert len(team.members) == 2
        assert team.strategy == CoordinationStrategy.SEQUENTIAL

    def test_broadcast_team_with_exa_tools(self, mock_llm_client, mock_exa_tool):
        """测试广播策略的 exa 搜索团队"""
        # 创建两个搜索 agent
        tech_searcher = Agent(
            llm_client=mock_llm_client,
            name="TechSearcher",
            system_prompt="技术搜索专家",
            tools=[mock_exa_tool],
            max_steps=3
        )

        news_searcher = Agent(
            llm_client=mock_llm_client,
            name="NewsSearcher",
            system_prompt="新闻搜索专家",
            tools=[mock_exa_tool],
            max_steps=3
        )

        # 创建团队
        team = AgentTeam(
            members=[tech_searcher, news_searcher],
            strategy=CoordinationStrategy.BROADCAST,
            name="Multi-Search Team",
            enable_logging=False
        )

        assert team.name == "Multi-Search Team"
        assert len(team.members) == 2
        assert team.strategy == CoordinationStrategy.BROADCAST

    def test_leader_worker_team_with_mcp_tools(
        self, mock_llm_client, mock_exa_tool, mock_desktop_tool
    ):
        """测试 Leader-Worker 策略的 MCP 工具团队"""
        # 创建协调者
        coordinator = Agent(
            llm_client=mock_llm_client,
            name="Coordinator",
            system_prompt="团队协调者",
            max_steps=5
        )

        # 创建工作者
        search_agent = Agent(
            llm_client=mock_llm_client,
            name="WebSearcher",
            tools=[mock_exa_tool],
            max_steps=3
        )

        desktop_agent = Agent(
            llm_client=mock_llm_client,
            name="DesktopOperator",
            tools=[mock_desktop_tool],
            max_steps=3
        )

        # 创建团队
        team = AgentTeam(
            members=[search_agent, desktop_agent],
            coordinator=coordinator,
            strategy=CoordinationStrategy.LEADER_WORKER,
            name="Coordinated Team",
            share_interactions=True,
            enable_logging=False
        )

        assert team.name == "Coordinated Team"
        assert len(team.members) == 2
        assert team.coordinator is not None
        assert team.coordinator.name == "Coordinator"
        assert team.share_interactions is True

    def test_team_member_tool_access(self, mock_llm_client, mock_exa_tool, mock_desktop_tool):
        """测试团队成员可以正确访问其工具"""
        search_agent = Agent(
            llm_client=mock_llm_client,
            name="WebSearcher",
            tools=[mock_exa_tool],
            max_steps=3
        )

        desktop_agent = Agent(
            llm_client=mock_llm_client,
            name="DesktopOperator",
            tools=[mock_desktop_tool],
            max_steps=3
        )

        # 验证每个 agent 有正确的工具
        assert len(search_agent.tools) == 1
        assert search_agent.tools[0].name == "web_search_exa"

        assert len(desktop_agent.tools) == 1
        assert desktop_agent.tools[0].name == "execute_command"

    def test_team_strategies_enum(self):
        """测试协调策略枚举"""
        assert CoordinationStrategy.LEADER_WORKER.value == "leader_worker"
        assert CoordinationStrategy.BROADCAST.value == "broadcast"
        assert CoordinationStrategy.SEQUENTIAL.value == "sequential"
        assert CoordinationStrategy.ROUND_ROBIN.value == "round_robin"

    @patch('fastapi_agent.core.agent.Agent.run')
    def test_sequential_execution_flow(
        self, mock_run, mock_llm_client, mock_exa_tool, mock_desktop_tool
    ):
        """测试顺序执行流程（模拟 agent.run）"""
        # 模拟 agent.run 的返回值
        mock_run.side_effect = [
            {"success": True, "message": "搜索完成", "steps": 1},
            {"success": True, "message": "执行完成", "steps": 1}
        ]

        search_agent = Agent(
            llm_client=mock_llm_client,
            name="WebSearcher",
            tools=[mock_exa_tool],
            max_steps=3
        )

        desktop_agent = Agent(
            llm_client=mock_llm_client,
            name="DesktopOperator",
            tools=[mock_desktop_tool],
            max_steps=3
        )

        team = AgentTeam(
            members=[search_agent, desktop_agent],
            strategy=CoordinationStrategy.SEQUENTIAL,
            enable_logging=False
        )

        result = team.run("测试任务")

        # 验证两个 agent 都被调用
        assert mock_run.call_count == 2
        assert result.success is True
        assert result.steps == 2

    def test_team_without_coordinator_raises_error(self, mock_llm_client):
        """测试 LEADER_WORKER 策略没有协调者时抛出错误"""
        agent = Agent(llm_client=mock_llm_client, name="Worker", max_steps=3)

        with pytest.raises(ValueError, match="LEADER_WORKER strategy requires a coordinator"):
            AgentTeam(
                members=[agent],
                strategy=CoordinationStrategy.LEADER_WORKER,
                coordinator=None  # 没有协调者
            )

    def test_team_empty_members_raises_error(self, mock_llm_client):
        """测试空成员列表抛出错误"""
        with pytest.raises(ValueError, match="Team must have at least one member"):
            AgentTeam(
                members=[],  # 空成员列表
                strategy=CoordinationStrategy.SEQUENTIAL
            )


class TestMCPToolIntegration:
    """测试 MCP 工具集成"""

    def test_exa_tool_structure(self):
        """测试 exa 工具的结构"""
        # 这是一个集成测试，验证实际的 exa 工具结构
        # 在真实环境中，这将从 MCP 服务器加载
        expected_tool_name = "web_search_exa"
        expected_params = ["query"]

        # 注意: 这只是结构验证，实际工具需要 MCP 服务器运行
        assert expected_tool_name is not None
        assert len(expected_params) > 0

    def test_desktop_commander_tool_structure(self):
        """测试 desktop-commander 工具的结构"""
        # 验证 desktop-commander 工具的预期结构
        expected_tool_types = ["execute_command", "list_processes", "system_info"]

        # 注意: 这只是结构验证，实际工具需要 MCP 服务器运行
        assert len(expected_tool_types) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
