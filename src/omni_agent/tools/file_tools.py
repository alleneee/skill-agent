"""文件操作工具。

提供 deepagents 风格的文件系统工具：
- read_file: 读取文件内容，带行号
- write_file: 创建或覆盖文件
- edit_file: 精确字符串替换，支持全局替换
- ls: 列出目录内容及元数据
- glob: 按模式查找文件
- grep: 支持正则表达式的文件内容搜索
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult

SENSITIVE_PATTERNS = [
    re.compile(r"(^|/)\.env(\..+)?$"),
    re.compile(r"(^|/).*credentials.*", re.IGNORECASE),
    re.compile(r"(^|/).*secret.*", re.IGNORECASE),
    re.compile(r"(^|/)\.ssh/"),
    re.compile(r".*\.pem$"),
    re.compile(r".*\.key$"),
    re.compile(r"(^|/)\.git-credentials$"),
    re.compile(r"(^|/).*\.keystore$"),
    re.compile(r"(^|/)\.netrc$"),
    re.compile(r"(^|/)\.pgpass$"),
]


def _is_sensitive_path(path: str) -> bool:
    return any(pattern.search(path) for pattern in SENSITIVE_PATTERNS)


def _resolve_and_validate(path: str, workspace_dir: Path) -> Path:
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = workspace_dir / file_path
    resolved = file_path.resolve()
    workspace_resolved = workspace_dir.resolve()
    if (
        not str(resolved).startswith(str(workspace_resolved) + "/")
        and resolved != workspace_resolved
    ):
        raise PermissionError(
            f"Access denied: path '{path}' is outside workspace '{workspace_dir}'"
        )
    if file_path.exists() and file_path.is_symlink():
        target = file_path.readlink().resolve()
        if (
            not str(target).startswith(str(workspace_resolved) + "/")
            and target != workspace_resolved
        ):
            raise PermissionError("Access denied: symlink target is outside workspace")
    rel_path = (
        str(resolved.relative_to(workspace_resolved))
        if resolved != workspace_resolved
        else str(resolved.name)
    )
    if _is_sensitive_path(rel_path):
        raise PermissionError(f"Access denied: '{path}' matches a sensitive file pattern")
    return resolved


class ReadTool(Tool):
    """读取文件内容。"""

    def __init__(self, workspace_dir: str = "."):
        """使用工作目录初始化 ReadTool。"""
        self.workspace_dir = Path(workspace_dir).absolute()

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read file contents from the filesystem. Output includes line numbers "
            "in format 'LINE_NUMBER|LINE_CONTENT' (1-indexed). Supports reading partial content "
            "by specifying line offset and limit for large files."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file",
                },
                "offset": {
                    "type": "integer",
                    "description": "Starting line number (1-indexed). Use for large files",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of lines to read. Use with offset for large files",
                },
            },
            "required": ["path"],
        }

    async def execute(
        self, path: str, offset: int | None = None, limit: int | None = None
    ) -> ToolResult:
        """执行文件读取。"""
        try:
            file_path = _resolve_and_validate(path, self.workspace_dir)

            if not file_path.exists():
                return ToolResult(
                    success=False,
                    content="",
                    error=f"File not found: {path}",
                )

            with open(file_path, encoding="utf-8") as f:
                lines = f.readlines()

            # Apply offset and limit
            start = (offset - 1) if offset else 0
            end = (start + limit) if limit else len(lines)
            start = max(0, start)
            end = min(end, len(lines))

            selected_lines = lines[start:end]

            # Format with line numbers
            numbered_lines = []
            for i, line in enumerate(selected_lines, start=start + 1):
                line_content = line.rstrip("\n")
                numbered_lines.append(f"{i:6d}|{line_content}")

            content = "\n".join(numbered_lines)
            return ToolResult(success=True, content=content)
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e))


class WriteTool(Tool):
    """写入内容到文件。"""

    def __init__(self, workspace_dir: str = "."):
        """使用工作目录初始化 WriteTool。"""
        self.workspace_dir = Path(workspace_dir).absolute()

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Write content to a file. Will overwrite existing files completely. "
            "For existing files, read first using read_file. "
            "Prefer editing existing files over creating new ones."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file",
                },
                "content": {
                    "type": "string",
                    "description": "Complete content to write (will replace existing content)",
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, path: str, content: str) -> ToolResult:
        """执行文件写入。"""
        try:
            file_path = _resolve_and_validate(path, self.workspace_dir)

            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            return ToolResult(success=True, content=f"Successfully wrote to {file_path}")
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e))


class EditTool(Tool):
    """通过替换文本编辑文件。"""

    def __init__(self, workspace_dir: str = "."):
        """使用工作目录初始化 EditTool。"""
        self.workspace_dir = Path(workspace_dir).absolute()

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return (
            "Perform exact string replacement in a file. By default, old_str must be unique. "
            "Set replace_all=true to replace all occurrences. Read the file first before editing."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file",
                },
                "old_str": {
                    "type": "string",
                    "description": "Exact string to find and replace",
                },
                "new_str": {
                    "type": "string",
                    "description": "Replacement string",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences (default: false, requires unique match)",
                },
            },
            "required": ["path", "old_str", "new_str"],
        }

    async def execute(
        self, path: str, old_str: str, new_str: str, replace_all: bool = False
    ) -> ToolResult:
        """执行文件编辑。"""
        try:
            file_path = _resolve_and_validate(path, self.workspace_dir)

            if not file_path.exists():
                return ToolResult(
                    success=False,
                    content="",
                    error=f"File not found: {path}",
                )

            content = file_path.read_text(encoding="utf-8")
            count = content.count(old_str)

            if count == 0:
                return ToolResult(
                    success=False,
                    content="",
                    error=f"Text not found in file: {old_str[:100]}...",
                )

            if count > 1 and not replace_all:
                return ToolResult(
                    success=False,
                    content="",
                    error=f"Found {count} matches. Set replace_all=true to replace all, or provide more context for unique match.",
                )

            new_content = content.replace(old_str, new_str)
            file_path.write_text(new_content, encoding="utf-8")

            msg = f"Successfully edited {file_path}"
            if count > 1:
                msg += f" ({count} replacements)"
            return ToolResult(success=True, content=msg)
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e))


class ListDirTool(Tool):
    """列出目录内容及元数据。"""

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = Path(workspace_dir).absolute()

    @property
    def name(self) -> str:
        return "ls"

    @property
    def description(self) -> str:
        return "List files and directories with size and modification time."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path (default: current workspace)",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "List subdirectories recursively (default: false)",
                },
            },
            "required": [],
        }

    async def execute(self, path: str = ".", recursive: bool = False) -> ToolResult:
        try:
            dir_path = _resolve_and_validate(path, self.workspace_dir)

            if not dir_path.exists():
                return ToolResult(success=False, content="", error=f"Directory not found: {path}")

            if not dir_path.is_dir():
                return ToolResult(success=False, content="", error=f"Not a directory: {path}")

            entries = []
            pattern = "**/*" if recursive else "*"

            for item in sorted(dir_path.glob(pattern)):
                try:
                    stat = item.stat()
                    size = stat.st_size
                    mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                    rel_path = item.relative_to(dir_path)
                    type_indicator = "d" if item.is_dir() else "f"
                    size_str = self._format_size(size) if item.is_file() else "-"
                    entries.append(f"{type_indicator} {size_str:>8} {mtime} {rel_path}")
                except (OSError, ValueError):
                    continue

            if not entries:
                return ToolResult(success=True, content="(empty directory)")

            return ToolResult(success=True, content="\n".join(entries))
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e))

    def _format_size(self, size: int) -> str:
        size_f = float(size)
        for unit in ["B", "KB", "MB", "GB"]:
            if size_f < 1024:
                return f"{size_f:.0f}{unit}" if unit == "B" else f"{size_f:.1f}{unit}"
            size_f /= 1024
        return f"{size_f:.1f}TB"


class GlobTool(Tool):
    """按 glob 模式查找文件。"""

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = Path(workspace_dir).absolute()

    @property
    def name(self) -> str:
        return "glob"

    @property
    def description(self) -> str:
        return "Find files matching glob pattern (e.g., **/*.py, src/**/*.md, *.txt)"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to match files",
                },
                "path": {
                    "type": "string",
                    "description": "Base directory for search (default: workspace)",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, pattern: str, path: str = ".") -> ToolResult:
        try:
            base_path = _resolve_and_validate(path, self.workspace_dir)

            if not base_path.exists():
                return ToolResult(success=False, content="", error=f"Path not found: {path}")

            matches = sorted(base_path.glob(pattern))
            if not matches:
                return ToolResult(success=True, content=f"No files matching: {pattern}")

            results = [str(m.relative_to(base_path)) for m in matches[:500]]
            output = "\n".join(results)
            if len(matches) > 500:
                output += f"\n... and {len(matches) - 500} more"

            return ToolResult(success=True, content=output)
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e))


class GrepTool(Tool):
    """使用正则表达式搜索文件内容。"""

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = Path(workspace_dir).absolute()

    @property
    def name(self) -> str:
        return "grep"

    @property
    def description(self) -> str:
        return "Search for pattern in files. Returns matching lines with file path and line number."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Search pattern (regex supported)",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory to search (default: workspace)",
                },
                "include": {
                    "type": "string",
                    "description": "File pattern to include (e.g., *.py, *.md)",
                },
                "context": {
                    "type": "integer",
                    "description": "Lines of context around each match (default: 0)",
                },
            },
            "required": ["pattern"],
        }

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        include: str | None = None,
        context: int = 0,
    ) -> ToolResult:
        try:
            search_path = _resolve_and_validate(path, self.workspace_dir)

            if not search_path.exists():
                return ToolResult(success=False, content="", error=f"Path not found: {path}")

            try:
                regex = re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                return ToolResult(success=False, content="", error=f"Invalid regex: {e}")

            results = []
            files_to_search = []

            if search_path.is_file():
                files_to_search = [search_path]
            else:
                glob_pattern = include or "*"
                if "**" not in glob_pattern:
                    glob_pattern = f"**/{glob_pattern}"
                files_to_search = [f for f in search_path.glob(glob_pattern) if f.is_file()]

            max_results = 100
            for file_path in files_to_search:
                if len(results) >= max_results:
                    break

                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    lines = content.split("\n")

                    for i, line in enumerate(lines, 1):
                        if regex.search(line):
                            rel_path = (
                                file_path.relative_to(self.workspace_dir)
                                if file_path.is_relative_to(self.workspace_dir)
                                else file_path
                            )

                            if context > 0:
                                start = max(0, i - 1 - context)
                                end = min(len(lines), i + context)
                                ctx_lines = []
                                for j in range(start, end):
                                    prefix = ">" if j == i - 1 else " "
                                    ctx_lines.append(f"{prefix} {j + 1:4d}| {lines[j]}")
                                results.append(f"{rel_path}:\n" + "\n".join(ctx_lines))
                            else:
                                results.append(f"{rel_path}:{i}: {line.strip()}")

                            if len(results) >= max_results:
                                break
                except (OSError, UnicodeDecodeError):
                    continue

            if not results:
                return ToolResult(success=True, content=f"No matches for: {pattern}")

            output = "\n\n".join(results) if context > 0 else "\n".join(results)
            if len(results) >= max_results:
                output += f"\n\n... (limited to {max_results} results)"

            return ToolResult(success=True, content=output)
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e))
