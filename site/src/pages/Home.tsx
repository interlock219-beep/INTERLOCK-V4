import { Link } from 'react-router-dom';
import { usePageMeta } from '../components/PageMeta';
import { Icon } from '../components/Icon';
import { HeroMock } from '../components/HeroMock';
import { Reveal } from '../components/Reveal';
import { Section, SectionHead } from '../components/Layout';
import { Accordion } from '../components/Accordion';
import { CodeBlock, Terminal } from '../components/CodeBlock';
import { FeatureCard, StatCard } from '../components/Cards';
import {
  EVIDENCE_NOTE,
  EVIDENCE_STATS,
  FAQS,
  FEATURES,
  INSTALL_STEPS,
  SAFETY_CAN,
  SAFETY_CANNOT,
  SITE,
  WORKFLOW_STEPS,
} from '../data/site';

const DOC_LINKS = [
  { to: '/docs/introduction', title: 'Introduction', body: 'What Interlock is, and what it is not.' },
  { to: '/docs/how-recovery-works', title: 'How recovery works', body: 'Evidence → plan → atomic restore → verify.' },
  { to: '/docs/safety-model', title: 'Safety model', body: 'Confinement, refusal conditions and fail-closed behaviour.' },
  { to: '/docs/troubleshooting', title: 'Troubleshooting', body: 'The failures you are most likely to hit, and safe next steps.' },
];

export function HomePage() {
  usePageMeta({
    title: 'Interlock V6 — AI agent recovery & verification',
    description:
      'Recover from harmful AI agent changes, verify data integrity, detect conflicts and refuse unsafe operations. Windows x64 tested; Linux and macOS in validation.',
  });

  return (
    <>
      {/* ---------------- hero ---------------- */}
      <section className="hero">
        <div className="container hero-grid">
          <div>
            <Reveal>
              <span className="eyebrow">AI Agent Recovery &amp; Verification</span>
              <h1>
                Your AI agents can change real systems.{' '}
                <span className="accent">Recover. Verify. Stay in control.</span>
              </h1>
              <p className="hero-lead">
                Explore how Interlock approaches recovery, integrity verification, conflict
                detection and controlled recovery workflows for supported environments — with the
                limitations stated up front.
              </p>
              <div className="hero-actions">
                <Link to="/download" className="btn btn-primary btn-lg">
                  <Icon name="download" /> Install Interlock
                </Link>
                <Link to="/demo" className="btn btn-secondary btn-lg">
                  <Icon name="play" /> Try Interactive Demo
                </Link>
              </div>
              <p className="hero-note">
                Install from the public repository — no binary or installer is published yet.
                Windows x64 is the tested primary platform; macOS and Linux are{' '}
                <Link to="/download">in validation</Link>.
              </p>
            </Reveal>
          </div>
          <Reveal delay={120}>
            <HeroMock />
          </Reveal>
        </div>
      </section>

      {/* ---------------- evidence ---------------- */}
      <Section labelledBy="evidence-title" id="evidence">
        <SectionHead
          id="evidence-title"
          eyebrow="Evidence, not marketing"
          title="Numbers we can point at."
          lead="Every figure below comes from a recorded test run in this repository. There are no customer counts, downloads, revenue figures or usage metrics here, because none exist."
        />
        <Reveal>
          <div className="stats-grid">
            {EVIDENCE_STATS.map((stat) => (
              <StatCard key={stat.label} {...stat} />
            ))}
          </div>
          <p className="evidence-note">{EVIDENCE_NOTE}</p>
        </Reveal>
      </Section>

      {/* ---------------- features ---------------- */}
      <Section alt labelledBy="features-title" id="features">
        <SectionHead
          id="features-title"
          eyebrow="Key features"
          title="Built for real-world AI agent workflows."
          lead="Everything you need to recover, verify and control what your AI agents do — before and after they act. Each capability states what it does not guarantee."
        />
        <div className="grid grid-3">
          {FEATURES.map((feature, index) => (
            <Reveal key={feature.id} delay={index * 60}>
              <FeatureCard feature={feature} />
            </Reveal>
          ))}
        </div>
      </Section>

      {/* ---------------- demo preview ---------------- */}
      <Section labelledBy="demo-preview-title" id="demo-preview">
        <div className="grid grid-2" style={{ alignItems: 'center' }}>
          <Reveal>
            <span className="eyebrow">Interactive demo</span>
            <h2 id="demo-preview-title">Run a recovery in your browser.</h2>
            <p className="section-lead">
              A deterministic, browser-only simulation: detect an incident, inspect the diff,
              analyse risk, build a plan, approve it, run recovery and verify the result — plus
              conflict, refusal and interruption cases that must not end in success.
            </p>
            <ul className="prose-list">
              {[
                'Four scenarios: success, conflict, unsafe refusal, interrupted workflow.',
                'Explicit state machine — recovery cannot start before analysis and approval.',
                'Verification is computed from the fictional files, never hardcoded.',
                'No real files, no shell commands, no account, no network calls.',
              ].map((line) => (
                <li key={line}>
                  <Icon name="check" />
                  {line}
                </li>
              ))}
            </ul>
            <Link to="/demo" className="btn btn-primary">
              Open the simulated console <Icon name="arrow-right" />
            </Link>
          </Reveal>
          <Reveal delay={100}>
            <div className="terminal">
              <div className="terminal-bar">
                <span className="terminal-dot" />
                <span className="terminal-dot" />
                <span className="terminal-dot" />
                <span className="terminal-title">demo — scenario A</span>
              </div>
              <div className="terminal-body">
                <div className="term-line term-out">state: incident_detected → analyzed</div>
                <div className="term-line term-out">risk: 3 files high, 1 medium</div>
                <div className="term-line term-out">plan: 4 restore, 0 skip, 0 conflict</div>
                <div className="term-line term-warn">approval: explicit human approval required</div>
                <div className="term-line term-out">recovering … 100%</div>
                <div className="term-line term-ok">verify: 4/4 files match captured digests</div>
                <div className="term-line term-ok">verified · no staging residue</div>
                <div className="term-line term-prompt">$ _</div>
              </div>
            </div>
            <p className="small faint">
              Illustrative transcript of one scenario — a demonstration, not a guarantee. Recovery
              restores only what was captured before the change; a file that was never captured
              cannot be recovered.
            </p>
          </Reveal>
        </div>
      </Section>

      {/* ---------------- workflow ---------------- */}
      <Section alt labelledBy="workflow-title" id="workflow">
        <SectionHead
          id="workflow-title"
          eyebrow="Recovery workflow"
          title="Detect. Analyse. Plan. Approve. Recover. Verify."
          lead="The same sequence the simulation walks you through — and the order the real engine enforces."
        />
        <div className="grid grid-3">
          {WORKFLOW_STEPS.map((step, index) => (
            <Reveal key={step.n} delay={index * 50}>
              <div className="step" style={{ height: '100%' }}>
                <span className="step-num">{step.n}</span>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.body}</p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </Section>

      {/* ---------------- install ---------------- */}
      <Section labelledBy="install-title" id="install">
        <div className="grid grid-2" style={{ alignItems: 'start' }}>
          <Reveal>
            <span className="eyebrow">Get started</span>
            <h2 id="install-title">Install from source in minutes.</h2>
            <p className="section-lead">
              Interlock is not published to any package index. The supported path is a checkout, a
              virtual environment, and a disposable project directory to work against.
            </p>
            <div className="steps">
              {INSTALL_STEPS.slice(0, 4).map((step) => (
                <div className="step" key={step.n}>
                  <span className="step-num">{step.n}</span>
                  <div>
                    <h3>{step.title}</h3>
                    <p>{step.body}</p>
                  </div>
                </div>
              ))}
            </div>
            <div className="row">
              <Link to="/download" className="btn btn-primary">
                <Icon name="download" /> Full install guide
              </Link>
              <Link to="/docs/installation" className="btn btn-secondary">
                Read the docs
              </Link>
            </div>
          </Reveal>
          <Reveal delay={100}>
            <Terminal
              title="interlock — first run"
              lines={[
                { kind: 'prompt', text: 'git clone https://github.com/interlock219-beep/INTERLOCK-V4.git' },
                { kind: 'out', text: "Cloning into 'INTERLOCK-V4'…" },
                { kind: 'prompt', text: 'python -m venv .venv && .venv\\Scripts\\activate' },
                { kind: 'prompt', text: 'pip install -e ".[dev,security]"' },
                { kind: 'out', text: 'Successfully installed intentlock-4.0.0' },
                { kind: 'prompt', text: 'python scripts/pilot_demo_v1.py' },
                { kind: 'ok', text: '{ "recovery": true, "safety": true,' },
                { kind: 'ok', text: '  "human_change": true, "idempotency": true,' },
                { kind: 'ok', text: '  "overall_pass": true, "exit_code": 0 }' },
              ]}
            />
            <p className="faint small" style={{ marginTop: 'var(--space-3)' }}>
              Observed output from the controlled-beta first-run guide. Your environment prints the
              same structure; digests depend on your content.
            </p>
          </Reveal>
        </div>
      </Section>

      {/* ---------------- safety ---------------- */}
      <Section labelledBy="safety-title" id="safety">
        <SectionHead
          id="safety-title"
          eyebrow="Safety &amp; limitations"
          title="Built for safety. Designed for transparency."
          lead="Interlock helps you recover and verify your data, but it is not a magic solution. Here is what it can and cannot do."
        />
        <Reveal>
          <div className="compare">
            <div className="compare-col can">
              <h3>
                <Icon name="check-circle" width={20} height={20} /> What Interlock can do
              </h3>
              <ul className="compare-list">
                {SAFETY_CAN.map((item) => (
                  <li key={item}>
                    <Icon name="check" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="compare-col cannot">
              <h3>
                <Icon name="alert" width={20} height={20} /> What Interlock cannot guarantee
              </h3>
              <ul className="compare-list">
                {SAFETY_CANNOT.map((item) => (
                  <li key={item}>
                    <Icon name="x" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Reveal>
        <Reveal>
          <div className="row" style={{ marginTop: 'var(--space-5)' }}>
            <Link to="/safety" className="btn btn-secondary">
              Full safety &amp; security page <Icon name="arrow-right" />
            </Link>
            <Link to="/docs/limitations" className="btn btn-ghost">
              Known limitations
            </Link>
          </div>
        </Reveal>
      </Section>

      {/* ---------------- docs ---------------- */}
      <Section alt labelledBy="docs-title" id="docs-links">
        <SectionHead
          id="docs-title"
          eyebrow="Documentation"
          title="Written against the code, not around it."
          lead="Installation, the recovery model, verification, conflict handling, safety, troubleshooting and platform status — each page checked against the implementation."
        />
        <div className="grid grid-4">
          {DOC_LINKS.map((doc, index) => (
            <Reveal key={doc.to} delay={index * 50}>
              <Link to={doc.to} className="card card-link" style={{ display: 'block', height: '100%' }}>
                <h3>{doc.title}</h3>
                <p>{doc.body}</p>
                <span className="learn">
                  Read <Icon name="arrow-right" width={14} height={14} />
                </span>
              </Link>
            </Reveal>
          ))}
        </div>
        <Reveal>
          <CodeBlock
            filename="verify after install"
            code={'python -m pip check\npython -c "import app.main, sdk.intentlock; print(\'imports ok\')"'}
          />
        </Reveal>
      </Section>

      {/* ---------------- faq + beta ---------------- */}
      <Section labelledBy="faq-title">
        <div className="grid grid-2" style={{ alignItems: 'start' }}>
          <Reveal>
            <span className="eyebrow">FAQ</span>
            <h2 id="faq-title">Common questions.</h2>
            <p className="section-lead">Straight answers, including the uncomfortable ones.</p>
          </Reveal>
          <Reveal delay={80}>
            <Accordion
              items={FAQS.map((item) => ({ id: item.q, question: item.q, answer: <p>{item.a}</p> }))}
            />
          </Reveal>
        </div>
      </Section>

      <Section className="section-tight">
        <Reveal>
          <div className="cta-band">
            <div>
              <span className="eyebrow">Controlled beta</span>
              <h2>Join the Interlock V6 beta.</h2>
              <p>
                Help test recovery on disposable projects. No account, no telemetry, no data
                collection — just a checkout, one hour, and an honest report of what happened.
              </p>
            </div>
            <div className="row">
              <Link to="/beta" className="btn btn-primary btn-lg">
                Apply for beta <Icon name="arrow-right" />
              </Link>
              <a
                href={SITE.repoUrl}
                className="btn btn-secondary btn-lg"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Icon name="github" width={16} height={16} /> View source
              </a>
            </div>
          </div>
        </Reveal>
      </Section>
    </>
  );
}

export default HomePage;
