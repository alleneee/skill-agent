// 用于流式传输 agents 输出的 SSE 客户端
import type { AgentRequest, StreamEvent } from '@/types/agent';

export class SSEClient {
  private controller: AbortController | null = null;

  async stream(
    request: AgentRequest,
    onEvent: (event: StreamEvent) => void,
    onError?: (error: Error) => void
  ): Promise<void> {
    // 创建中止控制器，用于取消请求
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

        // 解码数据块并追加到缓冲区
        buffer += decoder.decode(value, { stream: true });

        // 按换行拆分
        const lines = buffer.split('\n');

        // 保留最后一行的未完整部分
        buffer = lines.pop() || '';

        // 处理完整行
        for (const line of lines) {
          if (!line.trim()) continue;

          // 解析 SSE 格式："data: {...}"
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6); // 移除 "data: " 前缀

            try {
              const event: StreamEvent = JSON.parse(dataStr);
              onEvent(event);

              // 如果完成或出错则停止
              if (event.type === 'done' || event.type === 'error') {
                return;
              }
            } catch (e) {
              console.error('Failed to parse SSE event:', e);
            }
          } else if (line.startsWith('event: done')) {
            // 流式传输完成
            return;
          }
        }
      }
    } catch (error) {
      if (error instanceof Error) {
        // 用户手动中止时不抛错
        if (error.name === 'AbortError') {
          return;
        }
        onError?.(error);
      }
    } finally {
      this.controller = null;
    }
  }

  // 取消正在进行的流
  cancel(): void {
    this.controller?.abort();
  }
}
