"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";

import { ChatComposer } from "@/components/ChatComposer";
import { ChatMessage } from "@/components/ChatMessage";
import { SourcesPanel } from "@/components/SourcesPanel";
import { streamChat } from "@/lib/api";
import type { Message, Source } from "@/lib/types";

const STARTER_QUERIES = [
  "How does Carrick set up against deep blocks?",
  "Where are we in the table?",
  "Compare Bruno's role across managers.",
];

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [composerValue, setComposerValue] = useState("");
  const [busy, setBusy] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const lastAssistant = [...messages]
    .reverse()
    .find((m): m is Extract<Message, { role: "assistant" }> => m.role === "assistant");

  async function ask(query: string) {
    if (busy || !query.trim()) return;

    const userId = crypto.randomUUID();
    const assistantId = crypto.randomUUID();

    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", text: query },
      { id: assistantId, role: "assistant", text: "", sources: [], streaming: true },
    ]);
    setComposerValue("");
    setBusy(true);
    abortRef.current = new AbortController();

    try {
      for await (const event of streamChat(query, abortRef.current.signal)) {
        setMessages((prev) =>
          prev.map((m): Message => {
            if (m.id !== assistantId || m.role !== "assistant") return m;
            switch (event.type) {
              case "decision":
                return { ...m, decision: event.data };
              case "sources":
                return { ...m, sources: event.data as Source[] };
              case "token":
                return { ...m, text: m.text + event.data };
              case "done":
                return { ...m, streaming: false, latency_ms: event.data.latency_ms };
              default:
                return m;
            }
          }),
        );
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "something went wrong";
      setMessages((prev) =>
        prev.map((m): Message => {
          if (m.id !== assistantId || m.role !== "assistant") return m;
          return { ...m, streaming: false, error: message };
        }),
      );
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  return (
    <main className="grid min-h-screen grid-rows-[auto_1fr_auto]">
      <header className="sticky top-0 z-30 border-b border-[color:var(--hairline)]/60 bg-[color:var(--bg)]/85 backdrop-blur-md">
        <div className="mx-auto flex max-w-[1180px] items-center justify-between px-6 py-4 sm:px-10">
          <Link href="/" className="font-display text-[22px] leading-none no-underline tracking-tight">
            Gaffer<span className="text-[color:var(--red)]">.</span>
          </Link>
          <Link
            href="/"
            className="font-mono text-[11px] uppercase tracking-[0.16em] text-[color:var(--muted)] no-underline hover:text-[color:var(--ink)]"
          >
            ← Back
          </Link>
        </div>
      </header>

      <div ref={scrollRef} className="overflow-y-auto px-6 sm:px-10">
        <div className="mx-auto grid max-w-[1180px] gap-16 py-12 lg:grid-cols-[1fr_300px]">
          <div>
            {messages.length === 0 ? (
              <EmptyState onPick={ask} />
            ) : (
              <div className="divide-y divide-[color:var(--hairline)]">
                <AnimatePresence initial={false}>
                  {messages.map((m) => (
                    <ChatMessage key={m.id} message={m} />
                  ))}
                </AnimatePresence>
              </div>
            )}
          </div>

          <SourcesPanel sources={lastAssistant?.sources ?? []} />
        </div>
      </div>

      <ChatComposer
        value={composerValue}
        onChange={setComposerValue}
        onSubmit={() => ask(composerValue)}
        disabled={busy}
      />
    </main>
  );
}

function EmptyState({ onPick }: { onPick: (q: string) => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6 }}
      className="flex min-h-[60vh] flex-col justify-center py-12"
    >
      <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-[color:var(--muted)]">
        New conversation
      </p>
      <h1 className="font-display mt-6 text-[clamp(36px,5vw,56px)] leading-[1.05] tracking-[-0.01em]">
        What do you want to know?
      </h1>
      <div className="mt-10 flex flex-wrap gap-2">
        {STARTER_QUERIES.map((q, i) => (
          <motion.button
            key={q}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.2 + i * 0.06 }}
            onClick={() => onPick(q)}
            className="lift border border-[color:var(--hairline)] bg-[color:var(--bg-elevated)] px-4 py-2 text-[13px] text-[color:var(--ink-soft)]"
          >
            {q}
          </motion.button>
        ))}
      </div>
    </motion.div>
  );
}