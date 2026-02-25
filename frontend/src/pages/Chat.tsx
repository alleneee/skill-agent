import { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Send, Square, Trash2, Plus, Bot, User, Database, Bug, ChevronDown, ChevronRight } from 'lucide-react';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import { useAgentStream } from '@/hooks/useAgentStream';
import UserInputForm from '@/components/UserInputForm';
import MarkdownRenderer from '@/components/MarkdownRenderer';

function mergeInlineCodeToBlock(text: string): string {
  const lines = text.split('\n');
  const result: string[] = [];
  let codeLines: string[] = [];
  let inCodeSequence = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    const isCodeLine = /^`[^`]+`$/.test(line) && !line.includes('``');

    if (isCodeLine) {
      const code = line.slice(1, -1);
      codeLines.push(code);
      inCodeSequence = true;
    } else {
      if (inCodeSequence && codeLines.length >= 2) {
        result.push('```');
        result.push(...codeLines);
        result.push('```');
      } else if (codeLines.length === 1) {
        result.push('`' + codeLines[0] + '`');
      }
      codeLines = [];
      inCodeSequence = false;
      result.push(lines[i]);
    }
  }

  if (inCodeSequence && codeLines.length >= 2) {
    result.push('```');
    result.push(...codeLines);
    result.push('```');
  } else if (codeLines.length === 1) {
    result.push('`' + codeLines[0] + '`');
  }

  return result.join('\n');
}

function cleanContent(content: string): string {
  if (!content) return content;
  let cleaned = content
    .replace(/<has_function_call>[A-Za-z0-9.\-\s]*/g, '')
    .replace(/<\/has_function_call>/g, '')
    .replace(/^\s+/, '')
    .replace(/(#{1,6})([^\s#])/g, '$1 $2')
    .replace(/([^\n])(#{1,6}\s)/g, '$1\n\n$2')
    .replace(/(\d+\.)\*\*\s*([^*]+)\*\*/g, '$1 **$2**')
    .replace(/-([^\s\n])/g, '- $1');

  cleaned = mergeInlineCodeToBlock(cleaned);
  return cleaned;
}

interface ThinkingBlockProps {
  content: string;
}

function ThinkingBlock({ content }: ThinkingBlockProps) {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <div className="thinking-block">
      <button className="thinking-toggle" onClick={() => setIsOpen(!isOpen)}>
        {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        <span>Thinking Process</span>
      </button>
      {isOpen && <div className="thinking-content">{content}</div>}
    </div>
  );
}

export default function Chat() {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { sessions, currentSessionId, loadSessions, createSession, switchSession, deleteSession } =
    useSessionStore();
  const { streamingMessage } = useChatStore();
  const {
    sendMessage,
    cancelStream,
    isStreaming,
    currentStep,
    maxSteps,
    pendingUserInput,
    isWaitingForInput,
    clearPendingUserInput,
  } = useAgentStream();

  const handleUserInputSubmit = useCallback(
    async (values: Record<string, string>) => {
      clearPendingUserInput();
      const inputSummary = Object.entries(values)
        .map(([k, v]) => `${k}: ${v}`)
        .join(', ');
      await sendMessage(`[用户输入] ${inputSummary}`);
    },
    [clearPendingUserInput, sendMessage]
  );

  const handleUserInputCancel = useCallback(() => {
    clearPendingUserInput();
  }, [clearPendingUserInput]);

  const currentSession = sessions.find((s) => s.id === currentSessionId);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [currentSession?.messages, streamingMessage]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [input]);

  const handleSubmit = useCallback(
    async (e?: React.FormEvent) => {
      e?.preventDefault();
      if (!input.trim() || isStreaming) return;
      const message = input.trim();
      setInput('');
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
      await sendMessage(message);
    },
    [input, isStreaming, sendMessage]
  );

  const allMessages = useMemo(() => {
    const showStreamingMessage = streamingMessage && streamingMessage.content;
    const messages = [
      ...(currentSession?.messages || []),
      ...(showStreamingMessage ? [streamingMessage] : []),
    ];
    return messages.map((msg) => ({
      ...msg,
      content: msg.role === 'assistant' ? cleanContent(msg.content) : msg.content,
    }));
  }, [currentSession?.messages, streamingMessage]);

  return (
    <div className="flex h-screen bg-[var(--bg-primary)]">
      <aside className="w-64 flex-shrink-0 flex flex-col bg-[var(--bg-sidebar)] border-r border-[var(--border-sidebar)]">
        <div className="p-3">
          <button
            onClick={() => createSession()}
            className="w-full flex items-center gap-2 px-3 py-2.5 rounded-lg border border-[var(--border-sidebar)] hover:bg-[var(--bg-sidebar-hover)] transition-colors text-sm font-medium"
          >
            <Plus className="w-4 h-4" />
            New chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-2">
          <div className="text-xs font-medium text-[var(--text-sidebar-secondary)] px-3 py-2">
            Recent
          </div>
          {sessions.map((session) => (
            <div
              key={session.id}
              className={`group flex items-center gap-2 px-3 py-2.5 rounded-lg cursor-pointer transition-colors text-sm relative mb-0.5 ${
                session.id === currentSessionId
                  ? 'bg-[var(--bg-sidebar-hover)]'
                  : 'hover:bg-[var(--bg-sidebar-hover)]'
              }`}
              onClick={() => switchSession(session.id)}
            >
              <div className="flex-1 truncate pr-6 text-[var(--text-sidebar)]">
                {session.title || 'New Chat'}
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  deleteSession(session.id);
                }}
                className="absolute right-2 opacity-0 group-hover:opacity-100 p-1 hover:text-red-500 text-[var(--text-sidebar-secondary)] transition-all"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>

        <div className="p-3 border-t border-[var(--border-sidebar)] space-y-1">
          <Link
            to="/knowledge"
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-[var(--bg-sidebar-hover)] transition-colors text-sm"
          >
            <div className="w-7 h-7 rounded-md bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center">
              <Database className="w-3.5 h-3.5 text-white" />
            </div>
            <span className="font-medium">Knowledge</span>
          </Link>

          <a
            href={import.meta.env.VITE_LANGFUSE_URL || 'https://cloud.langfuse.com'}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-[var(--bg-sidebar-hover)] transition-colors text-sm"
          >
            <div className="w-7 h-7 rounded-md bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center">
              <Bug className="w-3.5 h-3.5 text-white" />
            </div>
            <span className="font-medium">Debug</span>
          </a>

          <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-[var(--bg-sidebar-hover)] cursor-pointer transition-colors">
            <div className="w-7 h-7 rounded-md bg-[var(--accent-green)] flex items-center justify-center text-white font-medium text-xs">
              U
            </div>
            <span className="text-sm font-medium">User</span>
          </div>
        </div>
      </aside>

      <main className="flex-1 flex flex-col relative min-w-0">
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-3xl mx-auto px-6 pb-36 pt-8">
            {allMessages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-[60vh] text-center">
                <div className="w-14 h-14 rounded-2xl bg-[var(--accent-green)] flex items-center justify-center mb-6">
                  <Bot className="w-7 h-7 text-white" />
                </div>
                <h2 className="text-2xl font-semibold mb-2">How can I help you today?</h2>
                <p className="text-[var(--text-secondary)] text-sm">
                  Ask me anything or start a conversation
                </p>
              </div>
            ) : (
              allMessages.map((message) => (
                <div key={message.id} className="mb-6 fade-in">
                  <div className="flex gap-4">
                    <div className="flex-shrink-0">
                      {message.role === 'user' ? (
                        <div className="w-8 h-8 rounded-lg bg-[var(--bg-secondary)] flex items-center justify-center">
                          <User className="w-4 h-4 text-[var(--text-secondary)]" />
                        </div>
                      ) : (
                        <div className="w-8 h-8 rounded-lg bg-[var(--accent-green)] flex items-center justify-center">
                          <Bot className="w-4 h-4 text-white" />
                        </div>
                      )}
                    </div>

                    <div className="flex-1 min-w-0 pt-0.5">
                      {message.role === 'user' ? (
                        <p className="font-medium leading-relaxed">{message.content}</p>
                      ) : (
                        <>
                          {message.thinking && <ThinkingBlock content={message.thinking} />}
                          <MarkdownRenderer
                            content={message.content || (message.isStreaming ? '' : '...')}
                          />
                          {message.isStreaming && message.content && (
                            <span className="inline-block w-1.5 h-4 ml-0.5 bg-[var(--accent-green)] animate-pulse rounded-sm" />
                          )}
                        </>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}

            {isWaitingForInput && pendingUserInput && (
              <div className="mt-4">
                <UserInputForm
                  fields={pendingUserInput.fields}
                  context={pendingUserInput.context}
                  onSubmit={handleUserInputSubmit}
                  onCancel={handleUserInputCancel}
                />
              </div>
            )}

            {isStreaming && !streamingMessage?.content && (
              <div className="mb-6 fade-in">
                <div className="flex gap-4">
                  <div className="flex-shrink-0">
                    <div className="w-8 h-8 rounded-lg bg-[var(--accent-green)] flex items-center justify-center">
                      <Bot className="w-4 h-4 text-white" />
                    </div>
                  </div>
                  <div className="flex-1 min-w-0 pt-1.5">
                    <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                      <Loader2 className="w-4 h-4 animate-spin text-[var(--accent-green)]" />
                      <span>Thinking ({currentStep}/{maxSteps})</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} className="h-4" />
          </div>
        </div>

        <div className="absolute bottom-0 left-0 w-full bg-gradient-to-t from-[var(--bg-primary)] via-[var(--bg-primary)] to-transparent pt-12 pb-6">
          <div className="max-w-3xl mx-auto px-6">
            <div className="relative bg-white rounded-2xl border border-[var(--border-color)] shadow-[var(--shadow-input)] focus-within:shadow-lg focus-within:border-[var(--accent-green)] transition-all">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSubmit();
                  }
                }}
                placeholder="Message..."
                className="w-full px-4 py-3.5 pr-12 bg-transparent border-0 focus:ring-0 resize-none outline-none text-[15px] max-h-48"
                rows={1}
                style={{ minHeight: '52px' }}
                disabled={isStreaming}
              />
              <button
                onClick={() => isStreaming ? cancelStream() : handleSubmit()}
                disabled={!isStreaming && !input.trim()}
                className={`absolute right-3 bottom-3 p-2 rounded-lg transition-colors hover:opacity-90 ${
                  isStreaming
                    ? 'bg-red-500 text-white hover:bg-red-600'
                    : 'bg-[var(--accent-green)] text-white disabled:bg-gray-200 disabled:text-gray-400'
                }`}
              >
                {isStreaming ? (
                  <Square className="w-4 h-4" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
              </button>
            </div>

            <p className="text-center mt-2.5 text-xs text-[var(--text-secondary)]">
              AI may produce inaccurate information
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
