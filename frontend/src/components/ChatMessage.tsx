"use client";

import { motion } from "motion/react";
import type { Message } from "@/lib/types";
import { ThinkingState } from "./ThinkingState";

interface ChatMessageProps {
  message: Message;
}

// strip [S1] [S2] tokens from the answer. they live in the prompt for
// grounding discipline, but the user-facing text reads as clean prose.
// the sources panel surfaces what was used separately.
function stripCitations(text: string): string {
  return text.replace(/\s?\[S\d+\]/g, "").replace(/\s+([.,;:!?])/g, "$1");
}

export function ChatMessage({ message }: ChatMessageProps) {
  if (message.role === "user") {
    return (
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="py-8"
      >
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
          You asked
        </p>
        <p className="mt-3 text-[19px] leading-[1.45] font-display italic">
          {message.text}
        </p>
      </motion.div>
    );
  }

  const cleanText = stripCitations(message.text);
  const showThinking = message.streaming && !message.text;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="py-8"
    >
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
        Gaffer
      </p>

      <div className="mt-3">
        {message.error ? (
          <p className="text-[15px] text-[color:var(--red)]">{message.error}</p>
        ) : showThinking ? (
          <ThinkingState
            routes={message.decision?.routes ?? null}
            hasSources={message.sources.length > 0}
          />
        ) : (
          <p className="text-[16px] leading-[1.7] whitespace-pre-wrap text-[color:var(--ink-soft)]">
            {cleanText}
            {message.streaming && (
              <span
                aria-hidden
                className="ml-0.5 inline-block h-[0.9em] w-[2px] translate-y-[2px] animate-pulse bg-[color:var(--ink)]"
              />
            )}
          </p>
        )}
      </div>

      {message.latency_ms !== undefined && (
        <p className="mt-5 font-mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
          {(message.latency_ms / 1000).toFixed(2)}s
        </p>
      )}
    </motion.div>
  );
}