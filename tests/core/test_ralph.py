"""Ralph 模式测试."""

import tempfile
from pathlib import Path

import pytest

from omni_agent.core.ralph import (
    CompletionCondition,
    CompletionDetector,
    ContextManager,
    ContextStrategy,
    RalphConfig,
    RalphLoop,
    RalphState,
    ToolResultCache,
    WorkingMemory,
)


class TestRalphConfig:
    def test_default_config(self):
        config = RalphConfig()
        assert config.enabled is False
        assert config.max_iterations == 20
        assert config.completion_promise == "TASK COMPLETE"
        assert config.idle_threshold == 3
        assert config.context_strategy == ContextStrategy.ALL

    def test_enabled_config(self):
        config = RalphConfig(enabled=True, max_iterations=10)
        assert config.enabled is True
        assert config.max_iterations == 10

    def test_to_dict(self):
        config = RalphConfig(enabled=True)
        result = config.to_dict()
        assert result["enabled"] is True
        assert "max_iterations" in result
        assert "completion_conditions" in result


class TestToolResultCache:
    def test_store_and_retrieve(self):
        cache = ToolResultCache()
        cache.store(
            tool_call_id="test_id",
            tool_name="read_file",
            arguments={"path": "/test"},
            full_content="Full content here",
            summary="Summary",
            iteration=1,
        )

        assert cache.get_summary("test_id") == "Summary"
        assert cache.get_full_content("test_id") == "Full content here"

    def test_get_by_tool_name(self):
        cache = ToolResultCache()
        cache.store("id1", "read_file", {}, "content1", "sum1", 1)
        cache.store("id2", "write_file", {}, "content2", "sum2", 1)
        cache.store("id3", "read_file", {}, "content3", "sum3", 1)

        results = cache.get_by_tool_name("read_file")
        assert len(results) == 2

    def test_max_cache_size(self):
        cache = ToolResultCache(max_cache_size=2)
        cache.store("id1", "tool1", {}, "c1", "s1", 1)
        cache.store("id2", "tool2", {}, "c2", "s2", 1)
        cache.store("id3", "tool3", {}, "c3", "s3", 1)

        assert cache.get_full_content("id1") is None
        assert cache.get_full_content("id2") is not None
        assert cache.get_full_content("id3") is not None

    def test_clear(self):
        cache = ToolResultCache()
        cache.store("id1", "tool1", {}, "c1", "s1", 1)
        cache.clear()
        assert cache.get_full_content("id1") is None


class TestWorkingMemory:
    def test_basic_operations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = WorkingMemory(Path(tmpdir))

            memory.add_progress("Step 1 completed")
            memory.add_finding("Found issue X")
            todo_key = memory.add_todo("Fix issue X")

            assert memory.get(todo_key) is not None
            assert not memory.get(todo_key)["completed"]

            memory.complete_todo(todo_key)
            assert memory.get(todo_key)["completed"]

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory1 = WorkingMemory(Path(tmpdir))
            memory1.add_progress("Test progress")
            memory1.increment_iteration()

            memory2 = WorkingMemory(Path(tmpdir))
            assert memory2.current_iteration == 1
            progress = memory2.get_by_category(WorkingMemory.CATEGORY_PROGRESS)
            assert len(progress) == 1

    def test_to_context_string(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = WorkingMemory(Path(tmpdir))
            memory.add_progress("Did X")
            memory.add_finding("Found Y")
            memory.add_todo("Do Z")

            context = memory.to_context_string()
            assert "Working Memory" in context
            assert "Did X" in context
            assert "Found Y" in context
            assert "Do Z" in context

    def test_file_modified_tracking(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = WorkingMemory(Path(tmpdir))
            memory.record_file_modified("/path/to/file.py")
            memory.record_file_modified("/path/to/another.py")

            files = memory.get_files_modified()
            assert len(files) == 2
            assert "/path/to/file.py" in files


class TestCompletionDetector:
    def test_promise_detection(self):
        config = RalphConfig(completion_conditions=[CompletionCondition.PROMISE_TAG])
        detector = CompletionDetector(config)

        result = detector.check(
            content="Task done. <promise>TASK COMPLETE</promise>",
            iteration=1,
            files_modified=set(),
        )
        assert result.completed is True
        assert result.reason == CompletionCondition.PROMISE_TAG

    def test_max_iterations(self):
        config = RalphConfig(
            max_iterations=5, completion_conditions=[CompletionCondition.MAX_ITERATIONS]
        )
        detector = CompletionDetector(config)

        result = detector.check(
            content="Still working...",
            iteration=5,
            files_modified=set(),
        )
        assert result.completed is True
        assert result.reason == CompletionCondition.MAX_ITERATIONS

    def test_idle_threshold(self):
        config = RalphConfig(
            idle_threshold=2, completion_conditions=[CompletionCondition.IDLE_THRESHOLD]
        )
        detector = CompletionDetector(config)

        files = {"file1.py"}
        detector.check("Working", 1, files)
        result1 = detector.check("Working", 2, files)
        assert result1.completed is False

        result2 = detector.check("Working", 3, files)
        assert result2.completed is True
        assert result2.reason == CompletionCondition.IDLE_THRESHOLD

    def test_not_completed(self):
        config = RalphConfig(
            max_iterations=10,
            idle_threshold=5,
            completion_conditions=[
                CompletionCondition.PROMISE_TAG,
                CompletionCondition.MAX_ITERATIONS,
            ],
        )
        detector = CompletionDetector(config)

        result = detector.check(
            content="Still working on it",
            iteration=3,
            files_modified={"new_file.py"},
        )
        assert result.completed is False


class TestContextManager:
    @pytest.mark.asyncio
    async def test_summarize_short_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RalphConfig()
            cache = ToolResultCache()
            memory = WorkingMemory(Path(tmpdir))
            manager = ContextManager(config, cache, memory)

            short_content = "Short result"
            summary = await manager.summarize_tool_result("test_tool", short_content)
            assert summary == short_content

    @pytest.mark.asyncio
    async def test_summarize_long_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RalphConfig()
            cache = ToolResultCache()
            memory = WorkingMemory(Path(tmpdir))
            manager = ContextManager(config, cache, memory)

            long_content = "This is a long line of content that repeats many times.\n" * 50
            summary = await manager.summarize_tool_result("test_tool", long_content)
            assert "more lines" in summary

    @pytest.mark.asyncio
    async def test_process_tool_result_caches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RalphConfig(context_strategy=ContextStrategy.ALL)
            cache = ToolResultCache()
            memory = WorkingMemory(Path(tmpdir))
            manager = ContextManager(config, cache, memory)

            await manager.process_tool_result(
                tool_call_id="call_123",
                tool_name="read_file",
                arguments={"path": "/test"},
                content="Full file content here",
                iteration=1,
            )

            assert cache.get_full_content("call_123") is not None

    def test_build_context_prefix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RalphConfig()
            cache = ToolResultCache()
            memory = WorkingMemory(Path(tmpdir))
            manager = ContextManager(config, cache, memory)

            memory.add_progress("Made progress")
            cache.store("id1", "tool1", {}, "content", "Tool summary", 1)

            context = manager.build_context_prefix()
            assert "Working Memory" in context
            assert "Made progress" in context


class TestRalphLoop:
    def test_initialization(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RalphConfig(enabled=True)
            loop = RalphLoop(config, Path(tmpdir))

            assert loop.config.enabled is True
            assert loop.state.iteration == 0
            assert loop.state.completed is False

    def test_start_iteration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RalphConfig(enabled=True)
            loop = RalphLoop(config, Path(tmpdir))

            iteration = loop.start_iteration()
            assert iteration == 1
            assert loop.state.iteration == 1

            iteration = loop.start_iteration()
            assert iteration == 2

    def test_record_file_modified(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RalphConfig(enabled=True)
            loop = RalphLoop(config, Path(tmpdir))

            loop.record_file_modified("/path/to/file.py")
            assert "/path/to/file.py" in loop.state.files_modified

    @pytest.mark.asyncio
    async def test_process_tool_result_tracks_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RalphConfig(enabled=True)
            loop = RalphLoop(config, Path(tmpdir))
            loop.start_iteration()

            await loop.process_tool_result(
                tool_call_id="call_1",
                tool_name="write_file",
                arguments={"file_path": "/test/output.txt"},
                content="File written",
            )

            assert "/test/output.txt" in loop.working_memory.get_files_modified()

    def test_check_completion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RalphConfig(enabled=True)
            loop = RalphLoop(config, Path(tmpdir))
            loop.start_iteration()

            result = loop.check_completion("<promise>TASK COMPLETE</promise>")
            assert result.completed is True
            assert loop.state.completed is True

    def test_get_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RalphConfig(enabled=True)
            loop = RalphLoop(config, Path(tmpdir))

            status = loop.get_status()
            assert status["enabled"] is True
            assert "state" in status
            assert "memory_summary" in status

    def test_reset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RalphConfig(enabled=True)
            loop = RalphLoop(config, Path(tmpdir))

            loop.start_iteration()
            loop.working_memory.add_progress("Test")
            loop.check_completion("<promise>TASK COMPLETE</promise>")

            loop.reset()
            assert loop.state.iteration == 0
            assert loop.state.completed is False


class TestRalphState:
    def test_default_state(self):
        state = RalphState()
        assert state.iteration == 0
        assert state.completed is False
        assert state.completion_reason is None

    def test_to_dict(self):
        state = RalphState(iteration=3, completed=True, completion_reason="max_iterations")
        result = state.to_dict()
        assert result["iteration"] == 3
        assert result["completed"] is True
        assert result["completion_reason"] == "max_iterations"
