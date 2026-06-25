"use client";

import Image from "next/image";
import Link from "next/link";
import { motion } from "motion/react";
import { ArrowRight, ArrowUpRight } from "lucide-react";

const springEase = "easeOut" as const;

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.7, ease: springEase } },
};

const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08, delayChildren: 0.1 } },
};

export default function Home() {
  return (
    <main className="min-h-screen overflow-x-hidden">
      <Nav />
      <Hero />
      <Principles />
      <FinalCTA />
      <Footer />
    </main>
  );
}

function Nav() {
  return (
    <nav className="sticky top-0 z-30 border-b border-[color:var(--hairline)]/60 bg-[color:var(--bg)]/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1180px] items-center justify-between px-6 py-4 sm:px-10">
        <Link href="/" className="font-display text-[24px] leading-none no-underline tracking-tight">
          Gaffer<span className="text-[color:var(--red)]">.</span>
        </Link>
        <Link
          href="/chat"
          className="group inline-flex items-center gap-2 text-[13px] font-medium no-underline"
        >
          <span>Open the chat</span>
          <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-1" />
        </Link>
      </div>
    </nav>
  );
}

function Hero() {
  return (
    <section className="px-6 pt-16 pb-24 sm:px-10 sm:pt-24 sm:pb-32">
      <motion.div
        variants={stagger}
        initial="hidden"
        animate="show"
        className="mx-auto grid max-w-[1180px] items-center gap-12 lg:grid-cols-[1.15fr_1fr] lg:gap-20"
      >
        <div>
          <motion.p variants={fadeUp} className="font-mono text-[11px] uppercase tracking-[0.22em] text-[color:var(--muted)]">
            Manchester United · AI Tactical Analyst
          </motion.p>

          <motion.h1
            variants={fadeUp}
            className="font-display mt-7 text-[clamp(44px,7vw,84px)] leading-[1.02] tracking-[-0.015em] text-[color:var(--ink)]"
          >
            Ask anything <br />
            about <em className="italic text-[color:var(--red)]">United</em>.
          </motion.h1>

          <motion.p variants={fadeUp} className="mt-7 max-w-[52ch] text-[17px] leading-[1.6] text-[color:var(--ink-soft)]">
            From Carrick's pressing structure to Cantona's volleys — Gaffer is a tactical analyst trained on real football writing, live stats and verified news. It never guesses.
          </motion.p>

          <motion.div variants={fadeUp} className="mt-10 flex flex-wrap items-center gap-4">
            <Link
              href="/chat"
              className="group inline-flex items-center gap-2 border border-[color:var(--red)] bg-[color:var(--red)] px-6 py-3.5 text-[14px] font-medium text-[color:var(--bg)] no-underline transition-all hover:-translate-y-0.5 hover:bg-[#d61d38] hover:shadow-[0_10px_24px_rgba(200,16,46,0.22)]"
            >
              Ask Gaffer a question
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
            </Link>
            <Link
              href="https://github.com/chukwuemekaorji/gaffer"
              target="_blank"
              className="group inline-flex items-center gap-1.5 text-[13px] text-[color:var(--muted)] no-underline hover:text-[color:var(--ink)]"
            >
              Source on GitHub
              <ArrowUpRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
            </Link>
          </motion.div>
        </div>

        <motion.div variants={fadeUp} className="relative">
          <div className="relative mx-auto aspect-[4/5] w-full max-w-[360px] overflow-hidden bg-transparent">
            <Image
              src="/logo1.png"
              alt="Manchester United logo"
              fill
              priority
              className="object-contain p-8"
              sizes="(max-width: 1024px) 80vw, 360px"
            />
          </div>
          <div className="absolute -bottom-6 -left-6 hidden border border-[color:var(--hairline)] bg-[color:var(--bg-elevated)] px-4 py-3 sm:block">
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--muted)]">Built in public</p>
            <p className="mt-1 font-display text-[18px] leading-none">2026</p>
          </div>
        </motion.div>
      </motion.div>
    </section>
  );
}

const PRINCIPLES = [
  {
    label: "How it knows",
    title: "It reads, it doesn't guess.",
    body: "Tactical articles, match reports and player profiles are continuously ingested, chunked and indexed. Live league standings, fixtures and player stats come straight from football-data.org. Gaffer answers from real material — not vibes from a training set.",
    imageHint: "Tactical board / pitch diagram",
    imageSrc: "/bruno.png",
    imageAlt: "Manchester United players",
  },
  {
    label: "How it answers",
    title: "Every claim has a receipt.",
    body: "Behind each answer, Gaffer keeps the sources it actually used. Open the panel and you'll see which match report, which stat row, which article informed what you just read. Nothing on screen is decorative — it all traces back.",
    imageHint: "Sources panel / archive shelf",
    imageSrc: "/mainoo1.png",
    imageAlt: "Manchester United player Mainoo",
  },
  {
    label: "When it doesn't know",
    title: "It would rather say nothing.",
    body: "If the sources don't cover it, Gaffer tells you. Other clubs, other sports, idle speculation — none of it gets answered with a hallucination. A specialist tool that's honest about its edges, not a chatbot trying to please.",
    imageHint: "Empty / quiet image",
    imageSrc: "/cunha1.png",
    imageAlt: "Manchester United player Cunha",
  },
];

function Principles() {
  return (
    <section className="border-t border-[color:var(--hairline)] px-6 py-24 sm:px-10 sm:py-32">
      <div className="mx-auto max-w-[1180px]">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6 }}
          className="mb-20 flex items-baseline justify-between border-b border-[color:var(--hairline)] pb-8"
        >
          <h2 className="font-display text-[clamp(28px,4vw,44px)] leading-[1.05]">
            Three principles.
          </h2>
          <p className="hidden font-mono text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)] sm:block">
            What makes it Gaffer
          </p>
        </motion.div>

        <div className="space-y-32">
          {PRINCIPLES.map((p, i) => (
            <Principle key={p.title} principle={p} reversed={i % 2 === 1} />
          ))}
        </div>
      </div>
    </section>
  );
}

function Principle({
  principle,
  reversed,
}: {
  principle: (typeof PRINCIPLES)[number];
  reversed: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 40 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-100px" }}
      transition={{ duration: 0.8, ease: springEase }}
      className={`grid items-center gap-10 lg:gap-20 ${reversed ? "lg:grid-cols-[1fr_1.15fr]" : "lg:grid-cols-[1.15fr_1fr]"}`}
    >
      <div className={reversed ? "lg:order-2" : ""}>
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-[color:var(--muted)]">
          {principle.label}
        </p>
        <h3 className="font-display mt-5 text-[clamp(28px,4vw,44px)] leading-[1.08] tracking-[-0.01em]">
          {principle.title}
        </h3>
        <p className="mt-6 max-w-[48ch] text-[16px] leading-[1.7] text-[color:var(--ink-soft)]">
          {principle.body}
        </p>
      </div>
      <div className={reversed ? "lg:order-1" : ""}>
        <div className="relative mx-auto aspect-[5/4] w-full max-w-[420px] overflow-hidden bg-transparent">
          <Image
            src={principle.imageSrc}
            alt={principle.imageAlt}
            fill
            className="object-contain p-6"
            sizes="(max-width: 1024px) 80vw, 420px"
          />
        </div>
      </div>
    </motion.div>
  );
}

function FinalCTA() {
  return (
    <section className="border-t border-[color:var(--hairline)] px-6 py-28 sm:px-10 sm:py-36">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.7 }}
        className="mx-auto max-w-[820px] text-center"
      >
        <h2 className="font-display text-[clamp(40px,6vw,72px)] leading-[1.05] tracking-[-0.01em]">
          Talk to it.
        </h2>
        <p className="mx-auto mt-6 max-w-[44ch] text-[16px] leading-[1.65] text-[color:var(--muted)]">
          The conversation is the demo. Ask whatever you'd ask a tactically obsessed friend.
        </p>
        <Link
          href="/chat"
          className="group mt-12 inline-flex items-center gap-2 border border-[color:var(--red)] bg-[color:var(--red)] px-8 py-4 text-[14px] font-medium text-[color:var(--bg)] no-underline transition-all hover:-translate-y-0.5 hover:bg-[#d61d38] hover:shadow-[0_10px_24px_rgba(200,16,46,0.22)]"
        >
          Open the chat
          <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
        </Link>
      </motion.div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-[color:var(--hairline)] px-6 py-10 sm:px-10">
      <div className="mx-auto flex max-w-[1180px] flex-wrap items-center justify-between gap-3 text-[12px] text-[color:var(--muted)]">
        <span>Built by Chukwuemeka Orji · Not affiliated with Manchester United FC</span>
        <Link
          href="https://github.com/chukwuemekaorji/gaffer"
          target="_blank"
          className="font-mono uppercase tracking-[0.14em] no-underline hover:text-[color:var(--ink)]"
        >
          GitHub
        </Link>
      </div>
    </footer>
  );
}