"""追踪查看器，用于分析工作流执行。"""

import json
from pathlib import Path


class TraceViewer:
    """View and analyze trace logs."""

    def __init__(self, trace_dir: str | None = None):
        """Initialize viewer.

        Args:
            trace_dir: Trace directory (defaults to ~/.omni-agents/traces/)
        """
        if trace_dir:
            self.trace_dir = Path(trace_dir)
        else:
            self.trace_dir = Path.home() / ".omni-agents" / "traces"

    def list_traces(self, limit: int = 10):
        """List recent traces."""
        if not self.trace_dir.exists():
            print("No traces found")
            return

        traces = sorted(
            self.trace_dir.glob("trace_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:limit]

        print(f"\n{'=' * 80}")
        print(
            f"Recent Traces (showing {len(traces)} of {len(list(self.trace_dir.glob('trace_*.jsonl')))})"
        )
        print(f"{'=' * 80}\n")

        for i, trace_file in enumerate(traces, 1):
            summary_file = trace_file.with_suffix(".summary.json")
            if summary_file.exists():
                with open(summary_file) as f:
                    summary = json.load(f)
                    print(f"{i}. {trace_file.name}")
                    print(f"   Trace ID: {summary.get('trace_id', 'N/A')}")
                    print(f"   Duration: {summary.get('total_duration_seconds', 0):.2f}s")
                    print(f"   Events: {summary.get('total_events', 0)}")
                    print(f"   Agents: {len(summary.get('agents', []))}")
                    print(f"   Tasks: {len(summary.get('tasks', []))}")
                    print()
            else:
                print(f"{i}. {trace_file.name}")
                print("   (Summary not available)")
                print()

    def view_trace(self, trace_file: str):
        """View detailed trace information."""
        trace_path = self.trace_dir / trace_file
        if not trace_path.exists():
            print(f"Trace file not found: {trace_file}")
            return

        summary_path = trace_path.with_suffix(".summary.json")
        if summary_path.exists():
            self._print_summary(summary_path)

        print(f"\n{'=' * 80}")
        print("Event Timeline")
        print(f"{'=' * 80}\n")

        with open(trace_path) as f:
            for line in f:
                event = json.loads(line)
                self._print_event(event)

    def _print_summary(self, summary_path: Path):
        """Print trace summary."""
        with open(summary_path) as f:
            summary = json.load(f)

        print(f"\n{'=' * 80}")
        print(f"Trace Summary: {summary.get('trace_id', 'N/A')}")
        print(f"{'=' * 80}\n")

        print(f"Duration: {summary.get('total_duration_seconds', 0):.2f}s")
        print(f"Total Events: {summary.get('total_events', 0)}")
        print(
            f"Total Tokens: {summary.get('total_tokens', 0)} (input: {summary.get('total_input_tokens', 0)}, output: {summary.get('total_output_tokens', 0)})"
        )
        print()

        print("Event Counts:")
        for event_type, count in summary.get("event_counts", {}).items():
            print(f"  - {event_type}: {count}")
        print()

        agents = summary.get("agents", [])
        if agents:
            print("Agents:")
            for agent in agents:
                status = "+" if agent.get("success") else "x"
                print(f"  {status} {agent.get('agent_name')} ({agent.get('agent_id')})")
                print(
                    f"      Steps: {agent.get('steps', 0)}, Time: {agent.get('elapsed', 0):.2f}s, Tokens: {agent.get('total_tokens', 0)}"
                )
            print()

        tasks = summary.get("tasks", [])
        if tasks:
            print("Tasks:")
            for task in tasks:
                print(f"  - {task.get('task_id')}: {task.get('status')}")
                print(f"      Time: {task.get('elapsed', 0):.2f}s")
            print()

        delegations = summary.get("delegations", [])
        if delegations:
            print("Delegations:")
            for delegation in delegations:
                print(f"  {delegation.get('from')} → {delegation.get('to')}")
            print()

    def _print_event(self, event: dict):
        """Print single event."""
        timestamp = event.get("timestamp", "")
        event_type = event.get("event_type", "")

        if event_type == "workflow_start":
            print(f"🚀 [{timestamp}] WORKFLOW START")
            print(f"   Type: {event.get('trace_type')}")
            print()

        elif event_type == "workflow_end":
            print(f"🏁 [{timestamp}] WORKFLOW END")
            print(f"   Success: {event.get('success')}")
            print(f"   Duration: {event.get('elapsed_seconds', 0):.2f}s")
            print()

        elif event_type == "agent_start":
            indent = "  " * event.get("depth", 0)
            print(f"{indent}👤 [{timestamp}] AGENT START")
            print(f"{indent}   Name: {event.get('agent_name')}")
            print(f"{indent}   Role: {event.get('agent_role')}")
            print(f"{indent}   Task: {event.get('task', '')[:80]}")
            print()

        elif event_type == "agent_end":
            status = "✓" if event.get("success") else "✗"
            print(f"   {status} [{timestamp}] AGENT END: {event.get('agent_name')}")
            print(
                f"      Steps: {event.get('steps', 0)}, Time: {event.get('elapsed_seconds', 0):.2f}s"
            )
            print()

        elif event_type == "task_start":
            print(f"📋 [{timestamp}] TASK START: {event.get('task_id')}")
            print(f"   Layer: {event.get('layer')}")
            print(f"   Assigned to: {event.get('assigned_to')}")
            print(f"   Depends on: {event.get('depends_on', [])}")
            print()

        elif event_type == "task_end":
            print(f"   ✓ [{timestamp}] TASK END: {event.get('task_id')}")
            print(
                f"      Status: {event.get('status')}, Time: {event.get('elapsed_seconds', 0):.2f}s"
            )
            print()

        elif event_type == "delegation":
            print(f"🔀 [{timestamp}] DELEGATION")
            print(f"   {event.get('from_agent')} → {event.get('to_member')}")
            print()

        elif event_type == "message_pass":
            print(f"💬 [{timestamp}] MESSAGE PASS")
            print(f"   {event.get('from_task')} → {event.get('to_task')}")
            print()

        elif event_type == "tool_call":
            status = "✓" if event.get("success") else "✗"
            print(f"   {status} [{timestamp}] TOOL: {event.get('tool_name')}")
            print(f"      Time: {event.get('elapsed_seconds', 0):.3f}s")

        elif event_type == "llm_call":
            print(f"   🤖 [{timestamp}] LLM: {event.get('model')}")
            print(
                f"      Tokens: {event.get('tokens', 0)}, Time: {event.get('elapsed_seconds', 0):.2f}s"
            )

    def visualize_flow(self, trace_file: str):
        """Generate ASCII flow visualization."""
        trace_path = self.trace_dir / trace_file
        if not trace_path.exists():
            print(f"Trace file not found: {trace_file}")
            return

        print(f"\n{'=' * 80}")
        print("Workflow Flow Visualization")
        print(f"{'=' * 80}\n")

        events = []
        with open(trace_path) as f:
            for line in f:
                events.append(json.loads(line))

        layers = {}
        for event in events:
            if event.get("event_type") == "task_start":
                layer = event.get("layer", 0)
                if layer not in layers:
                    layers[layer] = []
                layers[layer].append(event.get("task_id"))

        if layers:
            print("Dependency Layers:")
            for layer_num in sorted(layers.keys()):
                tasks = layers[layer_num]
                if len(tasks) == 1:
                    print(f"Layer {layer_num}: {tasks[0]}")
                else:
                    print(f"Layer {layer_num}: [{' || '.join(tasks)}]  (parallel)")
                if layer_num < max(layers.keys()):
                    print("    ↓")
            print()

        delegations = []
        for event in events:
            if event.get("event_type") == "delegation":
                delegations.append((event.get("from_agent"), event.get("to_member")))

        if delegations:
            print("Delegation Flow:")
            for from_agent, to_member in delegations:
                print(f"  {from_agent} → {to_member}")
            print()


def main():
    """CLI for trace viewer."""
    import sys

    viewer = TraceViewer()

    if len(sys.argv) == 1:
        viewer.list_traces()
    elif sys.argv[1] == "list":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        viewer.list_traces(limit=limit)
    elif sys.argv[1] == "view":
        if len(sys.argv) < 3:
            print("Usage: trace_viewer.py view <trace_file>")
            return
        viewer.view_trace(sys.argv[2])
    elif sys.argv[1] == "flow":
        if len(sys.argv) < 3:
            print("Usage: trace_viewer.py flow <trace_file>")
            return
        viewer.visualize_flow(sys.argv[2])
    else:
        print("Usage: trace_viewer.py [list|view|flow] [args]")


if __name__ == "__main__":
    main()
