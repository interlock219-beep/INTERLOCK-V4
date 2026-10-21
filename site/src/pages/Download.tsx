import { useState } from 'react';
import { Link } from 'react-router-dom';
import { usePageMeta } from '../components/PageMeta';
import { Icon } from '../components/Icon';
import { Reveal } from '../components/Reveal';
import { Section, SectionHead } from '../components/Layout';
import { Callout, CodeBlock, Terminal } from '../components/CodeBlock';
import { Tabs } from '../components/Accordion';
import {
  INSTALL_OPTIONS,
  PLATFORMS,
  SITE,
  TERMINAL_COMMANDS,
  TERMINAL_STATUS,
  TEST_COMMAND,
  TEST_RESULT,
  UNSUPPORTED_ENVIRONMENTS,
  VS_CODE_STATUS,
} from '../data/site';

const PREREQS = [
  'Python 3.11 or newer, below 3.15 (3.11.9 is the verified version)',
  'git and pip',
  'About 2 GB of free disk for the virtual environment',
  'A disposable project directory to point the beta at',
];

const NOT_REQUIRED = ['Docker', 'PostgreSQL', 'Redis', 'Administrator / root', 'Network access at run time'];

export function DownloadPage() {
  // Card A's CTA discloses the real (unavailable) state — it never fakes an install.
  const [vsOpen, setVsOpen] = useState(false);

  usePageMeta({
    title: 'Install — Interlock V6',
    description:
      'Two ways to work with Interlock V6: build the VS Code extension from the source in this repository, or install the terminal runner from the public repository. Nothing is published to a marketplace or PyPI. Windows x64 is the tested platform; macOS and Linux have not completed native validation.',
  });

  return (
    <>
      <div className="page-hero">
        <div className="container">
          <Reveal>
            <span className="eyebrow">Installation</span>
            <h1>Build from source. Nothing published yet.</h1>
            <p className="section-lead">
              Two interfaces, one engine: run Interlock from your terminal today, or build the VS
              Code extension from the source in this repository. Nothing is distributed through
              PyPI, npm or any marketplace, so no download link or checksum appears anywhere on
              this site.
            </p>
          </Reveal>
        </div>
      </div>

      {/* ---------------- choose your workflow: two cards ---------------- */}
      <Section labelledBy="workflow-title">
        <SectionHead
          id="workflow-title"
          eyebrow="CHOOSE YOUR WORKFLOW"
          title="One engine. Two ways to work."
          lead="Use Interlock inside VS Code or run it directly from your terminal."
          sub="Both interfaces are designed to use the same underlying Interlock engine."
        />

        <Reveal>
          <div className="wf-grid">
            {INSTALL_OPTIONS.map((option) => {
              const pending = option.id === 'vscode';
              const inPageSecondary = option.secondaryTarget.startsWith('#');

              return (
                <article
                  key={option.id}
                  className={`wf-card${pending ? '' : ' ready'}`}
                  aria-labelledby={`wf-${option.id}-title`}
                >
                  <div className="wf-head">
                    <span className="wf-icon">
                      <Icon name={option.icon} width={26} height={26} />
                    </span>
                    <span className={`badge badge-${option.statusTone}`}>
                      <span className="status-dot" /> {option.statusLabel}
                    </span>
                  </div>

                  <h3 id={`wf-${option.id}-title`}>{option.title}</h3>
                  <p className="wf-desc">{option.description}</p>
                  <p className="wf-note small">{option.statusNote}</p>

                  {pending ? (
                    <>
                      <button
                        type="button"
                        className="btn btn-primary btn-block"
                        aria-expanded={vsOpen}
                        aria-controls="vscode-unavailable"
                        onClick={() => setVsOpen((open) => !open)}
                      >
                        <Icon name="vscode" /> {option.primaryLabel}
                      </button>

                      <div className="wf-panel" id="vscode-unavailable" hidden={!vsOpen}>
                        <p className="wf-panel-title">
                          <strong>{VS_CODE_STATUS.badge}.</strong> {VS_CODE_STATUS.headline}
                        </p>
                        <ul>
                          {VS_CODE_STATUS.facts.map((fact) => (
                            <li key={fact}>{fact}</li>
                          ))}
                        </ul>
                        <p className="small mb-0">
                          Next step:{' '}
                          <a href="#install-vscode">
                            view the VS Code installation instructions
                          </a>{' '}
                          — current status, engine prerequisite, interface capabilities and
                          diagnostics.
                        </p>
                      </div>
                    </>
                  ) : (
                    <a className="btn btn-primary btn-block" href={option.primaryTarget}>
                      <Icon name={option.icon} /> {option.primaryLabel}
                    </a>
                  )}

                  {inPageSecondary ? (
                    <a className="wf-secondary" href={option.secondaryTarget}>
                      {option.secondaryLabel} <Icon name="arrow-right" width={14} height={14} />
                    </a>
                  ) : (
                    <Link className="wf-secondary" to={option.secondaryTarget}>
                      {option.secondaryLabel} <Icon name="arrow-right" width={14} height={14} />
                    </Link>
                  )}
                </article>
              );
            })}
          </div>
        </Reveal>

        <p className="compat-note small">
          Platform support depends on the validated engine, dependencies, and installation method.{' '}
          <Link to="/docs/supported-platforms">See the compatibility guide</Link> for current
          support status.
        </p>

        <div className="panel panel-pad">
          <h3>Compatibility status</h3>
          <ul className="compare-list">
            {PLATFORMS.map((platform) => (
              <li key={platform.id}>
                <Icon
                  name={platform.status === 'tested' ? 'check-circle' : 'alert'}
                  style={{ color: platform.status === 'tested' ? 'var(--green)' : 'var(--amber)' }}
                />
                <span>
                  <strong>{platform.name}</strong> — {platform.statusLabel}. {platform.arch} ·{' '}
                  {platform.python}
                </span>
              </li>
            ))}
          </ul>
          <p className="small faint mb-0">
            macOS and Linux have not completed native validation, and Windows ARM64 is untested.
            Nothing above is an installer: every install runs from a checkout. Full detail:{' '}
            <Link to="/docs/supported-platforms">supported platforms</Link>.
          </p>
        </div>

        <Reveal>
          <Callout type="warn" title="No published binaries, no published checksums">
            <p>
              There is no published release artifact to download, therefore no published checksum,
              signature or installer to advertise. If you find a &ldquo;Interlock installer&rdquo;
              somewhere else, it did not come from this repository. Verify anything you run
              against{' '}
              <a href={SITE.repoUrl} target="_blank" rel="noopener noreferrer">
                {SITE.repoUrl}
              </a>
              .
            </p>
          </Callout>
        </Reveal>
      </Section>

      <Section alt labelledBy="prereq-title" id="prereq">
        <div className="grid grid-2">
          <Reveal>
            <span className="eyebrow">Prerequisites</span>
            <h2 id="prereq-title">What you need.</h2>
            <ul className="prose-list">
              {PREREQS.map((item) => (
                <li key={item}>
                  <Icon name="check" />
                  {item}
                </li>
              ))}
            </ul>
          </Reveal>
          <Reveal delay={80}>
            <span className="eyebrow">Not required</span>
            <h2>What you do not need.</h2>
            <ul className="prose-list">
              {NOT_REQUIRED.map((item) => (
                <li key={item}>
                  <Icon name="x" />
                  {item}
                </li>
              ))}
            </ul>
          </Reveal>
        </div>
      </Section>

      {/* ---------------- installation instructions: VS Code ---------------- */}
      <Section labelledBy="vscode-title" id="install-vscode">
        <SectionHead
          id="vscode-title"
          eyebrow="Installation instructions"
          title="Install for VS Code."
          lead="Use Interlock directly inside your development environment. The editor interface exists in this repository: build it locally, install the resulting local package, and the engine is installed and verified for you. Nothing is published, so this page never offers a download."
        />

        <Callout type="warn" title={VS_CODE_STATUS.badge}>
          <p>{VS_CODE_STATUS.headline}</p>
          <ul>
            {VS_CODE_STATUS.facts.map((fact) => (
              <li key={fact}>{fact}</li>
            ))}
          </ul>
        </Callout>

        <div className="grid grid-2" style={{ alignItems: 'start' }}>
          <div className="stack">
            <div className="panel panel-pad">
              <h3>Install routes</h3>
              <ul className="compare-list">
                <li>
                  <Icon name="x" />
                  <span>
                    <strong>Marketplace installation</strong> — no listing exists, so there is no
                    extension identifier to install and no Marketplace URL is shown.
                  </span>
                </li>
                <li>
                  <Icon name="check" />
                  <span>
                    <strong>Build the local <code>.vsix</code></strong> — the extension source is in
                    this repository. In <code>extensions/vscode/</code> run{' '}
                    <code>npm install</code> and <code>npm run package</code>, then install the
                    resulting file with <code>code --install-extension</code>. The artifact is
                    local: it is not published and carries no published checksum.
                  </span>
                </li>
                <li>
                  <Icon name="check" />
                  <span>
                    <strong>Build from source</strong> — the same source tree is what the packaging
                    step consumes, so <code>npm run package</code> is the whole build.
                  </span>
                </li>
              </ul>
              <p className="small faint mb-0">
                Nothing on this page marks the extension as installed: the local build is yours to
                make and to verify. Track or propose editor work in the repository:{' '}
                <a href={SITE.repoUrl} target="_blank" rel="noopener noreferrer">
                  {SITE.repoLabel}
                </a>
                .
              </p>
            </div>

            <div className="panel panel-pad">
              <h3>Engine prerequisite (required either way)</h3>
              <p className="small muted">{VS_CODE_STATUS.engineNote}</p>
              <CodeBlock code={TERMINAL_COMMANDS.verify} language="bash" />
              <p className="small muted mb-0">
                Then follow the <a href="#install-terminal">terminal installation instructions</a> —
                the engine installs the same way with or without an editor attached.
              </p>
            </div>
          </div>

          <div className="stack">
            <div className="panel panel-pad">
              <h3>{VS_CODE_STATUS.capabilitiesTitle}</h3>
              <ul className="compare-list">
                {VS_CODE_STATUS.capabilities.map((item) => (
                  <li key={item}>
                    <Icon name="arrow-right" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
              <p className="small faint mb-0">
                This describes the interface as it exists in the repository. The editor stays a
                thin interface over the shared engine — recovery, security and verification logic
                are not duplicated in an extension.
              </p>
            </div>

            <div className="panel panel-pad">
              <h3>Diagnosing installation and engine-connection errors</h3>
              {VS_CODE_STATUS.diagnostics.map((item) => (
                <div className="err-item" key={item.check}>
                  <p className="err-msg">
                    <strong>{item.check}</strong>
                  </p>
                  {item.code ? <CodeBlock code={item.code} language="bash" /> : null}
                  <p className="small muted mb-0">{item.note}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Section>

      {/* ---------------- installation instructions: terminal ---------------- */}
      <Section alt labelledBy="install-title" id="install-terminal">
        <SectionHead
          id="install-title"
          eyebrow="Installation instructions"
          title="Install for Terminal."
          lead="Run Interlock from your terminal and integrate it into your development workflow. Validated end-to-end on Windows x64; macOS and Linux remain in validation. Every command below appears verbatim in the controlled-beta first-run guide, where it was executed on the reference host before being documented."
        />

        <div className="wf-status">
          <div className="panel panel-pad">
            <h3>Validated today</h3>
            <ul className="compare-list">
              {TERMINAL_STATUS.validated.map((item) => (
                <li key={item}>
                  <Icon name="check-circle" style={{ color: 'var(--green)' }} />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="panel panel-pad">
            <h3>Pending validation</h3>
            <ul className="compare-list">
              {TERMINAL_STATUS.pending.map((item) => (
                <li key={item}>
                  <Icon name="alert" style={{ color: 'var(--amber)' }} />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="grid grid-2" style={{ alignItems: 'start' }}>
          <div className="steps">
            {[
              {
                n: 1,
                title: 'Clone the repository',
                body: 'The only supported install path is from tracked files.',
                code: TERMINAL_COMMANDS.clone,
              },
              {
                n: 2,
                title: 'Create and activate a virtual environment',
                body: 'Windows PowerShell below; macOS/Linux use `source .venv/bin/activate`.',
                code: `python -m venv .venv\n${TERMINAL_COMMANDS.activateWindows}`,
              },
              {
                n: 3,
                title: 'Install with the dev and security extras',
                body: 'Pulls pytest, ruff, mypy, bandit, pip-audit and the SBOM generator alongside the runtime.',
                code: TERMINAL_COMMANDS.install,
              },
              {
                n: 4,
                title: 'Verify the install',
                body: 'Three checks that must pass before you go further.',
                code: TERMINAL_COMMANDS.verify,
              },
              {
                n: 5,
                title: 'Run the safe demonstration',
                body: 'Disposable temp directory, no network, no repository files touched. It deletes its own workspace afterwards.',
                code: TERMINAL_COMMANDS.usage,
              },
              {
                n: 6,
                title: 'Optional: run the control plane locally',
                body: 'Only needed if you want the REST surface; the recovery engine itself does not require it.',
                code: TERMINAL_COMMANDS.server,
              },
            ].map((step) => (
              <div className="step" key={step.n}>
                <span className="step-num">{step.n}</span>
                <div style={{ minWidth: 0 }}>
                  <h3>{step.title}</h3>
                  <p>{step.body}</p>
                  <CodeBlock code={step.code} language="bash" />
                </div>
              </div>
            ))}
          </div>

          <div className="stack">
            <Reveal>
              <Terminal
                title="interlock — install & verify"
                lines={[
                  { kind: 'prompt', text: `git clone ${SITE.repoUrl}.git` },
                  { kind: 'out', text: "Cloning into 'INTERLOCK-V4'... done." },
                  { kind: 'prompt', text: 'python --version' },
                  { kind: 'ok', text: 'Python 3.11.9' },
                  { kind: 'prompt', text: 'pip install -e ".[dev,security]"' },
                  { kind: 'out', text: 'Successfully installed intentlock-4.0.0' },
                  { kind: 'prompt', text: 'python -m pip check' },
                  { kind: 'ok', text: 'No broken requirements found' },
                  { kind: 'prompt', text: 'python scripts/pilot_demo_v1.py' },
                  { kind: 'ok', text: '{ "recovery": true, "safety": true,' },
                  { kind: 'ok', text: '  "human_change": true, "idempotency": true,' },
                  { kind: 'ok', text: '  "overall_pass": true, "exit_code": 0 }' },
                ]}
              />
            </Reveal>

            <Reveal delay={60}>
              <div className="panel panel-pad">
                <h3>Minimal usage</h3>
                <p className="small muted">
                  There is no <code>interlock</code> console binary — the working entry points are
                  the demo script, the Python/SDK interfaces and the optional control plane.
                </p>
                <CodeBlock code={TERMINAL_COMMANDS.usage} language="bash" />
                <CodeBlock code={TERMINAL_COMMANDS.server} language="bash" />
                <p className="faint small mb-0">
                  Interface reference: <Link to="/docs/cli-api">CLI &amp; API docs</Link>.
                </p>
              </div>
            </Reveal>

            <Reveal delay={100}>
              <div className="panel panel-pad">
                <h3>Upgrade and uninstall</h3>
                <p className="small muted">Upgrade — pull and reinstall the editable package:</p>
                <CodeBlock code={TERMINAL_COMMANDS.upgrade} language="bash" />
                <p className="small muted">Uninstall — remove the package from the environment:</p>
                <CodeBlock code={TERMINAL_COMMANDS.uninstall} language="bash" />
                <p className="faint small mb-0">
                  Deleting the clone and the <code>.venv</code> directory removes everything else;
                  nothing is installed system-wide.
                </p>
              </div>
            </Reveal>

            <Reveal delay={140}>
              <div className="panel panel-pad">
                <h3>Run the regression subset</h3>
                <p className="small muted">
                  The evidence you can reproduce yourself after installing.
                </p>
                <CodeBlock code={TEST_COMMAND} language="bash" />
                <p className="faint small mb-0">{TEST_RESULT}</p>
              </div>
            </Reveal>
          </div>
        </div>

        <div className="panel panel-pad" style={{ marginTop: 'var(--space-5)' }}>
          <h3>Common dependency errors</h3>
          {TERMINAL_STATUS.commonErrors.map((item) => (
            <div className="err-item" key={item.error}>
              <p className="err-msg">
                <code>{item.error}</code>
              </p>
              <p className="small muted mb-0">
                {item.fix} <Link to={item.href}>{item.linkLabel} →</Link>
              </p>
            </div>
          ))}
        </div>
      </Section>

      <Section labelledBy="unsupported-title">
        <SectionHead
          id="unsupported-title"
          eyebrow="Boundaries"
          title="Environments that are not supported."
          lead="Attempting recovery on these filesystems or layouts is outside the safety contract — there is no atomic-replace guarantee to lean on."
        />
        <Reveal>
          <div className="card">
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
      </Section>

      <Section alt labelledBy="platform-questions-title">
        <div className="grid grid-2" style={{ alignItems: 'start' }}>
          <Reveal>
            <span className="eyebrow">Next steps</span>
            <h2 id="platform-questions-title">After installing.</h2>
            <Tabs
              label="Post-install paths"
              tabs={[
                {
                  id: 'demo',
                  label: 'Try the demo',
                  content: (
                    <p className="muted">
                      New to the workflow? Run the browser simulation first — it teaches the state
                      machine, the approval step and the refusal cases without touching a single
                      file. <Link to="/demo">Open the demo →</Link>
                    </p>
                  ),
                },
                {
                  id: 'docs',
                  label: 'Read the docs',
                  content: (
                    <p className="muted">
                      Quick start, how recovery works, verification, conflict handling and
                      troubleshooting — all checked against the implementation.{' '}
                      <Link to="/docs">Open documentation →</Link>
                    </p>
                  ),
                },
                {
                  id: 'beta',
                  label: 'Join the beta',
                  content: (
                    <p className="muted">
                      The controlled beta runs on disposable projects and reports back through a
                      structured template. <Link to="/beta">Beta details →</Link>
                    </p>
                  ),
                },
              ]}
            />
          </Reveal>
          <Reveal delay={80}>
            <Callout type="info" title="Troubleshooting install failures">
              <p>
                If <code>pip install</code> fails, stop and report it rather than improvising a
                workaround — the install path itself is part of what the beta validates. See{' '}
                <Link to="/docs/troubleshooting">troubleshooting</Link> for the common failure modes
                and the exact information a useful bug report contains.
              </p>
            </Callout>
          </Reveal>
        </div>
      </Section>
    </>
  );
}

export default DownloadPage;
