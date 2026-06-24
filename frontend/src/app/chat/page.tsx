import Link from "next/link";

// placeholder. the real chat ui lands in section 8. having this stub
// means the landing's CTA already works without a 404, and we can
// commit the landing as a standalone deliverable.
export default function ChatPage() {
  return (
    <main className="min-h-screen px-6">
      <div className="mx-auto max-w-[680px] pt-32">
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
          Coming next
        </p>
        <h1 className="font-display mt-4 text-[40px] leading-[1.1]">
          The chat interface lands in the next section.
        </h1>
        <p className="mt-6 text-[16px] leading-[1.65] text-[color:var(--muted)]">
          The backend is already running — you can hit{" "}
          <code className="font-mono text-[14px]">
            POST http://localhost:8000/chat
          </code>{" "}
          if you want to try it from the docs UI in the meantime.
        </p>
        <Link
          href="/"
          className="mt-10 inline-block font-mono text-[12px] uppercase tracking-[0.12em] text-[color:var(--muted)] no-underline hover:text-[color:var(--ink)]"
        >
          ← Back to the landing
        </Link>
      </div>
    </main>
  );
}