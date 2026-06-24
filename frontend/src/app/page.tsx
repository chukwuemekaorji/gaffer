import Link from "next/link";

// the landing page is intentionally one file. no component splitting
// until we know the layout has settled. easier to iterate on copy and
// spacing when everything is right here.
export default function Home() {
  return (
    <main className="min-h-screen px-6 sm:px-8">
      <Nav />

      <article className="mx-auto max-w-[680px] pt-20 sm:pt-28">
        <Hero />
        <DemoBlock />
        <WhatItReads />
        <HowItHandlesUncertainty />
      </article>

      <Footer />
    </main>
  );
}

function Nav() {
  return (
    <nav className="mx-auto flex max-w-[680px] items-center justify-between pt-6">
      <Link
        href="/"
        className="font-display text-[22px] leading-none no-underline tracking-tight"
      >
        Gaffer.
      </Link>
      <Link
        href="/chat"
        className="font-mono text-[12px] uppercase tracking-[0.12em] text-[color:var(--muted)] no-underline hover:text-[color:var(--ink)]"
      >
        Open the chat →
      </Link>
    </nav>
  );
}

function Hero() {
  return (
    <header className="border-b border-[color:var(--hairline)] pb-14">
      <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
        A grounded tactical analyst · Manchester United
      </p>
      <h1 className="font-display mt-6 text-[44px] leading-[1.05] tracking-[-0.01em] sm:text-[56px]">
        Ask anything about United.
        <br />
        <em className="italic text-[color:var(--muted)]">
          Get cited answers.
        </em>
      </h1>
      <p className="mt-7 max-w-[52ch] text-[17px] leading-[1.6] text-[color:var(--ink)]">
        Gaffer is an AI analyst that won't make things up about Manchester
        United. Every claim it makes points back to a source — a tactical
        article, a match report, a live stat, or a verified news story. When it
        can't ground an answer, it says so.
      </p>

      <div className="mt-10 flex items-center gap-6">
        <Link
          href="/chat"
          className="bg-[color:var(--ink)] px-5 py-3 text-[14px] text-[color:var(--bg)] no-underline transition-colors hover:bg-[color:var(--red)]"
        >
          Ask Gaffer a question
        </Link>
        <Link
          href="https://github.com/chukwuemekaorji/gaffer"
          className="font-mono text-[12px] uppercase tracking-[0.12em] text-[color:var(--muted)] hover:text-[color:var(--ink)]"
          target="_blank"
        >
          Source on GitHub
        </Link>
      </div>
    </header>
  );
}

// the demo block is the signature. it's a static mock of a real
// gaffer interaction so visitors immediately see what the product is
// and what the citation pills look like in context. no animation, no
// fake typing — just typeset html that reads like the product.
function DemoBlock() {
  return (
    <section className="border-b border-[color:var(--hairline)] py-14">
      <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
        Example
      </p>

      <div className="mt-6 space-y-7">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
            You
          </p>
          <p className="mt-2 text-[17px] leading-[1.55]">
            How does Carrick's setup differ from Amorim's 3-4-3?
          </p>
        </div>

        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
            Gaffer
          </p>
          <p className="mt-2 text-[17px] leading-[1.65]">
            Carrick has moved United back to a 4-2-3-1 with a double pivot of
            Casemiro and Mainoo, prioritising defensive compactness over
            Amorim's aggressive 3-4-3 high press.{" "}
            <Cite>S1</Cite> Where Amorim pushed his wing-backs high to trigger
            pressing traps, Carrick keeps Shaw and Dalot narrower to support the
            centre-backs against deep blocks. <Cite>S2</Cite> Five games into
            his permanent appointment, the side has 13 points from 15
            available. <Cite>S3</Cite>
          </p>
        </div>

        <div className="border-t border-[color:var(--hairline)] pt-6">
          <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-[color:var(--muted)]">
            Sources
          </p>
          <ul className="mt-3 space-y-2 text-[14px] text-[color:var(--muted)]">
            <li>
              <Cite>S1</Cite>{" "}
              <span className="text-[color:var(--ink)]">
                Michael Carrick's Man United Tactics
              </span>{" "}
              · backtocarrington.com
            </li>
            <li>
              <Cite>S2</Cite>{" "}
              <span className="text-[color:var(--ink)]">
                Manchester United 3 Liverpool 2: tactical analysis
              </span>{" "}
              · Coaches' Voice
            </li>
            <li>
              <Cite>S3</Cite>{" "}
              <span className="text-[color:var(--ink)]">
                Premier League table position
              </span>{" "}
              · football-data.org
            </li>
          </ul>
        </div>
      </div>
    </section>
  );
}

function WhatItReads() {
  // four data sources, written as short paragraphs not bullets. the
  // skill warned that bullet/icon grids are a tell of templated design;
  // setting these as prose reinforces the editorial direction.
  return (
    <section className="border-b border-[color:var(--hairline)] py-14">
      <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
        What it reads
      </p>

      <div className="mt-6 space-y-6 text-[16px] leading-[1.65]">
        <p>
          <strong className="font-medium">Tactical writing.</strong> A curated
          knowledge base spanning United's last three managerial eras — Ten Hag,
          Amorim, Carrick — drawn from outlets like The Coaches' Voice and
          Back to Carrington.
        </p>

        <p>
          <strong className="font-medium">Live structured stats.</strong>{" "}
          League position, fixtures, results, and player stats from
          football-data.org, refreshed in the background. Factual lookups
          never touch the language model's memory.
        </p>

        <p>
          <strong className="font-medium">Continuous news ingestion.</strong>{" "}
          RSS feeds from BBC Sport, The Guardian, the official Manchester
          United site, and the Manchester Evening News, pulled and indexed
          every fifteen minutes.
        </p>

        <p>
          <strong className="font-medium">Web search.</strong> A fallback for
          breaking news that hasn't been indexed yet. Used sparingly and only
          when the routing layer judges that the question is recent enough to
          need it.
        </p>
      </div>
    </section>
  );
}

function HowItHandlesUncertainty() {
  return (
    <section className="py-14">
      <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-[color:var(--muted)]">
        When it doesn't know
      </p>

      <p className="mt-6 text-[16px] leading-[1.65]">
        If none of the four sources above can ground an answer, Gaffer says so
        and asks for clarification — it doesn't fall back on guesses from
        training data. Out-of-scope questions (other clubs, other sports,
        general life advice) get a polite decline rather than a hallucinated
        answer.
      </p>

      <p className="mt-5 text-[16px] leading-[1.65] text-[color:var(--muted)]">
        That refusal posture is the entire point: a specialist tool that's
        honest about the edges of what it knows, rather than a chatbot that's
        confidently wrong.
      </p>
    </section>
  );
}

function Footer() {
  return (
    <footer className="mx-auto mt-24 max-w-[680px] border-t border-[color:var(--hairline)] py-8 text-[12px] text-[color:var(--muted)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span>Built by Chukwuemeka Orji. Not affiliated with Manchester United FC.</span>
        <Link
          href="https://github.com/chukwuemekaorji/gaffer"
          className="font-mono uppercase tracking-[0.12em] hover:text-[color:var(--ink)]"
          target="_blank"
        >
          GitHub
        </Link>
      </div>
    </footer>
  );
}

// citation pill — uses the .cite class defined in globals.css so the
// styling stays in one place and gets reused by the chat ui later.
function Cite({ children }: { children: React.ReactNode }) {
  return <span className="cite">[{children}]</span>;
}