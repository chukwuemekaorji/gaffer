"use client";

import { motion } from "motion/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { Message } from "@/lib/types";
import { ThinkingState } from "./ThinkingState";

interface ChatMessageProps {
  message: Message;
}

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
          <AssistantMarkdown text={cleanText} streaming={message.streaming} />
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

function AssistantMarkdown({
  text,
  streaming,
}: {
  text: string;
  streaming: boolean;
}) {
  return (
    <div className="text-[16px] leading-[1.7] text-[color:var(--ink-soft)]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: (props) => <p className="mb-3 last:mb-0">{props.children}</p>,
          strong: (props) => (
            <strong className="font-semibold text-[color:var(--ink)]">
              {props.children}
            </strong>
          ),
          em: (props) => <em className="italic">{props.children}</em>,
          ul: (props) => (
            <ul className="mb-3 ml-5 list-disc space-y-1.5 marker:text-[color:var(--muted)]">
              {props.children}
            </ul>
          ),
          ol: (props) => (
            <ol className="mb-3 ml-5 list-decimal space-y-1.5 marker:text-[color:var(--muted)]">
              {props.children}
            </ol>
          ),
          a: (props) => (
            <a
              href={props.href}
              target="_blank"
              rel="noopener noreferrer"
              className="underline decoration-[color:var(--hairline)] decoration-1 underline-offset-[3px] transition-colors hover:decoration-[color:var(--ink)]"
            >
              {props.children}
            </a>
          ),
          h1: (props) => (
            <h1 className="mt-4 mb-2 font-display text-[22px] leading-[1.2]">
              {props.children}
            </h1>
          ),
          h2: (props) => (
            <h2 className="mt-4 mb-2 font-display text-[19px] leading-[1.25]">
              {props.children}
            </h2>
          ),
          h3: (props) => (
            <h3 className="mt-3 mb-1.5 font-semibold text-[16px] text-[color:var(--ink)]">
              {props.children}
            </h3>
          ),
          code: (props) => {
            const value = String(props.children);
            const isBlock = value.includes("\n");
            if (isBlock) {
              return (
                <pre className="mb-3 overflow-x-auto border border-[color:var(--hairline)] bg-[color:var(--bg-elevated)] p-3 text-[13px] leading-[1.5] font-mono">
                  <code>{props.children}</code>
                </pre>
              );
            }
            return (
              <code className="rounded bg-[color:var(--bg-elevated)] px-1.5 py-0.5 text-[14px] font-mono text-[color:var(--ink)]">
                {props.children}
              </code>
            );
          },
          blockquote: (props) => (
            <blockquote className="mb-3 border-l-2 border-[color:var(--hairline)] pl-4 italic text-[color:var(--muted)]">
              {props.children}
            </blockquote>
          ),
          hr: () => (
            <hr className="my-5 border-0 border-t border-[color:var(--hairline)]" />
          ),
          table: (props) => (
            <div className="mb-3 overflow-x-auto">
              <table className="w-full border-collapse text-[14px]">
                {props.children}
              </table>
            </div>
          ),
          th: (props) => (
            <th className="border-b border-[color:var(--ink)] px-2 py-1.5 text-left font-semibold">
              {props.children}
            </th>
          ),
          td: (props) => (
            <td className="border-b border-[color:var(--hairline)] px-2 py-1.5">
              {props.children}
            </td>
          ),
        }}
      >
        {text}
      </ReactMarkdown>

      {streaming && (
        <span
          aria-hidden
          className="ml-0.5 inline-block h-[0.9em] w-[2px] translate-y-[2px] animate-pulse bg-[color:var(--ink)]"
        />
      )}
    </div>
  );
}