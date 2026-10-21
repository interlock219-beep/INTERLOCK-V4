import { Link } from 'react-router-dom';
import { usePageMeta } from '../components/PageMeta';
import { Icon } from '../components/Icon';
import { Reveal } from '../components/Reveal';
import { Section, SectionHead } from '../components/Layout';
import { Callout, CodeBlock } from '../components/CodeBlock';
import {
  FEATURES,
  SAFETY_CANNOT,
  SITE,
  UNSUPPORTED_ENVIRONMENTS,
} from '../data/site';

const INTEGRATIONS = [
  {
    title: 'Python recovery adapters',
    body: 'Filesystem, git, config, database-record and mock adapters share one protocol: capture evidence, generate compensation, execute, verify.',
    code: `from app.infrastructure.recovery.filesystem_recovery_adapter import (
    FilesystemRecoveryAdapter,
)\nadapter = FilesystemRecoveryAdapter(base_path=work)
pre = await adapter.capture_recovery_evidence(action)`,
  },
  {
    title: 'Typed SDK guard',
    body: 'Wrap a tool so intent verification and execution-token consumption happen on every call, with a typed refusal instead of a silent failure.',
    code: `from sdk.intentlock import IntentLockGuard, SecurityError, guard_tool\nclient = IntentLockGuard(
    base_url="http://localhost:8000/api/v1/intent/verify",
    execute_url="http://localhost:8000/api/v1/intent/execute",
    auth_token="<access_token>",
)`,
  },
  {
    title: 'FastAPI control plane + REST',
    body: 'Run the gateway locally and call its REST endpoints. Health, readiness, auth, intent and recovery routes are served under /api/v1.',
    code: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000\ncurl http://localhost:8000/api/v1/health   # {"status":"ok"}`,
  },
  {
    title: 'LangChain adapter & examples',
    body: 'A LangChain wrapper plus runnable examples for multi-agent, human-in-the-loop and defence scenarios live under sdk/ and examples/.',
    code: `python examples/demo_agent_defense.py`,
  },
];

export function FeaturesPage() {
  usePageMeta({
    title: 'Features — Interlock V6',
    description:
      'Recovery, integrity verification, conflict detection, safe refusal, platform support and developer integrations — what each one does, and what it does not guarantee.',
  });

  return (
    <>
      <div className="page-hero">
        <div className="container">
          <Reveal>
            <span className="eyebrow">Key features</span>
            <h1>Every capability, with its limits attached.</h1>
            <p className="section-lead">
              Six building blocks for operating AI agents that change real files. For each one:
              what it does, why developers care, how it works, and what it does not guarantee.
            </p>
          </Reveal>
        </div>
      </div>

      <Section labelledBy="capabilities-title">
        <h2 id="capabilities-title" className="sr-only">
          Capability detail
        </h2>
        {FEATURES.map((feature) => (
          <Reveal key={feature.id}>
            <article className="feature-detail" id={feature.id}>
              <div>
                <div className="row" style={{ marginBottom: 'var(--space-3)' }}>
                  <span className={`badge ${feature.status === 'verified' ? 'badge-green' : 'badge-amber'}`}>
                    <span className="status-dot" /> {feature.statusLabel}
                  </span>
                </div>
                <h3 style={{ fontSize: '1.6rem' }}>{feature.title}</h3>
                <p className="section-lead" style={{ fontSize: 'var(--text-base)' }}>
                  {feature.summary}
                </p>
                <p style={{ color: 'var(--text-muted)' }}>{feature.what}</p>
              </div>
              <div className="fd-aside">
                <div className="fd-block">
                  <h4>Why developers care</h4>
                  <p>{feature.why}</p>
                </div>
                <div className="fd-block">
                  <h4>How it works</h4>
                  <p>{feature.how}</p>
                </div>
                <div className="fd-block limits">
                  <h4>What it does not guarantee</h4>
                  <p>{feature.notGuaranteed}</p>
                </div>
              </div>
            </article>
          </Reveal>
        ))}
      </Section>

      <Section alt labelledBy="interface-title" id="interface">
        <SectionHead
          id="interface-title"
          eyebrow="Product interface"
          title="What a recovery run looks like."
          lead="The workflow below mirrors the simulated console on the demo page: every transition is explicit, and the result is derived from verification, not optimism."
        />
        <div className="grid grid-2">
          <Reveal>
            <div className="terminal">
              <div className="terminal-bar">
                <span className="terminal-dot" />
                <span className="terminal-dot" />
                <span className="terminal-dot" />
                <span className="terminal-title">recovery run — simulated output</span>
              </div>
              <div className="terminal-body">
                <div className="term-line term-prompt">$ interlock-style recovery run (illustrative)</div>
                <div className="term-line term-warn">! incident detected — agent modified 4 files</div>
                <div className="term-line term-out">  analysis: 3 high risk, 1 medium</div>
                <div className="term-line term-out">  plan: 4 restore · 0 skip · 0 conflict</div>
                <div className="term-line term-out">  approval: waiting for explicit confirmation</div>
                <div className="term-line term-ok">✓ approval granted — staging + atomic swap</div>
                <div className="term-line term-ok">✓ verify: 4/4 digests match captured evidence</div>
                <div className="term-line term-ok">✓ recovery successful · 0 residue</div>
              </div>
            </div>
            <Callout type="info" title="Illustrative output">
              This is a stylised rendering of the workflow, not a captured terminal transcript. The
              real, reproducible commands live in the <Link to="/docs/installation">installation guide</Link>.
            </Callout>
          </Reveal>
          <Reveal delay={100}>
            <div className="card">
              <h3>Result states you will actually see</h3>
              <ul className="prose-list">
                <li>
                  <Icon name="check-circle" />
                  <span>
                    <strong>succeeded</strong> — restore applied and verified against captured
                    evidence.
                  </span>
                </li>
                <li>
                  <Icon name="alert" />
                  <span>
                    <strong>blocked_by_conflict</strong> — current content differs from the expected
                    state; the file was left untouched.
                  </span>
                </li>
                <li>
                  <Icon name="shield-x" />
                  <span>
                    <strong>refused</strong> — a precondition failed (path outside the boundary,
                    missing evidence, malformed backup).
                  </span>
                </li>
                <li>
                  <Icon name="x-circle" />
                  <span>
                    <strong>verification_failed</strong> — typed fail-closed result with the
                    evidence preserved for inspection.
                  </span>
                </li>
              </ul>
              <p className="faint small mb-0">
                Every one of these states exists in the codebase and is covered by tests; none of
                them is a decorative label.
              </p>
            </div>
          </Reveal>
        </div>
      </Section>

      <Section labelledBy="integrations-title" id="integrations">
        <SectionHead
          id="integrations-title"
          eyebrow="Developer integrations"
          title="The interfaces that exist today."
          lead="There is no hosted API, no package-index release and no sign-in system. These are the integration surfaces that are actually in the repository."
        />
        <div className="grid grid-2">
          {INTEGRATIONS.map((item, index) => (
            <Reveal key={item.title} delay={index * 60}>
              <div className="card" style={{ height: '100%' }}>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
                <CodeBlock code={item.code} language="bash" />
              </div>
            </Reveal>
          ))}
        </div>
        <Reveal>
          <p className="faint small">
            API reference: <code>uvicorn app.main:app</code> serves the OpenAPI schema at{' '}
            <code>/docs</code> when running locally. See{' '}
            <Link to="/docs/cli-api">CLI &amp; API reference</Link> for the verified surface.
          </p>
        </Reveal>
      </Section>

      <Section alt labelledBy="environments-title" id="environments">
        <SectionHead
          id="environments-title"
          eyebrow="Environments &amp; scope"
          title="Where this does not work."
        />

        <div className="grid grid-2">
          <Reveal>
            <div className="card">
              <h3>Explicitly unsupported</h3>
              <ul className="compare-list">
                {UNSUPPORTED_ENVIRONMENTS.map((item) => (
                  <li key={item}>
                    <Icon name="x" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>
          <Reveal delay={80}>
            <div className="card">
              <h3>Out of scope entirely</h3>
              <ul className="compare-list">
                {SAFETY_CANNOT.slice(2).map((item) => (
                  <li key={item}>
                    <Icon name="alert" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>
        </div>

        <Reveal>
          <Callout type="warn" title="Beta scope">
            During the controlled beta, point Interlock only at disposable projects you can afford
            to lose. Keep your own backups. Independent verification with{' '}
            <code>Get-FileHash</code> or <code>sha256sum</code> is part of the workflow, not an
            optional extra. <Link to="/safety">Read the safety page →</Link>
          </Callout>
        </Reveal>

        <Reveal>
          <div className="row">
            <Link to="/demo" className="btn btn-primary">
              Try the interactive demo <Icon name="arrow-right" />
            </Link>
            <Link to="/docs" className="btn btn-secondary">
              Documentation
            </Link>
            <a
              href={SITE.repoUrl}
              className="btn btn-ghost"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Icon name="github" width={16} height={16} /> Source
            </a>
          </div>
        </Reveal>
      </Section>
    </>
  );
}

export default FeaturesPage;
