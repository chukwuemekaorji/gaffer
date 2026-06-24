"use client";

import { useEffect, useRef } from "react";
import { ArrowUp } from "lucide-react";

interface ChatComposerProps {
  value: string;
  onChange: (next: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatComposer({
  value,
  onChange,
  onSubmit,
  disabled,
  placeholder,
}: ChatComposerProps) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [value]);

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!disabled && value.trim()) onSubmit();
    }
  };

  return (
    <div className="sticky bottom-0 border-t border-[color:var(--hairline)] bg-[color:var(--bg)]/95 backdrop-blur-md">
      <div className="mx-auto max-w-[920px] px-6 py-5">
        <div className="flex items-end gap-3 border border-[color:var(--hairline)] bg-[color:var(--bg-elevated)] px-4 py-3 transition-colors focus-within:border-[color:var(--ink)]">
          <textarea
            ref={ref}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKey}
            rows={1}
            placeholder={placeholder ?? "Ask anything about United…"}
            disabled={disabled}
            className="flex-1 resize-none bg-transparent text-[16px] leading-[1.5] outline-none placeholder:text-[color:var(--muted)] disabled:opacity-50"
          />
          <button
            type="button"
            onClick={onSubmit}
            disabled={disabled || !value.trim()}
            className="group flex h-9 w-9 flex-shrink-0 items-center justify-center bg-[color:var(--ink)] text-[color:var(--bg)] transition-all hover:bg-[color:var(--red)] disabled:cursor-not-allowed disabled:opacity-30"
            aria-label="Send"
          >
            <ArrowUp className="h-4 w-4 transition-transform group-hover:-translate-y-0.5" />
          </button>
        </div>
        <p className="mt-3 px-1 text-center font-mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
          Enter to send · Shift + Enter for newline
        </p>
      </div>
    </div>
  );
}