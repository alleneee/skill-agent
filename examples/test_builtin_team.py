"""
测试内置 Web Research Team 功能

演示如何通过 API 使用内置的 web_search_agent 和 web_spider_agent
"""

import asyncio
import json
import os
from dotenv import load_dotenv
import httpx

load_dotenv()

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


async def test_builtin_team_basic():
    """测试 1: 基础内置 Team 使用"""
    print("=" * 80)
    print("测试 1: 基础内置 Team 使用")
    print("=" * 80)

    async with httpx.AsyncClient(timeout=300.0) as client:
        request_data = {
            "message": "Search for recent AI news and summarize the top result",
            "use_team": True,
        }

        print(f"\n发送请求:")
        print(json.dumps(request_data, indent=2, ensure_ascii=False))

        response = await client.post(
            f"{BASE_URL}/api/v1/agent/run",
            json=request_data,
        )

        if response.status_code == 200:
            result = response.json()
            print(f"\n✓ 成功: {result['success']}")
            print(f"✓ 步数: {result['steps']}")
            print(f"✓ Session ID: {result.get('session_id', 'None')}")
            print(f"\n响应内容:\n{result['message']}\n")
        else:
            print(f"\n❌ 请求失败: {response.status_code}")
            print(f"错误信息: {response.text}")

    print("=" * 80 + "\n")


async def test_builtin_team_with_session():
    """测试 2: 使用会话的多轮对话"""
    print("=" * 80)
    print("测试 2: 使用会话的多轮对话")
    print("=" * 80)

    session_id = "builtin-team-test-session"

    async with httpx.AsyncClient(timeout=300.0) as client:
        # 第一轮: 搜索
        print("\n--- Round 1: 搜索 AI 新闻 ---")
        request1 = {
            "message": "Search for latest developments in large language models",
            "use_team": True,
            "session_id": session_id,
        }

        response1 = await client.post(
            f"{BASE_URL}/api/v1/agent/run",
            json=request1,
        )

        if response1.status_code == 200:
            result1 = response1.json()
            print(f"✓ 成功: {result1['success']}")
            print(f"✓ 步数: {result1['steps']}")
            print(f"\n响应:\n{result1['message'][:500]}...\n")
        else:
            print(f"❌ 失败: {response1.status_code}")
            return

        # 第二轮: 继续基于上一轮结果
        print("--- Round 2: 提取更多细节 ---")
        request2 = {
            "message": "Based on the previous search, extract more details from the first result",
            "use_team": True,
            "session_id": session_id,
            "num_history_runs": 3,
        }

        response2 = await client.post(
            f"{BASE_URL}/api/v1/agent/run",
            json=request2,
        )

        if response2.status_code == 200:
            result2 = response2.json()
            print(f"✓ 成功: {result2['success']}")
            print(f"✓ 步数: {result2['steps']}")
            print(f"\n响应:\n{result2['message'][:500]}...\n")
        else:
            print(f"❌ 失败: {response2.status_code}")

    print("=" * 80 + "\n")


async def test_builtin_team_search_and_crawl():
    """测试 3: 搜索并爬取内容"""
    print("=" * 80)
    print("测试 3: 搜索并爬取内容")
    print("=" * 80)

    async with httpx.AsyncClient(timeout=300.0) as client:
        request_data = {
            "message": (
                "First search for articles about Python asyncio, "
                "then crawl the most relevant article and summarize its content"
            ),
            "use_team": True,
            "config": {
                "max_steps": 30,
            }
        }

        print(f"\n发送请求:")
        print(json.dumps(request_data, indent=2, ensure_ascii=False))

        response = await client.post(
            f"{BASE_URL}/api/v1/agent/run",
            json=request_data,
        )

        if response.status_code == 200:
            result = response.json()
            print(f"\n✓ 成功: {result['success']}")
            print(f"✓ 步数: {result['steps']}")
            print(f"\n响应内容:\n{result['message']}\n")
        else:
            print(f"\n❌ 请求失败: {response.status_code}")
            print(f"错误信息: {response.text}")

    print("=" * 80 + "\n")


async def test_compare_team_vs_single():
    """测试 4: 对比 Team 模式和单 Agent 模式"""
    print("=" * 80)
    print("测试 4: 对比 Team 模式和单 Agent 模式")
    print("=" * 80)

    task = "Search for Python best practices"

    async with httpx.AsyncClient(timeout=300.0) as client:
        # 使用 Team 模式
        print("\n--- 使用 Team 模式 ---")
        team_request = {
            "message": task,
            "use_team": True,
        }

        team_response = await client.post(
            f"{BASE_URL}/api/v1/agent/run",
            json=team_request,
        )

        if team_response.status_code == 200:
            team_result = team_response.json()
            print(f"✓ Team 模式成功")
            print(f"✓ 步数: {team_result['steps']}")
            print(f"✓ 响应长度: {len(team_result['message'])} 字符")
        else:
            print(f"❌ Team 模式失败: {team_response.status_code}")

        # 使用单 Agent 模式
        print("\n--- 使用单 Agent 模式 ---")
        single_request = {
            "message": task,
            "use_team": False,
        }

        single_response = await client.post(
            f"{BASE_URL}/api/v1/agent/run",
            json=single_request,
        )

        if single_response.status_code == 200:
            single_result = single_response.json()
            print(f"✓ 单 Agent 模式成功")
            print(f"✓ 步数: {single_result['steps']}")
            print(f"✓ 响应长度: {len(single_result['message'])} 字符")
        else:
            print(f"❌ 单 Agent 模式失败: {single_response.status_code}")

    print("\n" + "=" * 80 + "\n")


async def main():
    """运行所有测试"""
    print("\n" + "=" * 80)
    print("内置 Web Research Team 测试套件")
    print("=" * 80 + "\n")

    tests = [
        ("基础内置 Team", test_builtin_team_basic),
        ("多轮对话", test_builtin_team_with_session),
        ("搜索并爬取", test_builtin_team_search_and_crawl),
        ("Team vs 单 Agent 对比", test_compare_team_vs_single),
    ]

    for name, test_func in tests:
        try:
            await test_func()
        except Exception as e:
            print(f"❌ 测试失败: {name}")
            print(f"错误: {e}")
            import traceback
            traceback.print_exc()
        print("\n")

    print("=" * 80)
    print("所有测试完成")
    print("=" * 80)


if __name__ == "__main__":
    print("\n注意: 确保服务器已启动 (make dev)")
    print("并且 mcp.json 中配置了 exa 和 firecrawl 工具\n")
    asyncio.run(main())
