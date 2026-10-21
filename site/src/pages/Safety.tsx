import { Link } from 'react-router-dom';
import { usePageMeta } from '../components/PageMeta';
import { Icon } from '../components/Icon';
import { Reveal } from '../components/Reveal';
import { Section, SectionHead } from '../components/Layout';
import { Callout, CodeBlock } from '../components/CodeBlock';
import { Accordion } from '../components/Accordion';
import { SAFETY_CAN, SAFETY_CANNOT, SITE, UNSUPPORTED_ENVIRONMENTS } from '../data/site';

const CONFINEMENT = [
  'Reads and writes only inside the configured project directory you point it at.',
  'Path normalisation rejects traversal (`file:../…`) with zero side effects.',
  'Staging refuses to follow planted symlinks: `O_EXCL` plus a pre-unlink.',
  'A same-directory staging file and `os.replace` keep the swap atomic on NTFS/APFS/ext4.',
  'No network sockets during the tested recovery workflow, and no telemetry anywhere.',
  'Ordinary user permissions only — no admin/root, registry, services, cron or firewall changes.',
];

const REFUSAL_CONDITIONS = [
  ['Path outside the confinement boundary', 'Refused with a typed error before any work starts.'],
  ['Missing pre-action evidence for a target', 'Plan refused — restoring would mean inventing content.'],
  ['Current content differs from the expected state', 'Typed `blocked_by_conflict`; the file is untouched.'],
  ['Malformed or hostile backup manifest', 'Import fails closed; covered by 19 fault-injection drills.'],
  ['Duplicate compensation delivery', 'Refused — never double-applied.'],
];

const VERIFIED_CAPABILITIES = [
  'Byte-exact restore of files an agent deleted or overwrote (Windows x64).',
  'Refusal to overwrite a human edit made after the agent action.',
  'Idempotent replay — duplicates are never applied twice.',
  'Path-traversal refusal with zero side effects.',
  'Survival of a hard process kill mid-recovery without torn writes (20/20 drills, Windows).',
  'Fail-closed typed errors on malformed or hostile backups.',
  'Independent digest verification of the restored content.',
];

const PLANNED_CAPABILITIES = [
  'Native macOS validation (declared; CI cell defined, not executed).',
  'Native Linux validation (declared; CI cell defined, not executed).',
  'Real disk-full (ENOSPC) drill — procedure prepared, authorization never granted.',
  'POSIX permission assertions executing on a POSIX host (tests exist, currently skip).',
  'External security audit (required before general availability, not started).',
  'Console command, hosted service, dashboard and account system (do not exist).',
];

const BACKUP_NOTES = [
  '`export_backup` / `restore_backup` are local operator utilities: they require the application to be stopped and are only as trustworthy as the directory they live in.',
  'Backup artifacts on POSIX currently use default umask permissions — a documented open item, not a hardened guarantee.',
  'Manifest integrity is unkeyed SHA-256: tamper-evidence, not tamper-proofing.',
  'Interlock complements version control. It does not replace an independent backup of anything you care about.',
];

export function SafetyPage() {
  usePageMeta({
    title: 'Safety & security — Interlock V6',
    description:
      'The Interlock recovery safety model: confinement, conflict detection, verification, refusal conditions, backup considerations, known limitations and security reporting.',
  });

  return (
    <>
      <div className="page-hero">
        <div className="container">
          <Reveal>
            <span className="eyebrow">Safety &amp; security</span>
            <h1>Built for safety. Designed for transparency.</h1>
            <p className="section-lead">
              Interlock helps you recover and verify your data, but it is not a magic solution.
              This page separates demonstrated capabilities from planned ones, and states plainly
              what no recovery tool can promise.
            </p>
          </Reveal>
        </div>
      </div>

      <Section labelledBy="model-title">
        <SectionHead
          id="model-title"
          eyebrow="Recovery safety model"
          title="Refuse first, recover second."
          lead="The design principle is simple: when a precondition cannot be proven, the operation refuses instead of guessing. A refusal you can rely on is worth more than a success you cannot."
        />
        <div className="grid grid-2">
          <Reveal>
            <div className="card">
              <h3>Confinement &amp; boundaries</h3>
              <ul className="compare-list">
                {CONFINEMENT.map((item) => (
                  <li key={item}>
                    <Icon name="lock" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>
          <Reveal delay={80}>
            <div className="card">
              <h3>Refusal conditions</h3>
              <ul className="compare-list">
                {REFUSAL_CONDITIONS.map(([condition, behaviour]) => (
                  <li key={condition}>
                    <Icon name="shield-x" />
                    <span>
                      <strong>{condition}</strong>
                      <br />
                      {behaviour}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>
        </div>
      </Section>

      <Section alt labelledBy="can-cannot-title">
        <SectionHead
          id="can-cannot-title"
          eyebrow="Honest scope"
          title="What Interlock can do — and what it cannot guarantee."
          lead="Left: capabilities with recorded evidence. Right: promises nobody should accept from any recovery tool, including this one."
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
          <Callout type="danger" title="Independent backups remain essential">
            <p>
              Not every file, filesystem or failure mode is recoverable. Not every operating system
              has been validated. Keep your own backups, keep humans in the loop, and treat a
              refusal or conflict as information rather than an obstacle.
            </p>
          </Callout>
        </Reveal>
      </Section>

      <Section labelledBy="verification-title" id="verification">
        <div className="grid grid-2" style={{ alignItems: 'start' }}>
          <Reveal>
            <span className="eyebrow">Verification behaviour</span>
            <h2 id="verification-title">Success is computed, not declared.</h2>
            <p className="section-lead">
              After every restore, the target is re-read and its digest recomputed. A mismatch is a
              typed, fail-closed error with the evidence preserved — never a warning in a log.
            </p>
            <CodeBlock
              filename="independent check (yours, not ours)"
              code={'# Windows\n(Get-FileHash .\\config.yaml -Algorithm SHA256).Hash\n\n# macOS / Linux\nsha256sum ./config.yaml'}
            />
            <p className="faint small">
              Error messages are content-free by design: a regression test asserts secrets never
              appear in them. They do contain file names — redact paths if your filenames are
              sensitive.
            </p>
          </Reveal>
          <Reveal delay={80}>
            <span className="eyebrow">Conflict detection</span>
            <h2>Human work is preserved.</h2>
            <p className="section-lead">
              Before the atomic swap, current bytes are compared with the state the plan expects.
              Any drift stops that restore and returns <code>blocked_by_conflict</code>.
            </p>
            <Callout type="warn" title="A documented window">
              <p>
                A micro-second TOCTOU window exists between the existence check and{' '}
                <code>os.replace</code>. The design assumes a single writer; concurrent-writer
                behaviour is mocked in tests and is not a claimed guarantee.
              </p>
            </Callout>
          </Reveal>
        </div>
      </Section>

      <Section alt labelledBy="backup-title">
        <div className="grid grid-2" style={{ alignItems: 'start' }}>
          <Reveal>
            <span className="eyebrow">Backup considerations</span>
            <h2 id="backup-title">Backups are your responsibility.</h2>
            <ul className="prose-list">
              {BACKUP_NOTES.map((item) => (
                <li key={item}>
                  <Icon name="database" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </Reveal>
          <Reveal delay={80}>
            <span className="eyebrow">Unsupported scenarios</span>
            <h2>Where it must not be used.</h2>
            <ul className="prose-list">
              {UNSUPPORTED_ENVIRONMENTS.map((item) => (
                <li key={item}>
                  <Icon name="x" />
                  <span>{item}</span>
                </li>
              ))}
              {SAFETY_CANNOT.slice(1, 4).map((item) => (
                <li key={item}>
                  <Icon name="alert" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </Reveal>
        </div>
      </Section>

      <Section labelledBy="verified-planned-title">
        <SectionHead
          id="verified-planned-title"
          eyebrow="Evidence status"
          title="Demonstrated versus planned."
          lead="Nothing in the right-hand column is described elsewhere on this site as working."
        />
        <div className="compare">
          <Reveal>
            <div className="compare-col can">
              <h3>
                <Icon name="check-circle" width={20} height={20} /> Demonstrated
              </h3>
              <ul className="compare-list">
                {VERIFIED_CAPABILITIES.map((item) => (
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
                <Icon name="clock" width={20} height={20} /> Planned or pending
              </h3>
              <ul className="compare-list">
                {PLANNED_CAPABILITIES.map((item) => (
                  <li key={item}>
                    <Icon name="clock" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>
        </div>
      </Section>

      <Section alt labelledBy="beta-safe-title">
        <div className="grid grid-2" style={{ alignItems: 'start' }}>
          <Reveal>
            <span className="eyebrow">Safe beta testing</span>
            <h2 id="beta-safe-title">How to test without risking anything you need.</h2>
            <ul className="prose-list">
              {[
                'Use a fresh clone and a disposable directory you create yourself.',
                'Never point Interlock at data you cannot afford to lose.',
                'Verify every recovery with your own hash tool.',
                'Report any network attempt during the workflow — none should occur.',
                'Stop if the same crash happens twice; keep the artifacts.',
                'You may stop at any time; partial results are still useful.',
              ].map((item) => (
                <li key={item}>
                  <Icon name="check" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
            <Link to="/beta" className="btn btn-primary">
              Beta programme <Icon name="arrow-right" />
            </Link>
          </Reveal>
          <Reveal delay={80}>
            <span className="eyebrow">Security reporting</span>
            <h2>Report a vulnerability.</h2>
            <Accordion
              items={[
                {
                  id: 'where',
                  question: 'Where do I report?',
                  answer: (
                    <p>
                      The project&rsquo;s <code>SECURITY.md</code> lists{' '}
                      <strong>{SITE.securityEmail}</strong> as the reporting address, and the
                      repository exposes GitHub security advisories at{' '}
                      <a href={`${SITE.repoUrl}/security`} target="_blank" rel="noopener noreferrer">
                        {SITE.repoUrl}/security
                      </a>
                      . Include a description, reproduction steps, potential impact and any
                      suggested remediation.
                    </p>
                  ),
                },
                {
                  id: 'scope',
                  question: 'What is in scope?',
                  answer: (
                    <p>
                      Auth bypass, token forgery or replay, SQL/shell injection, path traversal,
                      SSRF and DNS rebinding, prompt-injection or policy bypass, audit-log
                      tampering, exploitable runtime dependency issues, and container image issues.
                    </p>
                  ),
                },
                {
                  id: 'outscope',
                  question: 'What is out of scope?',
                  answer: (
                    <p>
                      Social engineering, physical security, third-party issues that are not
                      exploitable through Interlock, and denial of service without a demonstrated
                      security impact.
                    </p>
                  ),
                },
                {
                  id: 'safeharbour',
                  question: 'What about safe harbour?',
                  answer: (
                    <p>
                      The published policy states that good-faith reports that avoid privacy
                      violations, data destruction and service disruption will not face legal
                      action, and that credit is offered unless anonymity is preferred. Response
                      windows stated there: acknowledgement within 5 business days, detailed
                      response within 10.
                    </p>
                  ),
                },
              ]}
            />
            <Callout type="info" title="Acknowledgement windows are the project’s stated policy">
              <p>
                They are documented in <code>SECURITY.md</code>; this site does not independently
                verify response times.
              </p>
            </Callout>
          </Reveal>
        </div>
      </Section>
    </>
  );
}

export default SafetyPage;
