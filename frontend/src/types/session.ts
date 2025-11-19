// Session types for managing conversation history

import type { Message } from './message';

export interface Session {
  id: string;
  title: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
}

export interface SessionCreate {
  title?: string;
}

export interface SessionUpdate {
  title: string;
}
