// Simple MVP Chat Page
import { useEffect, useRef, useState } from 'react';
import { Send, Loader2, Trash2, Plus } from 'lucide-react';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import { useAgentStream } from '@/hooks/useAgentStream';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function Chat() {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { sessions, currentSessionId, loadSessions, createSession, switchSession, deleteSession } =
    useSessionStore();
  const { streamingMessage } = useChatStore();
  const { sendMessage, isStreaming, currentStep, maxSteps, tokenUsage, tokenLimit } =
    useAgentStream();

  const currentSession = sessions.find((s) => s.id === currentSessionId);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [currentSession?.messages, streamingMessage]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isStreaming) return;

    const message = input.trim();
    setInput('');
    await sendMessage(message);
  };

  const allMessages = [
    ...(currentSession?.messages || []),
    ...(streamingMessage ? [streamingMessage] : []),
  ];

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <div className="w-64 border-r flex flex-col" style={{ backgroundColor: 'var(--bg-sidebar)', borderColor: 'var(--border-color)' }}>
        <div className="p-4">
          <button
            onClick={() => createSession()}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors"
            style={{ backgroundColor: 'var(--accent-primary)', color: 'white' }}
            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--accent-hover)'}
            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'var(--accent-primary)'}
          >
            <Plus className="w-5 h-5" />
            新对话
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-2">
          {sessions.map((session) => (
            <div
              key={session.id}
              className="group flex items-center justify-between px-3 py-2 mb-1 rounded-lg cursor-pointer transition-colors"
              style={{
                backgroundColor: session.id === currentSessionId ? 'var(--bg-hover)' : 'transparent',
              }}
              onMouseEnter={(e) => {
                if (session.id !== currentSessionId) {
                  e.currentTarget.style.backgroundColor = 'var(--bg-hover)';
                }
              }}
              onMouseLeave={(e) => {
                if (session.id !== currentSessionId) {
                  e.currentTarget.style.backgroundColor = 'transparent';
                }
              }}
              onClick={() => switchSession(session.id)}
            >
              <span className="flex-1 truncate text-sm">{session.title}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  deleteSession(session.id);
                }}
                className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-100 transition-opacity"
              >
                <Trash2 className="w-4 h-4 text-red-500" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Status Bar */}
        {isStreaming && (
          <div className="px-4 py-2 text-sm flex items-center gap-4" style={{ backgroundColor: 'var(--bg-secondary)', borderBottom: '1px solid var(--border-color)' }}>
            <span>步骤 {currentStep}/{maxSteps}</span>
            <span>Token: {tokenUsage}/{tokenLimit}</span>
            <Loader2 className="w-4 h-4 animate-spin" />
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-3xl mx-auto py-4">
            {allMessages.map((message) => (
              <div key={message.id} className="mb-4 fade-in">
                {message.role === 'user' ? (
                  <div className="flex justify-end">
                    <div
                      className="max-w-[70%] rounded-2xl px-4 py-3"
                      style={{
                        backgroundColor: 'var(--bg-user-message)',
                        color: 'var(--text-user-message)',
                      }}
                    >
                      {message.content}
                    </div>
                  </div>
                ) : (
                  <div className="flex justify-start">
                    <div className="max-w-[70%]">
                      {message.thinking && (
                        <details className="mb-2 text-sm italic" style={{ color: 'var(--text-secondary)' }}>
                          <summary className="cursor-pointer">思考过程...</summary>
                          <div className="mt-2 whitespace-pre-wrap">{message.thinking}</div>
                        </details>
                      )}
                      <div
                        className="rounded-2xl px-4 py-3"
                        style={{
                          backgroundColor: 'var(--bg-assistant-message)',
                          color: 'var(--text-assistant)',
                        }}
                      >
                        <div className="markdown-content text-sm">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {message.content || (message.isStreaming ? '' : '...')}
                          </ReactMarkdown>
                        </div>
                        {message.isStreaming && message.content && <span className="cursor" />}
                      </div>
                      {message.toolCalls && message.toolCalls.length > 0 && (
                        <div className="mt-2 space-y-2">
                          {message.toolCalls.map((tc, idx) => (
                            <div
                              key={idx}
                              className="text-xs p-3 rounded-lg"
                              style={{ backgroundColor: 'var(--bg-secondary)' }}
                            >
                              <div className="font-semibold mb-1">🔧 {tc.tool}</div>
                              {tc.result && (
                                <div className={tc.result.success ? 'text-green-600' : 'text-red-600'}>
                                  {tc.result.success ? '✓ 成功' : '✗ 失败'}
                                  {tc.result.execution_time && ` (${tc.result.execution_time.toFixed(2)}s)`}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input */}
        <div className="border-t p-4" style={{ backgroundColor: 'var(--bg-primary)', borderColor: 'var(--border-color)' }}>
          <form onSubmit={handleSubmit} className="max-w-3xl mx-auto">
            <div className="flex gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                    handleSubmit(e);
                  }
                }}
                placeholder="发送消息... (Cmd/Ctrl + Enter 发送)"
                rows={1}
                className="flex-1 resize-none rounded-lg border px-4 py-3 focus:outline-none focus:ring-2 max-h-[200px]"
                style={{
                  backgroundColor: 'var(--bg-secondary)',
                  borderColor: 'var(--border-color)',
                  color: 'var(--text-primary)',
                  minHeight: '52px',
                }}
                disabled={isStreaming}
              />
              <button
                type="submit"
                disabled={isStreaming || !input.trim()}
                className="flex items-center justify-center rounded-lg px-4 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                style={{
                  backgroundColor: 'var(--accent-primary)',
                  minHeight: '52px',
                  minWidth: '52px',
                }}
                onMouseEnter={(e) => !isStreaming && input.trim() && (e.currentTarget.style.backgroundColor = 'var(--accent-hover)')}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'var(--accent-primary)'}
              >
                {isStreaming ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
