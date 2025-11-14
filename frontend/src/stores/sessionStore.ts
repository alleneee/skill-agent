// Session management store using Zustand
import { create } from 'zustand';
import { v4 as uuidv4 } from 'uuid';
import type { Session } from '@/types/session';
import type { Message } from '@/types/message';
import { sessionStorage, type StorageSession } from '@/utils/storage';

interface SessionState {
  sessions: Session[];
  currentSessionId: string | null;

  // Actions
  loadSessions: () => void;
  createSession: (title?: string) => Session;
  switchSession: (id: string) => void;
  deleteSession: (id: string) => void;
  updateSessionTitle: (id: string, title: string) => void;
  addMessageToSession: (sessionId: string, message: Message) => void;
  getCurrentSession: () => Session | null;
}

// Convert storage session to Session type
function fromStorage(s: StorageSession): Session {
  return {
    ...s,
    createdAt: new Date(s.createdAt),
    updatedAt: new Date(s.updatedAt),
    messages: s.messages.map((m) => ({
      ...m,
      timestamp: new Date(m.timestamp),
    })),
  };
}

// Convert Session to storage format
function toStorage(s: Session): StorageSession {
  return {
    ...s,
    createdAt: s.createdAt.toISOString(),
    updatedAt: s.updatedAt.toISOString(),
    messages: s.messages.map((m) => ({
      ...m,
      timestamp: m.timestamp.toISOString(),
    })),
  };
}

export const useSessionStore = create<SessionState>((set, get) => ({
  sessions: [],
  currentSessionId: null,

  loadSessions: () => {
    const storedSessions = sessionStorage.getSessions().map(fromStorage);
    const currentId = sessionStorage.getCurrentSessionId();

    set({
      sessions: storedSessions,
      currentSessionId: currentId,
    });

    // Create initial session if none exist
    if (storedSessions.length === 0) {
      get().createSession('新对话');
    }
  },

  createSession: (title = '新对话') => {
    const newSession: Session = {
      id: uuidv4(),
      title,
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date(),
    };

    // Save to storage
    sessionStorage.saveSession(toStorage(newSession));
    sessionStorage.setCurrentSessionId(newSession.id);

    // Update state
    set((state) => ({
      sessions: [newSession, ...state.sessions],
      currentSessionId: newSession.id,
    }));

    return newSession;
  },

  switchSession: (id: string) => {
    sessionStorage.setCurrentSessionId(id);
    set({ currentSessionId: id });
  },

  deleteSession: (id: string) => {
    sessionStorage.deleteSession(id);

    set((state) => {
      const filtered = state.sessions.filter((s) => s.id !== id);

      // If deleted current session, switch to first available
      let newCurrentId = state.currentSessionId;
      if (state.currentSessionId === id) {
        newCurrentId = filtered.length > 0 ? filtered[0].id : null;
        if (newCurrentId) {
          sessionStorage.setCurrentSessionId(newCurrentId);
        }
      }

      return {
        sessions: filtered,
        currentSessionId: newCurrentId,
      };
    });

    // Create new session if none left
    const { sessions } = get();
    if (sessions.length === 0) {
      get().createSession('新对话');
    }
  },

  updateSessionTitle: (id: string, title: string) => {
    set((state) => {
      const updated = state.sessions.map((s) =>
        s.id === id ? { ...s, title, updatedAt: new Date() } : s
      );

      // Save to storage
      const session = updated.find((s) => s.id === id);
      if (session) {
        sessionStorage.saveSession(toStorage(session));
      }

      return { sessions: updated };
    });
  },

  addMessageToSession: (sessionId: string, message: Message) => {
    set((state) => {
      const updated = state.sessions.map((s) => {
        if (s.id === sessionId) {
          const newSession = {
            ...s,
            messages: [...s.messages, message],
            updatedAt: new Date(),
          };

          // Save to storage
          sessionStorage.saveSession(toStorage(newSession));

          return newSession;
        }
        return s;
      });

      return { sessions: updated };
    });
  },

  getCurrentSession: () => {
    const { sessions, currentSessionId } = get();
    return sessions.find((s) => s.id === currentSessionId) || null;
  },
}));
