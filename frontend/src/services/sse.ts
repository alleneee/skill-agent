// Server-Sent Events (SSE) client for streaming agent output
import type { AgentRequest, StreamEvent } from '@/types/agent';

export class SSEClient {
  private controller: AbortController | null = null;

  async stream(
    request: AgentRequest,
    onEvent: (event: StreamEvent) => void,
    onError?: (error: Error) => void
  ): Promise<void> {
    // Create abort controller for cancellation
    this.controller = new AbortController();

    try {
      const response = await fetch('/api/v1/agent/run/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
        signal: this.controller.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      if (!response.body) {
        throw new Error('No response body');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();

        if (done) {
          break;
        }

        // Decode chunk and add to buffer
        buffer += decoder.decode(value, { stream: true });

        // Split by newline
        const lines = buffer.split('\n');

        // Keep last incomplete line in buffer
        buffer = lines.pop() || '';

        // Process complete lines
        for (const line of lines) {
          if (!line.trim()) continue;

          // Parse SSE format: "data: {...}"
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6); // Remove "data: " prefix

            try {
              const event: StreamEvent = JSON.parse(dataStr);
              onEvent(event);

              // Stop if done or error
              if (event.type === 'done' || event.type === 'error') {
                return;
              }
            } catch (e) {
              console.error('Failed to parse SSE event:', e);
            }
          } else if (line.startsWith('event: done')) {
            // Stream complete
            return;
          }
        }
      }
    } catch (error) {
      if (error instanceof Error) {
        // Don't throw error if aborted by user
        if (error.name === 'AbortError') {
          return;
        }
        onError?.(error);
      }
    } finally {
      this.controller = null;
    }
  }

  // Cancel ongoing stream
  cancel(): void {
    this.controller?.abort();
  }
}
