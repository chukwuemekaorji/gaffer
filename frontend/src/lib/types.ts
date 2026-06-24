// types mirror what the fastapi `/chat/stream` endpoint emits.
// keeping the shape narrow on purpose — anything we don't render
// gets dropped at the api boundary so this file stays the only
// place we maintain.

export type Route =
  | "stats"
  | "tactical_rag"
  | "recent_rag"
  | "web_search"
  | "refuse";

export type SourceKind = "chunk" | "stat" | "web";

export interface Source {
  id: string;             // 'S1', 'S2', ...
  kind: SourceKind;
  title: string;
  url: string | null;
  published_at?: string | null;
}

export interface Decision {
  routes: Route[];
  reasoning: string;
}

// what a single message in the conversation thread holds. user
// messages are simple strings; gaffer messages carry decision,
// sources, latency, and the streaming/error flags the ui needs to
// render different states.
export type Message =
  | {
      id: string;
      role: "user";
      text: string;
    }
  | {
      id: string;
      role: "assistant";
      text: string;
      decision?: Decision;
      sources: Source[];
      streaming: boolean;
      latency_ms?: number;
      error?: string;
    };

// shape of each event the stream emits. matches the discriminated
// union the api yields per `data:` line.
export type StreamEvent =
  | { type: "decision"; data: Decision }
  | { type: "sources"; data: Source[] }
  | { type: "token"; data: string }
  | { type: "done"; data: { latency_ms: number } };