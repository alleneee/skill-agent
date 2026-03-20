import pytest

from omni_agent.tools.file_tools import (
    EditTool,
    GlobTool,
    GrepTool,
    ListDirTool,
    ReadTool,
    WriteTool,
    _is_sensitive_path,
    _resolve_and_validate,
)


class TestIsSensitivePath:
    @pytest.mark.parametrize(
        "path",
        [
            ".env",
            ".env.local",
            ".env.production",
            "config/.env",
            "config/.env.test",
        ],
    )
    def test_env_files_blocked(self, path: str) -> None:
        assert _is_sensitive_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "credentials.json",
            "aws_credentials",
            "db_credentials.yaml",
            "config/credentials",
        ],
    )
    def test_credentials_blocked(self, path: str) -> None:
        assert _is_sensitive_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "secret.txt",
            "client_secret.json",
            "config/secrets.yaml",
        ],
    )
    def test_secrets_blocked(self, path: str) -> None:
        assert _is_sensitive_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            ".ssh/id_rsa",
            ".ssh/config",
            ".ssh/authorized_keys",
        ],
    )
    def test_ssh_dir_blocked(self, path: str) -> None:
        assert _is_sensitive_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "server.pem",
            "cert.key",
            "app.keystore",
            ".git-credentials",
            ".netrc",
            ".pgpass",
        ],
    )
    def test_key_files_blocked(self, path: str) -> None:
        assert _is_sensitive_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "app.py",
            "README.md",
            "src/main.py",
            "config/settings.yaml",
            "data/output.csv",
            "environment.py",
            "envoy.yaml",
        ],
    )
    def test_safe_paths_allowed(self, path: str) -> None:
        assert _is_sensitive_path(path) is False


class TestResolveAndValidate:
    def test_relative_path_resolved_to_workspace(self, tmp_path) -> None:
        (tmp_path / "file.txt").write_text("hello")
        result = _resolve_and_validate("file.txt", tmp_path)
        assert result == (tmp_path / "file.txt").resolve()

    def test_absolute_path_in_workspace(self, tmp_path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("hello")
        result = _resolve_and_validate(str(f), tmp_path)
        assert result == f.resolve()

    def test_path_outside_workspace_raises(self, tmp_path) -> None:
        with pytest.raises(PermissionError, match="outside workspace"):
            _resolve_and_validate("/etc/passwd", tmp_path)

    def test_path_traversal_blocked(self, tmp_path) -> None:
        with pytest.raises(PermissionError, match="outside workspace"):
            _resolve_and_validate("../../etc/passwd", tmp_path)

    def test_sensitive_file_blocked(self, tmp_path) -> None:
        (tmp_path / ".env").write_text("SECRET=123")
        with pytest.raises(PermissionError, match="sensitive file pattern"):
            _resolve_and_validate(".env", tmp_path)

    def test_sensitive_nested_file_blocked(self, tmp_path) -> None:
        d = tmp_path / "config"
        d.mkdir()
        (d / "credentials.json").write_text("{}")
        with pytest.raises(PermissionError, match="sensitive file pattern"):
            _resolve_and_validate("config/credentials.json", tmp_path)


class TestReadTool:
    def test_properties(self) -> None:
        tool = ReadTool()
        assert tool.name == "read_file"
        assert "Read" in tool.description
        params = tool.parameters
        assert params["type"] == "object"
        assert "path" in params["properties"]
        assert params["required"] == ["path"]

    async def test_read_existing_file(self, tmp_path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\nline3\n")
        tool = ReadTool(workspace_dir=str(tmp_path))
        result = await tool.execute(path="test.txt")
        assert result.success is True
        assert "line1" in result.content
        assert "line2" in result.content

    async def test_read_with_line_numbers(self, tmp_path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello\nworld\n")
        tool = ReadTool(workspace_dir=str(tmp_path))
        result = await tool.execute(path="test.txt")
        assert result.success is True
        assert "1|hello" in result.content
        assert "2|world" in result.content

    async def test_read_with_offset_and_limit(self, tmp_path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("a\nb\nc\nd\ne\n")
        tool = ReadTool(workspace_dir=str(tmp_path))
        result = await tool.execute(path="test.txt", offset=2, limit=2)
        assert result.success is True
        assert "2|b" in result.content
        assert "3|c" in result.content
        assert "1|a" not in result.content

    async def test_read_nonexistent_file(self, tmp_path) -> None:
        tool = ReadTool(workspace_dir=str(tmp_path))
        result = await tool.execute(path="missing.txt")
        assert result.success is False
        assert "not found" in result.error.lower()

    async def test_read_sensitive_file_blocked(self, tmp_path) -> None:
        (tmp_path / ".env").write_text("SECRET=123")
        tool = ReadTool(workspace_dir=str(tmp_path))
        result = await tool.execute(path=".env")
        assert result.success is False
        assert "sensitive" in result.error.lower()

    async def test_read_outside_workspace_blocked(self, tmp_path) -> None:
        tool = ReadTool(workspace_dir=str(tmp_path))
        result = await tool.execute(path="/etc/passwd")
        assert result.success is False
        assert "outside workspace" in result.error.lower()


class TestWriteTool:
    def test_properties(self) -> None:
        tool = WriteTool()
        assert tool.name == "write_file"
        assert "Write" in tool.description
        assert "path" in tool.parameters["properties"]
        assert "content" in tool.parameters["properties"]

    async def test_write_new_file(self, tmp_path) -> None:
        tool = WriteTool(workspace_dir=str(tmp_path))
        result = await tool.execute(path="new.txt", content="hello world")
        assert result.success is True
        assert (tmp_path / "new.txt").read_text() == "hello world"

    async def test_write_creates_parent_dirs(self, tmp_path) -> None:
        tool = WriteTool(workspace_dir=str(tmp_path))
        result = await tool.execute(path="sub/dir/file.txt", content="nested")
        assert result.success is True
        assert (tmp_path / "sub" / "dir" / "file.txt").read_text() == "nested"

    async def test_write_overwrites_existing(self, tmp_path) -> None:
        (tmp_path / "existing.txt").write_text("old")
        tool = WriteTool(workspace_dir=str(tmp_path))
        result = await tool.execute(path="existing.txt", content="new")
        assert result.success is True
        assert (tmp_path / "existing.txt").read_text() == "new"

    async def test_write_sensitive_file_blocked(self, tmp_path) -> None:
        tool = WriteTool(workspace_dir=str(tmp_path))
        result = await tool.execute(path=".env", content="SECRET=bad")
        assert result.success is False
        assert "sensitive" in result.error.lower()

    async def test_write_outside_workspace_blocked(self, tmp_path) -> None:
        tool = WriteTool(workspace_dir=str(tmp_path))
        result = await tool.execute(path="/tmp/escape.txt", content="bad")
        assert result.success is False


class TestEditTool:
    def test_properties(self) -> None:
        tool = EditTool()
        assert tool.name == "edit_file"
        assert "path" in tool.parameters["properties"]
        assert "old_str" in tool.parameters["properties"]
        assert "new_str" in tool.parameters["properties"]

    async def test_edit_single_replacement(self, tmp_path) -> None:
        (tmp_path / "test.py").write_text("x = 1\ny = 2\n")
        tool = EditTool(workspace_dir=str(tmp_path))
        result = await tool.execute(path="test.py", old_str="x = 1", new_str="x = 10")
        assert result.success is True
        assert (tmp_path / "test.py").read_text() == "x = 10\ny = 2\n"

    async def test_edit_multiple_matches_without_replace_all_fails(self, tmp_path) -> None:
        (tmp_path / "test.py").write_text("x = 1\nx = 1\n")
        tool = EditTool(workspace_dir=str(tmp_path))
        result = await tool.execute(path="test.py", old_str="x = 1", new_str="x = 2")
        assert result.success is False
        assert "2 matches" in result.error

    async def test_edit_replace_all(self, tmp_path) -> None:
        (tmp_path / "test.py").write_text("x = 1\nx = 1\n")
        tool = EditTool(workspace_dir=str(tmp_path))
        result = await tool.execute(
            path="test.py", old_str="x = 1", new_str="x = 2", replace_all=True
        )
        assert result.success is True
        assert (tmp_path / "test.py").read_text() == "x = 2\nx = 2\n"

    async def test_edit_text_not_found(self, tmp_path) -> None:
        (tmp_path / "test.py").write_text("hello")
        tool = EditTool(workspace_dir=str(tmp_path))
        result = await tool.execute(path="test.py", old_str="missing", new_str="new")
        assert result.success is False
        assert "not found" in result.error.lower()

    async def test_edit_nonexistent_file(self, tmp_path) -> None:
        tool = EditTool(workspace_dir=str(tmp_path))
        result = await tool.execute(path="missing.py", old_str="a", new_str="b")
        assert result.success is False

    async def test_edit_sensitive_file_blocked(self, tmp_path) -> None:
        (tmp_path / ".env").write_text("SECRET=old")
        tool = EditTool(workspace_dir=str(tmp_path))
        result = await tool.execute(path=".env", old_str="old", new_str="new")
        assert result.success is False
        assert "sensitive" in result.error.lower()


class TestListDirTool:
    def test_properties(self) -> None:
        tool = ListDirTool()
        assert tool.name == "ls"

    async def test_list_directory(self, tmp_path) -> None:
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.py").write_text("b")
        tool = ListDirTool(workspace_dir=str(tmp_path))
        result = await tool.execute(path=".")
        assert result.success is True
        assert "a.txt" in result.content
        assert "b.py" in result.content

    async def test_list_empty_directory(self, tmp_path) -> None:
        sub = tmp_path / "empty"
        sub.mkdir()
        tool = ListDirTool(workspace_dir=str(tmp_path))
        result = await tool.execute(path="empty")
        assert result.success is True
        assert "empty" in result.content.lower()

    async def test_list_nonexistent_directory(self, tmp_path) -> None:
        tool = ListDirTool(workspace_dir=str(tmp_path))
        result = await tool.execute(path="missing")
        assert result.success is False

    async def test_list_file_not_dir(self, tmp_path) -> None:
        (tmp_path / "file.txt").write_text("x")
        tool = ListDirTool(workspace_dir=str(tmp_path))
        result = await tool.execute(path="file.txt")
        assert result.success is False
        assert "not a directory" in result.error.lower()

    async def test_format_size(self) -> None:
        tool = ListDirTool()
        assert tool._format_size(0) == "0B"
        assert tool._format_size(512) == "512B"
        assert tool._format_size(1024) == "1.0KB"
        assert tool._format_size(1048576) == "1.0MB"


class TestGlobTool:
    def test_properties(self) -> None:
        tool = GlobTool()
        assert tool.name == "glob"

    async def test_glob_py_files(self, tmp_path) -> None:
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        (tmp_path / "c.txt").write_text("")
        tool = GlobTool(workspace_dir=str(tmp_path))
        result = await tool.execute(pattern="*.py")
        assert result.success is True
        assert "a.py" in result.content
        assert "b.py" in result.content
        assert "c.txt" not in result.content

    async def test_glob_no_matches(self, tmp_path) -> None:
        tool = GlobTool(workspace_dir=str(tmp_path))
        result = await tool.execute(pattern="*.xyz")
        assert result.success is True
        assert "No files matching" in result.content

    async def test_glob_nonexistent_path(self, tmp_path) -> None:
        tool = GlobTool(workspace_dir=str(tmp_path))
        result = await tool.execute(pattern="*.py", path="missing")
        assert result.success is False


class TestGrepTool:
    def test_properties(self) -> None:
        tool = GrepTool()
        assert tool.name == "grep"

    async def test_grep_find_pattern(self, tmp_path) -> None:
        (tmp_path / "test.py").write_text("def hello():\n    return 'world'\n")
        tool = GrepTool(workspace_dir=str(tmp_path))
        result = await tool.execute(pattern="hello")
        assert result.success is True
        assert "hello" in result.content

    async def test_grep_no_matches(self, tmp_path) -> None:
        (tmp_path / "test.py").write_text("abc\n")
        tool = GrepTool(workspace_dir=str(tmp_path))
        result = await tool.execute(pattern="xyz")
        assert result.success is True
        assert "No matches" in result.content

    async def test_grep_invalid_regex(self, tmp_path) -> None:
        tool = GrepTool(workspace_dir=str(tmp_path))
        result = await tool.execute(pattern="[invalid")
        assert result.success is False
        assert "Invalid regex" in result.error

    async def test_grep_with_context(self, tmp_path) -> None:
        (tmp_path / "test.py").write_text("line1\nline2\nline3\nline4\nline5\n")
        tool = GrepTool(workspace_dir=str(tmp_path))
        result = await tool.execute(pattern="line3", context=1)
        assert result.success is True
        assert "line2" in result.content
        assert "line4" in result.content

    async def test_grep_with_include_filter(self, tmp_path) -> None:
        (tmp_path / "a.py").write_text("target\n")
        (tmp_path / "b.txt").write_text("target\n")
        tool = GrepTool(workspace_dir=str(tmp_path))
        result = await tool.execute(pattern="target", include="*.py")
        assert result.success is True
        assert "a.py" in result.content
        assert "b.txt" not in result.content
