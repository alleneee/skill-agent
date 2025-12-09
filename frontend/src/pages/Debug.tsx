import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  RefreshCw,
  ChevronRight,
  Send,
  MessageSquare,
  Zap,
  Wrench,
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  Bug,
  ArrowLeft,
} from 'lucide-react';
import { cn } from '@/utils/cn';
import {
  fetchRuns,
  fetchRunDetail,
  sendAgentRequest,
} from '@/services/debug';
import type { RunListItem, RunDetail, RunEvent, MessageData, ToolCallData } from '@/types/debug';

function formatTokens(n: number | undefined): string {
  if (!n) return '0';
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
  return String(n);
}

function JsonHighlight({ data }: { data: unknown }) {
  const json = JSON.stringify(data, null, 2);
  const highlighted = json.replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g,
    (match) => {
      let cls = 'text-orange-400';
      if (/^"/.test(match)) {
        cls = /:$/.test(match) ? 'text-purple-400' : 'text-green-400';
      } else if (/true|false/.test(match)) {
        cls = 'text-blue-400';
      } else if (/null/.test(match)) {
        cls = 'text-gray-500';
      }
      return `<span class="${cls}">${match}</span>`;
    }
  );
  return (
    <pre
      className="text-xs font-mono whitespace-pre-wrap break-words"
      dangerouslySetInnerHTML={{ __html: highlighted }}
    />
  );
}

function MessageItem({ msg }: { msg: MessageData }) {
  const roleColors: Record<string, string> = {
    system: 'bg-gray-500',
    user: 'bg-blue-500',
    assistant: 'bg-green-500',
    tool: 'bg-orange-500',
  };

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-lg p-3">
      <div className="flex items-center gap-2 mb-2">
        <span className={cn('text-[10px] font-semibold px-2 py-0.5 rounded text-white', roleColors[msg.role] || 'bg-gray-500')}>
          {msg.role}{msg.name ? ` (${msg.name})` : ''}
        </span>
      </div>
      <div className="text-xs text-gray-300 whitespace-pre-wrap max-h-48 overflow-y-auto">
        {typeof msg.content === 'string'
          ? msg.content.length > 1000 ? msg.content.slice(0, 1000) + '\n...(truncated)' : msg.content
          : JSON.stringify(msg.content, null, 2)}
      </div>
      {msg.thinking && (
        <div className="mt-2 p-2 bg-pink-500/10 border border-pink-500/30 rounded text-xs text-gray-300 max-h-32 overflow-y-auto">
          {msg.thinking.slice(0, 500)}{msg.thinking.length > 500 ? '...' : ''}
        </div>
      )}
      {msg.tool_calls && msg.tool_calls.length > 0 && (
        <div className="mt-2 space-y-2">
          {msg.tool_calls.map((tc, i) => (
            <div key={i} className="bg-gray-800 border border-gray-700 rounded p-2">
              <div className="text-xs font-mono text-orange-400 mb-1">{tc.function?.name}</div>
              <div className="text-[10px] text-gray-400">
                <JsonHighlight data={tc.function?.arguments || {}} />
              </div>
            </div>
          ))}
        </div>
      )}
      {msg.tool_call_id && (
        <div className="mt-2 text-[10px] text-gray-500">tool_call_id: {msg.tool_call_id}</div>
      )}
    </div>
  );
}

function ChainNode({ event, index }: { event: RunEvent; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const type = event.type;
  const data = event.data || {};
  const time = event.logged_at ? new Date(event.logged_at).toLocaleTimeString() : '';

  const renderContent = () => {
    switch (type) {
      case 'RUN_START':
        return <div className="text-xs text-gray-400">Run ID: {data.run_id}</div>;

      case 'STEP':
        return (
          <div className="space-y-2">
            <div className="text-xs text-gray-400">
              Tokens: {data.token_count?.toLocaleString()} / {data.token_limit?.toLocaleString()}
            </div>
            <div className="text-xs text-gray-400">
              Usage: {data.token_usage_percent?.toFixed(2)}%
            </div>
          </div>
        );

      case 'REQUEST':
        return (
          <div className="space-y-4">
            {data.messages && data.messages.length > 0 && (
              <div>
                <div className="text-[10px] font-semibold text-gray-500 uppercase mb-2">
                  Messages ({data.messages.length})
                </div>
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {data.messages.map((msg: MessageData, i: number) => (
                    <MessageItem key={i} msg={msg} />
                  ))}
                </div>
              </div>
            )}
            {data.tools && data.tools.length > 0 && (
              <div>
                <div className="text-[10px] font-semibold text-gray-500 uppercase mb-2">
                  Available Tools ({data.tools.length})
                </div>
                <div className="text-xs text-gray-400 bg-gray-900 rounded p-2">
                  {data.tools.join(', ')}
                </div>
              </div>
            )}
          </div>
        );

      case 'RESPONSE':
        return (
          <div className="space-y-4">
            {(data.input_tokens || data.output_tokens) && (
              <div>
                <div className="text-[10px] font-semibold text-gray-500 uppercase mb-2">Token Usage</div>
                <div className="text-xs text-gray-400 bg-gray-900 rounded p-2">
                  Input: {(data.input_tokens || 0).toLocaleString()} | Output: {(data.output_tokens || 0).toLocaleString()} | Total: {((data.input_tokens || 0) + (data.output_tokens || 0)).toLocaleString()}
                </div>
              </div>
            )}
            {data.thinking && (
              <div>
                <div className="text-[10px] font-semibold text-gray-500 uppercase mb-2">Thinking Process</div>
                <div className="bg-gradient-to-r from-pink-500/10 to-purple-500/10 border border-pink-500/30 rounded p-3 text-sm text-gray-300 whitespace-pre-wrap max-h-96 overflow-y-auto">
                  {data.thinking}
                </div>
              </div>
            )}
            {data.content && (
              <div>
                <div className="text-[10px] font-semibold text-gray-500 uppercase mb-2">Response Content</div>
                <div className="bg-gray-900 border border-gray-700 rounded p-3 text-xs text-gray-300 whitespace-pre-wrap max-h-72 overflow-y-auto">
                  {data.content}
                </div>
              </div>
            )}
            {data.tool_calls && data.tool_calls.length > 0 && (
              <div>
                <div className="text-[10px] font-semibold text-gray-500 uppercase mb-2">
                  Tool Calls ({data.tool_calls.length})
                </div>
                <div className="space-y-2">
                  {data.tool_calls.map((tc: ToolCallData, i: number) => (
                    <div key={i} className="bg-gray-900 border border-gray-700 rounded p-2">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-mono text-orange-400">{tc.function?.name}</span>
                        <span className="text-[10px] text-gray-500">ID: {tc.id}</span>
                      </div>
                      <div className="text-[10px] text-gray-400">
                        <JsonHighlight data={tc.function?.arguments || {}} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        );

      case 'TOOL_EXECUTION':
        return (
          <div className="space-y-4">
            <div>
              <div className="text-[10px] font-semibold text-gray-500 uppercase mb-2">Arguments</div>
              <div className="bg-gray-900 border border-gray-700 rounded p-2 max-h-40 overflow-y-auto">
                <JsonHighlight data={data.arguments || {}} />
              </div>
            </div>
            {data.success && data.result && (
              <div>
                <div className="text-[10px] font-semibold text-gray-500 uppercase mb-2">
                  Result {data.result_length ? `(${data.result_length} chars)` : ''}
                </div>
                <div className="bg-gray-900 border border-gray-700 rounded p-2 text-xs text-gray-300 whitespace-pre-wrap max-h-72 overflow-y-auto">
                  {data.result}
                </div>
              </div>
            )}
            {!data.success && data.error && (
              <div>
                <div className="text-[10px] font-semibold text-red-400 uppercase mb-2">Error</div>
                <div className="bg-red-500/10 border border-red-500/30 rounded p-2 text-xs text-red-400">
                  {data.error}
                </div>
              </div>
            )}
          </div>
        );

      case 'COMPLETION':
        return (
          <div>
            <div className="text-[10px] font-semibold text-gray-500 uppercase mb-2">Final Response</div>
            <div className="bg-gray-900 border border-gray-700 rounded p-3 text-xs text-gray-300 whitespace-pre-wrap max-h-96 overflow-y-auto">
              {data.final_response}
            </div>
          </div>
        );

      default:
        return <JsonHighlight data={data} />;
    }
  };

  const getNodeConfig = () => {
    switch (type) {
      case 'RUN_START':
        return { icon: Zap, color: 'bg-gray-500', label: 'S', title: 'Run Started', subtitle: `Run ID: ${data.run_id}` };
      case 'STEP':
        return { icon: Clock, color: 'bg-blue-500', label: String(data.step), title: `Step ${data.step} / ${data.max_steps}`, subtitle: `Token usage: ${data.token_usage_percent?.toFixed(1) || 0}%` };
      case 'REQUEST':
        return { icon: MessageSquare, color: 'bg-purple-500', label: 'R', title: 'LLM Request', subtitle: `${data.messages?.length || 0} messages, ${data.tools?.length || 0} tools` };
      case 'RESPONSE':
        return { icon: Zap, color: 'bg-green-500', label: 'A', title: 'LLM Response', subtitle: data.content?.slice(0, 60) || '(no content)' };
      case 'TOOL_EXECUTION':
        return { icon: Wrench, color: 'bg-orange-500', label: 'T', title: data.tool_name || 'Tool', subtitle: JSON.stringify(data.arguments || {}).slice(0, 50) };
      case 'COMPLETION':
        return { icon: CheckCircle, color: 'bg-cyan-500', label: 'C', title: 'Completed', subtitle: `${data.total_steps} steps, reason: ${data.reason}` };
      default:
        return { icon: Bug, color: 'bg-gray-500', label: '?', title: type, subtitle: '' };
    }
  };

  const config = getNodeConfig();
  const hasThinking = type === 'RESPONSE' && data.thinking;
  const hasToolCalls = type === 'RESPONSE' && data.tool_calls && data.tool_calls.length > 0;
  const isToolSuccess = type === 'TOOL_EXECUTION' && data.success;
  const isToolError = type === 'TOOL_EXECUTION' && !data.success;

  return (
    <>
      {index > 0 && <div className="w-0.5 h-3 bg-gradient-to-b from-gray-700 to-cyan-500/30 ml-6" />}
      <div className="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden">
        <div
          className="p-3 flex items-center gap-3 cursor-pointer hover:bg-gray-750"
          onClick={() => setExpanded(!expanded)}
        >
          <div className={cn('w-6 h-6 rounded flex items-center justify-center text-[10px] font-bold text-white', config.color)}>
            {config.label}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-medium flex items-center gap-2">
              {config.title}
              {hasThinking && <span className="text-[9px] px-1.5 py-0.5 rounded bg-pink-500 text-white">thinking</span>}
              {hasToolCalls && <span className="text-[9px] px-1.5 py-0.5 rounded bg-orange-500 text-white">{data.tool_calls?.length} tools</span>}
              {isToolSuccess && <span className="text-[9px] px-1.5 py-0.5 rounded bg-green-500 text-white">OK</span>}
              {isToolError && <span className="text-[9px] px-1.5 py-0.5 rounded bg-red-500 text-white">ERR</span>}
            </div>
            <div className="text-[10px] text-gray-500 truncate">{config.subtitle}</div>
          </div>
          <div className="flex items-center gap-3 text-[10px] text-gray-500 font-mono">
            {type === 'STEP' && <span>{formatTokens(data.token_count)} tokens</span>}
            {type === 'REQUEST' && <span>{formatTokens(data.token_count)} tokens</span>}
            {type === 'RESPONSE' && (data.input_tokens || data.output_tokens) && (
              <span>{formatTokens(data.input_tokens)} in / {formatTokens(data.output_tokens)} out</span>
            )}
            {type === 'TOOL_EXECUTION' && <span>{data.execution_time_seconds?.toFixed(2)}s</span>}
            <span>{time}</span>
          </div>
          <ChevronRight className={cn('w-4 h-4 text-gray-500 transition-transform', expanded && 'rotate-90')} />
        </div>
        {expanded && (
          <div className="p-3 pt-0 border-t border-gray-700 bg-gray-850">
            {renderContent()}
          </div>
        )}
      </div>
    </>
  );
}

export default function Debug() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [currentRun, setCurrentRun] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [input, setInput] = useState('');
  const [useTravelTeam, setUseTravelTeam] = useState(false);
  const [sending, setSending] = useState(false);
  const [allExpanded, setAllExpanded] = useState(false);

  const loadRuns = useCallback(async () => {
    try {
      const data = await fetchRuns();
      setRuns(data);
    } catch (err) {
      console.error('Failed to load runs:', err);
    }
  }, []);

  const loadRunDetail = useCallback(async (runId: string) => {
    setLoading(true);
    try {
      const data = await fetchRunDetail(runId);
      setCurrentRun(data);
    } catch (err) {
      console.error('Failed to load run detail:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSend = async () => {
    if (!input.trim() || sending) return;
    setSending(true);
    try {
      await sendAgentRequest({ message: input, useTravelTeam });
      setInput('');
      await loadRuns();
      if (runs.length > 0) {
        await loadRunDetail(runs[0].run_id);
      }
    } catch (err) {
      alert(`Error: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setSending(false);
    }
  };

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  const totalInputTokens = currentRun?.events
    .filter((e) => e.type === 'RESPONSE')
    .reduce((sum, e) => sum + (e.data?.input_tokens || 0), 0) || 0;
  const totalOutputTokens = currentRun?.events
    .filter((e) => e.type === 'RESPONSE')
    .reduce((sum, e) => sum + (e.data?.output_tokens || 0), 0) || 0;
  const totalRequests = currentRun?.events.filter((e) => e.type === 'REQUEST').length || 0;
  const totalTools = currentRun?.events.filter((e) => e.type === 'TOOL_EXECUTION').length || 0;

  const firstRequest = currentRun?.events.find((e) => e.type === 'REQUEST');
  const userMessage = firstRequest?.data?.messages?.find((m: MessageData) => m.role === 'user');
  const taskPreview = userMessage?.content?.slice(0, 100) || '';

  return (
    <div className="flex h-screen bg-gray-900 text-gray-100">
      {/* Sidebar */}
      <div className="w-80 flex-shrink-0 flex flex-col bg-gray-950 border-r border-gray-800">
        <div className="p-3 border-b border-gray-800 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors">
            <ArrowLeft className="w-4 h-4" />
            <span className="text-xs">Back to Chat</span>
          </Link>
          <div className="flex items-center gap-2">
            <Bug className="w-4 h-4 text-cyan-400" />
            <span className="text-sm font-semibold">Debug</span>
          </div>
        </div>

        <div className="p-3 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              placeholder="Enter request..."
              className="flex-1 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-cyan-500"
            />
            <button
              onClick={() => setUseTravelTeam(!useTravelTeam)}
              className={cn(
                'px-2 py-2 rounded text-[10px] font-medium border transition-colors',
                useTravelTeam
                  ? 'bg-orange-500 text-white border-orange-500'
                  : 'bg-transparent text-gray-400 border-gray-700 hover:border-orange-500'
              )}
            >
              Travel
            </button>
            <button
              onClick={handleSend}
              disabled={!input.trim() || sending}
              className="p-2 bg-cyan-500 text-white rounded hover:bg-cyan-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </button>
          </div>
        </div>

        <div className="p-3 border-b border-gray-800 flex items-center justify-between">
          <span className="text-[10px] font-semibold text-gray-500 uppercase">Agent Runs</span>
          <button onClick={loadRuns} className="p-1 hover:bg-gray-800 rounded">
            <RefreshCw className="w-3 h-3 text-gray-500" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {runs.length === 0 ? (
            <div className="text-center text-gray-500 text-xs py-8">No runs yet</div>
          ) : (
            runs.map((run) => (
              <div
                key={run.run_id}
                onClick={() => loadRunDetail(run.run_id)}
                className={cn(
                  'p-3 rounded cursor-pointer border transition-colors',
                  currentRun?.run_id === run.run_id
                    ? 'bg-gray-800 border-cyan-500'
                    : 'bg-transparent border-transparent hover:bg-gray-800/50 hover:border-gray-700'
                )}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-mono text-cyan-400">{run.run_id}</span>
                  <span className={cn('flex items-center gap-1 text-[10px]', run.success ? 'text-green-400' : 'text-red-400')}>
                    {run.success ? <CheckCircle className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                    {run.success ? 'OK' : 'ERR'}
                  </span>
                </div>
                <div className="flex gap-3 text-[10px] text-gray-500 font-mono">
                  <span>{run.total_steps} steps</span>
                  <span>{run.total_tool_calls} tools</span>
                  <span>{formatTokens(run.final_token_count)}</span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="w-8 h-8 animate-spin text-cyan-500" />
          </div>
        ) : currentRun ? (
          <div className="max-w-4xl mx-auto">
            <div className="flex items-center justify-between mb-4 pb-4 border-b border-gray-800">
              <div>
                <h2 className="text-lg font-semibold">
                  Run <span className="text-cyan-400 font-mono">#{currentRun.run_id}</span>
                </h2>
              </div>
              <div className="flex items-center gap-4 text-xs">
                <div className="flex items-center gap-1">
                  <span className="font-mono font-semibold">{currentRun.summary.total_steps}</span>
                  <span className="text-gray-500">steps</span>
                </div>
                <div className="flex items-center gap-1">
                  <span className="font-mono font-semibold">{totalRequests}</span>
                  <span className="text-gray-500">requests</span>
                </div>
                <div className="flex items-center gap-1">
                  <span className="font-mono font-semibold">{totalTools}</span>
                  <span className="text-gray-500">tools</span>
                </div>
                <div className="flex items-center gap-1">
                  <span className="font-mono font-semibold">{formatTokens(totalInputTokens)}</span>
                  <span className="text-gray-500">in</span>
                </div>
                <div className="flex items-center gap-1">
                  <span className="font-mono font-semibold">{formatTokens(totalOutputTokens)}</span>
                  <span className="text-gray-500">out</span>
                </div>
                <button
                  onClick={() => setAllExpanded(!allExpanded)}
                  className="px-2 py-1 text-[10px] bg-gray-800 hover:bg-gray-700 rounded border border-gray-700"
                >
                  {allExpanded ? 'Collapse All' : 'Expand All'}
                </button>
              </div>
            </div>

            {taskPreview && (
              <div className="mb-4 p-3 bg-gray-800 border border-gray-700 rounded-lg">
                <span className="text-blue-400 text-xs font-medium mr-2">Task:</span>
                <span className="text-xs text-gray-300">
                  {taskPreview}{userMessage?.content && userMessage.content.length > 100 ? '...' : ''}
                </span>
              </div>
            )}

            <div className="space-y-1">
              {currentRun.events.map((event, i) => (
                <ChainNode key={i} event={event} index={i} />
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-gray-500">
            <Bug className="w-12 h-12 mb-4 opacity-30" />
            <h3 className="text-sm font-medium">Select a run to debug</h3>
            <p className="text-xs">Choose from the list to inspect execution chain</p>
          </div>
        )}
      </div>
    </div>
  );
}
