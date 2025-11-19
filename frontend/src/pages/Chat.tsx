// Simple MVP Chat Page
import { useEffect, useRef, useState } from 'react';
import { Send, Loader2, Trash2, Plus, Bot, User } from 'lucide-react';
import { useSessionStore } from '@/stores/sessionStore';
import { useChatStore } from '@/stores/chatStore';
import { useAgentStream } from '@/hooks/useAgentStream';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function Chat() {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { sessions, currentSessionId, loadSessions, createSession, switchSession, deleteSession } =
    useSessionStore();
  const { streamingMessage } = useChatStore();
  const { sendMessage, isStreaming, currentStep, maxSteps } =
    useAgentStream();

  const currentSession = sessions.find((s) => s.id === currentSessionId);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [currentSession?.messages, streamingMessage]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [input]);

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || isStreaming) return;

    const message = input.trim();
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    await sendMessage(message);
  };

  const allMessages = [
    ...(currentSession?.messages || []),
    ...(streamingMessage ? [streamingMessage] : []),
  ];

  return (
    <div className="flex h-screen bg-[var(--bg-primary)]">
      {/* Sidebar */}
      <div className="w-[260px] flex-shrink-0 flex flex-col bg-[var(--bg-sidebar)] text-[var(--text-sidebar)] transition-all duration-300">
        <div className="p-3">
          <button
            onClick={() => createSession()}
            className="w-full flex items-center gap-3 px-3 py-3 rounded-md border border-[var(--border-sidebar)] hover:bg-[var(--bg-sidebar-hover)] transition-colors text-sm text-left"
          >
            <Plus className="w-4 h-4" />
            New chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
          <div className="text-xs font-medium text-[var(--text-sidebar-secondary)] px-3 py-2">
            Today
          </div>
          {sessions.map((session) => (
            <div
              key={session.id}
              className="group flex items-center gap-3 px-3 py-3 rounded-md cursor-pointer hover:bg-[var(--bg-sidebar-hover)] transition-colors text-sm relative"
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
                className="absolute right-2 opacity-0 group-hover:opacity-100 p-1 hover:text-white text-[var(--text-sidebar-secondary)] transition-all"
              >
                <Trash2 className="w-4 h-4" />
              </button>
              {/* Gradient fade for long titles */}
              <div className="absolute right-8 top-0 bottom-0 w-8 bg-gradient-to-l from-[var(--bg-sidebar)] to-transparent group-hover:from-[var(--bg-sidebar-hover)] pointer-events-none" />
            </div>
          ))}
        </div>

        {/* User Profile / Settings placeholder */}
        <div className="p-3 border-t border-[var(--border-sidebar)]">
          <div className="flex items-center gap-3 px-3 py-3 rounded-md hover:bg-[var(--bg-sidebar-hover)] cursor-pointer transition-colors">
            <div className="w-8 h-8 rounded bg-green-700 flex items-center justify-center text-white font-medium text-xs">
              U
            </div>
            <div className="text-sm font-medium">User</div>
          </div>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col relative min-w-0">
        {/* Top Bar (Mobile/Tablet only usually, but keeping simple for now) */}
        <div className="h-12 flex items-center justify-center border-b border-transparent">
          <span className="text-[var(--text-secondary)] text-sm font-medium">
            Model: GPT-4o (Simulated)
          </span>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto scroll-smooth">
          <div className="max-w-3xl mx-auto px-4 pb-32 pt-4">
            {allMessages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-[60vh] text-center space-y-4">
                <div className="w-12 h-12 rounded-full bg-white shadow-sm flex items-center justify-center mb-4">
                   <Bot className="w-8 h-8 text-[var(--text-primary)]" />
                </div>
                <h2 className="text-2xl font-semibold">How can I help you today?</h2>
              </div>
            ) : (
              allMessages.map((message) => (
                <div key={message.id} className="group w-full text-[var(--text-primary)] border-b border-black/5 dark:border-white/5 border-none">
                  <div className="text-base gap-4 md:gap-6 md:max-w-3xl lg:max-w-[40rem] xl:max-w-[48rem] p-4 md:py-6 flex lg:px-0 m-auto">
                    
                    {/* Avatar */}
                    <div className="flex-shrink-0 flex flex-col relative items-end">
                      <div className="w-8 h-8 relative flex">
                        {message.role === 'user' ? (
                           <div className="bg-black/10 rounded-sm w-8 h-8 flex items-center justify-center">
                             <User className="w-5 h-5 text-gray-600" />
                           </div>
                        ) : (
                          <div className="bg-[var(--accent-primary)] rounded-sm w-8 h-8 flex items-center justify-center">
                            <Bot className="w-5 h-5 text-white" />
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Content */}
                    <div className="relative flex-1 overflow-hidden">
                      {message.role === 'user' ? (
                        <div className="font-medium">{message.content}</div>
                      ) : (
                        <div className="prose prose-slate dark:prose-invert max-w-none leading-7">
                           {message.thinking && (
                            <details className="mb-4 text-sm bg-gray-50 rounded-md border border-gray-100 open:pb-2">
                              <summary className="cursor-pointer px-3 py-2 text-gray-500 hover:text-gray-700 font-medium select-none list-none flex items-center gap-2">
                                <span className="text-xs uppercase tracking-wider">Thinking Process</span>
                              </summary>
                              <div className="px-3 pb-2 text-gray-600 whitespace-pre-wrap font-mono text-xs">
                                {message.thinking}
                              </div>
                            </details>
                          )}
                          <div className="markdown-content">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {message.content || (message.isStreaming ? '' : '...')}
                            </ReactMarkdown>
                          </div>
                          {message.isStreaming && message.content && (
                            <span className="inline-block w-2 h-4 ml-1 bg-black animate-pulse align-middle" />
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
            <div ref={messagesEndRef} className="h-4" />
          </div>
        </div>

        {/* Input Area */}
        <div className="absolute bottom-0 left-0 w-full bg-gradient-to-t from-white via-white to-transparent pt-10 pb-6">
          <div className="max-w-3xl mx-auto px-4">
             {/* Status Indicator */}
             {isStreaming && (
              <div className="mb-2 flex justify-center">
                 <div className="bg-white shadow-sm border border-gray-100 rounded-full px-4 py-1 text-xs font-medium text-gray-500 flex items-center gap-2">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Generating response... ({currentStep}/{maxSteps})
                 </div>
              </div>
            )}

            <div className="relative flex items-end w-full p-3 bg-white border border-gray-200 shadow-[0_0_15px_rgba(0,0,0,0.1)] rounded-xl focus-within:shadow-[0_0_20px_rgba(0,0,0,0.15)] focus-within:border-gray-300 transition-all">
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
                placeholder="Message ChatGPT..."
                className="w-full max-h-[200px] py-[10px] pr-10 md:py-3.5 md:pr-12 bg-transparent border-0 focus:ring-0 resize-none outline-none text-base"
                rows={1}
                style={{ minHeight: '44px' }}
                disabled={isStreaming}
              />
              <button
                onClick={() => handleSubmit()}
                disabled={!input.trim() || isStreaming}
                className="absolute right-3 bottom-3 p-1.5 rounded-md bg-black text-white disabled:bg-gray-100 disabled:text-gray-400 transition-colors"
              >
                {isStreaming ? (
                   <div className="w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
              </button>
            </div>
            <div className="text-center mt-2 text-xs text-gray-400">
              ChatGPT can make mistakes. Check important info.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
