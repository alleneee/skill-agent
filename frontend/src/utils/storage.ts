// Local storage utilities for session management

const SESSIONS_KEY = 'fastapi-agent-sessions';
const CURRENT_SESSION_KEY = 'fastapi-agent-current-session';

export interface StorageSession {
  id: string;
  title: string;
  messages: any[];
  createdAt: string;
  updatedAt: string;
}

export const sessionStorage = {
  // Get all sessions
  getSessions(): StorageSession[] {
    const data = localStorage.getItem(SESSIONS_KEY);
    return data ? JSON.parse(data) : [];
  },

  // Get session by ID
  getSession(id: string): StorageSession | null {
    const sessions = this.getSessions();
    return sessions.find((s) => s.id === id) || null;
  },

  // Save session
  saveSession(session: StorageSession): void {
    const sessions = this.getSessions();
    const index = sessions.findIndex((s) => s.id === session.id);

    if (index >= 0) {
      sessions[index] = session;
    } else {
      sessions.unshift(session);
    }

    localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions));
  },

  // Delete session
  deleteSession(id: string): void {
    const sessions = this.getSessions();
    const filtered = sessions.filter((s) => s.id !== id);
    localStorage.setItem(SESSIONS_KEY, JSON.stringify(filtered));

    // Clear current session if it was deleted
    if (this.getCurrentSessionId() === id) {
      this.setCurrentSessionId(null);
    }
  },

  // Get current session ID
  getCurrentSessionId(): string | null {
    return localStorage.getItem(CURRENT_SESSION_KEY);
  },

  // Set current session ID
  setCurrentSessionId(id: string | null): void {
    if (id) {
      localStorage.setItem(CURRENT_SESSION_KEY, id);
    } else {
      localStorage.removeItem(CURRENT_SESSION_KEY);
    }
  },
};
