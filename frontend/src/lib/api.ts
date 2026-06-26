import type { StreamEvent } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// shape the backend expects in the `history` field. matches the
// ChatTurn pydantic model on the python side, so don't drift these.
export interface ChatTurn {
  role: "user" | "assistant";
  text: string;
}

// streams the chat endpoint as a sequence of typed events. we don't
// use the built-in EventSource because it only supports GET and the
// chat endpoint is POST.
//
// instead we read the response body line by line, parse the `data:`
// prefixed payloads, and yield each event. the consumer can decide
// what to render in real time.
//
// `history` carries previous turns so the backend can reason in
// context. for the first message in a conversation, pass an empty
// array.
export async function* streamChat(
  query: string,
  history: ChatTurn[],
  signal: AbortSignal,
): AsyncGenerator<StreamEvent, void, unknown> {
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, history }),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(
      `chat stream failed: ${response.status} ${response.statusText}`,
    );
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  // sse frames are separated by a blank line. we keep an internal
  // buffer because tcp doesn't respect line boundaries and a single
  // chunk may contain partial events.
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      const trimmed = frame.trim();
      if (!trimmed || !trimmed.startsWith("data:")) continue;

      const payload = trimmed.slice(5).trim();
      try {
        const event = JSON.parse(payload) as StreamEvent;
        yield event;
      } catch {
        // malformed event — log to console and keep going. one bad
        // frame shouldn't kill the whole stream.
        console.warn("malformed sse frame", payload);
      }
    }
  }
}