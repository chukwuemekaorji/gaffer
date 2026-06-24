"use client";

import { motion, AnimatePresence } from "motion/react";
import type { Route } from "@/lib/types";

const STATUS_BY_ROUTE: Record<Route, string> = {
  tactical_rag: "Searching the tactical archive",
  recent_rag: "Pulling recent match reports",
  stats: "Cross-checking live stats",
  web_search: "Checking the latest news",
  refuse: "",
};

interface ThinkingStateProps {
  routes: Route[] | null;
  hasSources: boolean;
}

export function ThinkingState({ routes, hasSources }: ThinkingStateProps) {
  let status = "Routing your question";
  if (routes && routes.length > 0) {
    const labels = routes.map((r) => STATUS_BY_ROUTE[r]).filter(Boolean);
    if (labels.length > 0) {
      status = labels.join(" · ");
    }
  }
  if (hasSources) status = "Composing the answer";

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={status}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -4 }}
        transition={{ duration: 0.25 }}
        className="flex items-center gap-3 text-[14px] text-[color:var(--muted)]"
      >
        <ThinkingDots />
        <span className="italic">{status}…</span>
      </motion.div>
    </AnimatePresence>
  );
}

function ThinkingDots() {
  return (
    <span className="flex items-center gap-1">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="block h-1 w-1 rounded-full bg-[color:var(--ink)]"
          animate={{ opacity: [0.2, 1, 0.2] }}
          transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }}
        />
      ))}
    </span>
  );
}