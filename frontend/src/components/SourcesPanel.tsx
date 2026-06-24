"use client";

import { motion, AnimatePresence } from "motion/react";
import { ArrowUpRight } from "lucide-react";
import type { Source } from "@/lib/types";

const KIND_LABEL: Record<Source["kind"], string> = {
  chunk: "Article",
  stat: "Live data",
  web: "Web",
};

interface SourcesPanelProps {
  sources: Source[];
}

export function SourcesPanel({ sources }: SourcesPanelProps) {
  return (
    <aside className="lg:sticky lg:top-24">
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--muted)]">
        Sources {sources.length > 0 && `· ${sources.length}`}
      </p>

      <div className="mt-5 space-y-3">
        <AnimatePresence>
          {sources.length === 0 ? (
            <motion.p
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="text-[13px] leading-[1.5] text-[color:var(--muted)]"
            >
              The sources Gaffer uses will appear here as it searches.
            </motion.p>
          ) : (
            sources.map((source, index) => (
              <motion.div
                key={source.id}
                layout
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.3, delay: index * 0.04 }}
                className="lift border border-[color:var(--hairline)] bg-[color:var(--bg-elevated)] p-4"
              >
                <p className="font-mono text-[9px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
                  {KIND_LABEL[source.kind]}
                </p>
                <div className="mt-2 text-[13px] leading-[1.45]">
                  {source.url ? (
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="group inline-flex items-start gap-1 no-underline"
                    >
                      <span className="group-hover:underline">{source.title}</span>
                      <ArrowUpRight className="mt-0.5 h-3 w-3 flex-shrink-0 opacity-60" />
                    </a>
                  ) : (
                    <span>{source.title}</span>
                  )}
                </div>
                {source.published_at && (
                  <p className="mt-2 font-mono text-[9px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
                    {source.published_at.slice(0, 10)}
                  </p>
                )}
              </motion.div>
            ))
          )}
        </AnimatePresence>
      </div>
    </aside>
  );
}