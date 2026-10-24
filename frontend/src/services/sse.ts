import type { ChatEvent } from "@/types";

/**
 * SSE client over fetch POST (EventSource cannot POST with cookies/body).
 * Parses the backend's `event: <type>\ndata: <json>\n\n` frames and gives the
 * caller an AbortController for the Stop button / navigation cleanup.
 */
export async function streamChatEvents(
  conversationId: string,
  content: string,
  onEvent: (event: ChatEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const resp = await fetch(`/api/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ content }),
    signal,
  });

  if (!resp.ok || !resp.body) {
    let message = `HTTP ${resp.status}`;
    try {
      const body = await resp.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      /* keep default */
    }
    onEvent({ type: "error", data: { code: `http_${resp.status}`, message } });
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Frames are separated by a blank line.
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const event = parseFrame(frame);
      if (event) onEvent(event);
    }
  }
}

function parseFrame(frame: string): ChatEvent | null {
  let type: string | null = null;
  let dataLine = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event: ")) type = line.slice(7).trim();
    else if (line.startsWith("data: ")) dataLine = line.slice(6);
  }
  if (!type) return null;
  try {
    return { type, data: JSON.parse(dataLine) } as ChatEvent;
  } catch {
    return null;
  }
}
