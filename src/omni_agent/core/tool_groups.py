"""用于动态工具选择的工具分组与预设。"""

from enum import Enum
from typing import List, Set


class ToolGroup(Enum):
    """工具分组分类。"""

    FILE_OPS = "file_ops"
    CODE_TOOLS = "code_tools"
    SEARCH_TOOLS = "search_tools"
    MEMORY_TOOLS = "memory_tools"
    MAPS_TOOLS = "maps_tools"
    WEB_TOOLS = "web_tools"


TOOL_GROUP_MAPPING: dict[ToolGroup, List[str]] = {
    ToolGroup.FILE_OPS: ["read_file", "write_file", "edit_file", "list_dir"],
    ToolGroup.CODE_TOOLS: ["glob", "grep", "bash"],
    ToolGroup.SEARCH_TOOLS: ["search_knowledge", "web_search_exa"],
    ToolGroup.MEMORY_TOOLS: ["session_note", "recall_note", "deep_recall_memory"],
    ToolGroup.MAPS_TOOLS: [
        "maps_direction",
        "maps_search_nearby",
        "maps_geocode",
        "maps_weather",
        "maps_route_planning",
        "maps_text_search",
    ],
    ToolGroup.WEB_TOOLS: ["fetch", "web_search_exa"],
}


class ToolPreset(Enum):
    """预定义工具集合预设。"""

    MINIMAL = "minimal"
    CODING = "coding"
    RESEARCH = "research"
    TRAVEL = "travel"
    FULL = "full"


TOOL_PRESETS: dict[ToolPreset, List[ToolGroup]] = {
    ToolPreset.MINIMAL: [ToolGroup.FILE_OPS],
    ToolPreset.CODING: [ToolGroup.FILE_OPS, ToolGroup.CODE_TOOLS],
    ToolPreset.RESEARCH: [ToolGroup.FILE_OPS, ToolGroup.SEARCH_TOOLS, ToolGroup.WEB_TOOLS],
    ToolPreset.TRAVEL: [ToolGroup.FILE_OPS, ToolGroup.MAPS_TOOLS],
    ToolPreset.FULL: list(ToolGroup),
}


def get_tools_by_groups(groups: List[ToolGroup]) -> List[str]:
    """获取指定分组的全部工具名称。"""
    tools: Set[str] = set()
    for group in groups:
        tools.update(TOOL_GROUP_MAPPING.get(group, []))
    return list(tools)


def get_tools_by_preset(preset: ToolPreset) -> List[str]:
    """获取指定预设的全部工具名称。"""
    groups = TOOL_PRESETS.get(preset, [])
    return get_tools_by_groups(groups)


def get_tools_by_group_names(group_names: List[str]) -> List[str]:
    """获取指定分组名称（字符串）的全部工具名称。"""
    groups = []
    for name in group_names:
        try:
            groups.append(ToolGroup(name))
        except ValueError:
            continue
    return get_tools_by_groups(groups)


def get_tools_by_preset_name(preset_name: str) -> List[str]:
    """获取指定预设名称（字符串）的全部工具名称。"""
    try:
        preset = ToolPreset(preset_name)
        return get_tools_by_preset(preset)
    except ValueError:
        return []
