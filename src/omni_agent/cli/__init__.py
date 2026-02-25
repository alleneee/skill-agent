"""Omni Agent CLI 模块。

This module provides an interactive command-line interface for Omni Agent.

Usage:
    omni-agents [OPTIONS]

Example:
    omni-agents --workspace /path/to/project
"""
from omni_agent.cli.commands import AVAILABLE_COMMANDS
from omni_agent.cli.display import Colors
from omni_agent.cli.main import main

__all__ = ["main", "Colors", "AVAILABLE_COMMANDS"]
