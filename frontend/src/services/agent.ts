// Agent API service
import apiClient from './api';
import type { AgentRequest, AgentResponse } from '@/types/agent';

export const agentService = {
  // Execute agent task (blocking)
  async run(request: AgentRequest): Promise<AgentResponse> {
    const { data } = await apiClient.post<AgentResponse>('/agent/run', request);
    return data;
  },

  // Check health
  async health(): Promise<{ status: string }> {
    const { data } = await apiClient.get('/health');
    return data;
  },

  // Get available tools
  async getTools(): Promise<any> {
    const { data } = await apiClient.get('/tools/');
    return data;
  },
};
