import { useState } from 'react';
import { Link } from 'react-router-dom';
import { usePageMeta } from '../components/PageMeta';
import { Icon } from '../components/Icon';
import { Reveal } from '../components/Reveal';
import { Section, SectionHead } from '../components/Layout';
import { Callout, CodeBlock } from '../components/CodeBlock';
import { SITE } from '../data/site';

const REPORT_TEMPLATE = `Slot: T1/T2/T3
OS / python --version: _
Checkout commit: _
Step that failed: _
Exact command: _
Exact error text: _
Reproducible (yes/no, N attempts): _
Files created outside your disposable dir (yes/no): _
Network attempts observed (yes/no): _
Install / demo duration: _
Clarity notes (what confused you): _`;

const FOR_WHO = [
  'Developers running coding agents against real project files on Windows x64.',
  'People who want to see a refusal happen before they trust the tool with anything else.',
  'POSIX volunteers: macOS and Linux slots exist precisely because those platforms are unvalidated.',
  'Anyone willing to spend about an hour and report exactly what happened — including the failures.',
];

const NOT_FOR = [
  'Production systems, valuable databases, or anything you cannot afford to lose.',
  'Teams looking for a hosted service, dashboard or account — none exists.',
  'Performance benchmarking, SSO/KMS evaluation, or web-dashboard review (out of scope).',
  'Anyone expecting guaranteed recovery — no one should promise you that.',
];

const STOP_CONDITIONS = [
  'A file appears, changes or disappears outside your disposable directory.',
  'Any network attempt occurs during the tested workflow.',
  'A secret or file content appears in error output.',
  'The same crash happens twice.',
  'Something damages data you did not deliberately sacrifice.',
];

export function BetaPage() {
  const [formState, setFormState] = useState<'idle' | 'copied' | 'failed'>('idle');
  const [name, setName] = useState('');
  const [platform, setPlatform] = useState('');
  const [message, setMessage] = useState('');
  const [attempted, setAttempted] = useState(false);

  usePageMeta({
    title: 'Beta programme — Interlock V6',
    description:
      'Join the Interlock V6 controlled beta: disposable projects on Windows x64, one hour, no telemetry, structured reporting. POSIX slots open for macOS and Linux.',
  });

  const emailBody = encodeURIComponent(
    `Hi — I would like to join the Interlock V6 controlled beta.\n\n` +
      `Name / handle: ${name || '(not provided)'}\n` +
      `Platform I can test on: ${platform || '(not specified)'}\n\n` +
      `${message || 'I have read the beta page and the stop conditions.'}\n\n` +
      `I understand: disposable projects only, no production data, no credentials, and I may stop at any time.`,
  );

  const emailHref = `mailto:?subject=${encodeURIComponent('Interlock V6 beta application')}&body=${emailBody}`;

  const copyTemplate = () => {
    void (async () => {
      try {
        await navigator.clipboard.writeText(REPORT_TEMPLATE);
        setFormState('copied');
      } catch {
        setFormState('failed');
      }
      window.setTimeout(() => setFormState('idle'), 2200);
    })();
  };

  return (
    <>
      <div className="page-hero">
        <div className="container">
          <Reveal>
            <span className="eyebrow">Controlled beta</span>
            <h1>Help test recovery where it is honest to test it.</h1>
            <p className="section-lead">
              One hour, a disposable directory, and a structured report. Nothing is collected
              automatically, no credentials are requested, and partial results still help. This page
              does not submit anything anywhere — you stay in control of what you send, and to whom.
            </p>
          </Reveal>
        </div>
      </div>

      <Section labelledBy="what-title">
        <div className="grid grid-2" style={{ alignItems: 'start' }}>
          <Reveal>
            <span className="eyebrow">What Interlock is</span>
            <h2 id="what-title">A recovery engine you can watch refuse.</h2>
            <p className="section-lead">
              Interlock records what an agent did to your files, can restore the previous bytes
              exactly, refuses to overwrite human edits made afterwards, and verifies the result
              with digests it recomputes from disk.
            </p>
            <ul className="prose-list">
              {[
                'Installs from a checkout — no package index, no installer, no account.',
                'Runs offline in the tested workflow: no network calls, no telemetry.',
                'Writes only inside the disposable directory you point it at.',
                'Available today on Windows x64 only; macOS/Linux slots exist to generate that evidence.',
              ].map((item) => (
                <li key={item}>
                  <Icon name="check" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </Reveal>
          <Reveal delay={80}>
            <span className="eyebrow">Prerequisites</span>
            <h2>What you need.</h2>
            <ul className="prose-list">
              {[
                'Python 3.11–3.14 (3.11.9 verified), git, pip, ~2 GB disk.',
                'A fresh clone in a directory you create.',
                'A disposable project directory — never your real work.',
                'About one hour and the willingness to report exactly what happened.',
                'Not required: Docker, PostgreSQL, Redis, admin/root, network at run time.',
              ].map((item) => (
                <li key={item}>
                  <Icon name="terminal" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
            <CodeBlock
              filename="the only install path"
              code={`git clone ${SITE.repoUrl}.git\ncd INTERLOCK-V4\npython -m venv .venv\n.venv\\Scripts\\activate\npip install -e ".[dev,security]"`}
            />
          </Reveal>
        </div>
      </Section>

      <Section alt labelledBy="who-title">
        <div className="grid grid-2">
          <Reveal>
            <div className="compare-col can">
              <h3>
                <Icon name="check-circle" width={20} height={20} /> Who this is for
              </h3>
              <ul className="compare-list">
                {FOR_WHO.map((item) => (
                  <li key={item}>
                    <Icon name="check" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>
          <Reveal delay={80}>
            <div className="compare-col cannot">
              <h3>
                <Icon name="alert" width={20} height={20} /> Who should wait
              </h3>
              <ul className="compare-list">
                {NOT_FOR.map((item) => (
                  <li key={item}>
                    <Icon name="x" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>
        </div>
        <Reveal>
          <Callout type="warn" title="Known limitations you may hit">
            <p>
              Symlink drills skip in unprivileged Windows shells. Real disk-full behaviour is
              mocked-only on our side. Migration paths carry documented defects and are out of
              scope. POSIX backup permissions are an open item. Read{' '}
              <Link to="/docs/limitations">Limitations</Link> before you start.
            </p>
          </Callout>
        </Reveal>
      </Section>

      <Section labelledBy="process-title">
        <SectionHead
          id="process-title"
          eyebrow="How it works"
          title="Five steps, no data collection."
          lead="Everything below happens on your machine, and every artifact you share is chosen by you."
        />
        <div className="grid grid-3">
          {[
            { n: 1, title: 'Install verbatim', body: 'Follow BETA_FIRST_RUN.md exactly. If an install step fails, stop and report — do not improvise.' },
            { n: 2, title: 'Run the safe demo', body: 'python scripts/pilot_demo_v1.py — four verdicts must be true before you go further.' },
            { n: 3, title: 'Trigger one fault', body: 'On a disposable file you created: capture evidence, let the fictional agent fault, recover, verify with your own hash tool.' },
            { n: 4, title: 'Check your boundaries', body: 'Confirm nothing changed outside the disposable directory and no network attempt occurred.' },
            { n: 5, title: 'Report with the template', body: 'Send only the structured fields below through a channel you choose.' },
          ].map((step, index) => (
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

      <Section alt labelledBy="privacy-title">
        <div className="grid grid-2" style={{ alignItems: 'start' }}>
          <Reveal>
            <span className="eyebrow">Privacy</span>
            <h2 id="privacy-title">What is collected: nothing.</h2>
            <ul className="prose-list">
              {[
                'No telemetry exists in Interlock; nothing is collected automatically.',
                'This website sets no cookies, runs no analytics, and has no backend to send anything to.',
                'You are never asked for credentials, source code, database dumps or full logs.',
                'Any report you send is chosen and composed by you, then sent by you.',
                'You may stop at any time; partial results are still useful.',
              ].map((item) => (
                <li key={item}>
                  <Icon name="lock" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
            <Callout type="danger" title="Stop conditions — they apply to you too">
              <ul className="compare-list" style={{ marginTop: 'var(--space-2)' }}>
                {STOP_CONDITIONS.map((item) => (
                  <li key={item}>
                    <Icon name="alert" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </Callout>
          </Reveal>

          <Reveal delay={80}>
            <span className="eyebrow">Feedback process</span>
            <h2>How to apply — honestly.</h2>
            <p className="muted small">
              There is no application backend on this site. The form below prepares a message{' '}
              <strong>in your own email client or clipboard</strong> — it is never transmitted
              automatically, and this site has no server to transmit it to.
            </p>

            <form
              className="panel panel-pad stack"
              onSubmit={(event) => {
                event.preventDefault();
                setAttempted(true);
                if (!name.trim() || !platform.trim()) return;
                window.location.href = emailHref;
              }}
              noValidate
            >
              <div>
                <label htmlFor="beta-name" className="small mono">
                  Name or handle
                </label>
                <input
                  id="beta-name"
                  className="docs-search"
                  style={{ marginTop: 6 }}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="how you want to be addressed"
                  required
                />
              </div>
              <div>
                <label htmlFor="beta-platform" className="small mono">
                  Platform you can test on
                </label>
                <select
                  id="beta-platform"
                  className="docs-search"
                  style={{ marginTop: 6 }}
                  value={platform}
                  onChange={(event) => setPlatform(event.target.value)}
                  required
                >
                  <option value="">Choose one…</option>
                  <option value="Windows x64 (slot T1)">Windows x64 (slot T1)</option>
                  <option value="macOS (POSIX slot T2)">macOS (POSIX slot T2)</option>
                  <option value="Linux (POSIX slot T2/T3)">Linux (POSIX slot T2/T3)</option>
                </select>
              </div>
              <div>
                <label htmlFor="beta-message" className="small mono">
                  Anything you want to add (optional)
                </label>
                <textarea
                  id="beta-message"
                  className="docs-search"
                  style={{ marginTop: 6, minHeight: 90, resize: 'vertical' }}
                  value={message}
                  onChange={(event) => setMessage(event.target.value)}
                  placeholder="what you hope to test, your experience with coding agents…"
                />
              </div>

              {attempted && (!name.trim() || !platform.trim()) ? (
                <p className="callout callout-danger" role="alert" style={{ margin: 0 }}>
                  <span>
                    <strong className="callout-title">Missing information</strong>
                    Add your name or handle and pick a platform before preparing the message.
                  </span>
                </p>
              ) : null}

              <div className="row">
                <button type="submit" className="btn btn-primary">
                  <Icon name="arrow-right" /> Prepare application email
                </button>
                <button type="button" className="btn btn-secondary" onClick={copyTemplate}>
                  <Icon name="copy" />{' '}
                  {formState === 'copied'
                    ? 'Report template copied'
                    : formState === 'failed'
                      ? 'Copy failed'
                      : 'Copy report template'}
                </button>
              </div>

              <p className="faint small mb-0">
                Nothing here is stored or transmitted by this website. Your email client opens a
                draft addressed by you — no default recipient is configured, so choose the channel
                you received the invitation from (or open an issue on the repository).
              </p>
            </form>
          </Reveal>
        </div>
      </Section>

      <Section labelledBy="expect-title">
        <div className="cta-band">
          <div>
            <h2 id="expect-title">Prefer to look first?</h2>
            <p>
              The browser demo covers the same workflow with zero risk and zero setup, and the
              documentation walks through every command before you run it.
            </p>
          </div>
          <div className="row">
            <Link to="/demo" className="btn btn-primary btn-lg">
              <Icon name="play" /> Try the demo
            </Link>
            <Link to="/docs/quickstart" className="btn btn-secondary btn-lg">
              Read the quick start
            </Link>
          </div>
        </div>
      </Section>
    </>
  );
}

export default BetaPage;
