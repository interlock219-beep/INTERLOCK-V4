import { Link } from 'react-router-dom';
import { usePageMeta } from '../components/PageMeta';
import { Icon } from '../components/Icon';
import { Reveal } from '../components/Reveal';
import { Section, SectionHead } from '../components/Layout';
import { Callout } from '../components/CodeBlock';
import { SITE } from '../data/site';

const PRINCIPLES = [
  {
    title: 'Recovery over reconstruction',
    body: 'Restore exactly what was captured, or refuse. There is no heuristic “probably looks like this” path, because a plausible guess written over real data is worse than an honest failure.',
  },
  {
    title: 'Verification over confidence',
    body: 'Every claimed result is recomputed from the bytes involved. If a check cannot be performed, the outcome is reported as unknown rather than assumed.',
  },
  {
    title: 'Control stays with the developer',
    body: 'Nothing runs without explicit approval, refusals are never overridden silently, and the whole system can be operated offline from a checkout you control.',
  },
  {
    title: 'Transparency over polish',
    body: 'Limitations, skipped tests, mocked drills and unvalidated platforms are documented in the support matrix — including the parts that make the product look unfinished.',
  },
  {
    title: 'Responsible agent operation',
    body: 'AI agents change real systems faster than humans can review. The goal is a control plane that makes their mistakes cheap to reverse and impossible to miss.',
  },
];

const FACTS = [
  ['Product', 'Interlock V6 — package `intentlock`, version 4.0.0'],
  ['Repository', SITE.repoUrl],
  ['Interfaces', 'Python API, typed SDK, FastAPI REST surface, scripts, LangChain adapter'],
  ['Primary platform', 'Windows x64 / NTFS / Python 3.11.9 (tested)'],
  ['Status', 'Controlled beta; general availability explicitly not ready'],
  ['Licensing', 'Proprietary — see LICENSE in the repository'],
  ['Company', 'None disclosed. No founders, employees, funding or customers are claimed here.'],
];

export function AboutPage() {
  usePageMeta({
    title: 'About — Interlock V6',
    description:
      'Interlock is a recovery and verification layer for AI agents: recover from harmful changes, prove the result, and keep humans in control. This is what it is built on.',
  });

  return (
    <>
      <div className="page-hero">
        <div className="container">
          <Reveal>
            <span className="eyebrow">About</span>
            <h1>Agents move fast. Recovery has to be boring.</h1>
            <p className="section-lead">
              Interlock exists because the gap between &ldquo;an agent changed something&rdquo; and
              &ldquo;I can prove what it changed&rdquo; is where real damage happens. The product is
              built to close that gap — and to be honest about the places it does not.
            </p>
          </Reveal>
        </div>
      </div>

      <Section labelledBy="mission-title">
        <div className="grid grid-2" style={{ alignItems: 'start' }}>
          <Reveal>
            <span className="eyebrow">Mission</span>
            <h2 id="mission-title">Make agent mistakes cheap to reverse.</h2>
            <p className="section-lead">
              Coding agents, tool-using assistants and automated scripts now write files, run
              migrations and change configuration as a matter of course. When one of them goes
              wrong, the recovery question is not theoretical: someone has to reconstruct state
              under pressure, usually without knowing what the state was.
            </p>
            <p className="muted">
              Interlock records before-and-after evidence at authorisation time, can restore the
              previous bytes exactly, refuses to overwrite human work that landed afterwards, and
              verifies the outcome with recomputed digests. It runs locally, offline, without an
              account.
            </p>
          </Reveal>
          <Reveal delay={80}>
            <div className="card">
              <h3>Project facts</h3>
              <ul className="compare-list">
                {FACTS.map(([label, value]) => (
                  <li key={label}>
                    <Icon name="info" />
                    <span>
                      <strong>{label}</strong>
                      <br />
                      {value.startsWith('http') ? (
                        <a href={value} target="_blank" rel="noopener noreferrer">
                          {value}
                        </a>
                      ) : (
                        value
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>
        </div>
      </Section>

      <Section alt labelledBy="principles-title">
        <SectionHead
          id="principles-title"
          eyebrow="Design principles"
          title="What the product is built on."
          lead="These are engineering choices, not slogans: each one is visible in the code, the tests, and the limitations we publish."
        />
        <div className="grid grid-3">
          {PRINCIPLES.map((principle, index) => (
            <Reveal key={principle.title} delay={index * 60}>
              <div className="card" style={{ height: '100%' }}>
                <span className="icon-tile">
                  <Icon name="shield" />
                </span>
                <h3>{principle.title}</h3>
                <p className="mb-0">{principle.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </Section>

      <Section labelledBy="honesty-title">
        <div className="grid grid-2" style={{ alignItems: 'start' }}>
          <Reveal>
            <span className="eyebrow">Transparency</span>
            <h2 id="honesty-title">What this site deliberately omits.</h2>
            <ul className="prose-list">
              {[
                'Customer counts, downloads, revenue and usage metrics — none exist.',
                'Performance benchmarks beyond recorded test runs — the benchmark suite is frozen and not run.',
                'Security certifications and audits — an external audit is a GA requirement, not a completed fact.',
                'Testimonials, logos, star counts and press quotes — there are none.',
                'Download links, checksums and installers — no release artifact has been published.',
                'Sign-in, accounts and payment flows — no backend for any of them is configured.',
              ].map((item) => (
                <li key={item}>
                  <Icon name="x" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </Reveal>
          <Reveal delay={80}>
            <Callout type="info" title="Why the restraint">
              <p>
                Confidence in a safety tool has to come from engineering quality and evidence, not
                from claims nobody can check. Where evidence is missing, this site says so — and
                points at the document that records the gap.
              </p>
            </Callout>
            <Callout type="warn" title="Where the evidence lives">
              <p>
                <code>INTERLOCK_V6_RELEASE_READINESS_REPORT.md</code>,{' '}
                <code>docs/operations/SUPPORTED_PLATFORMS.md</code> and{' '}
                <code>docs/operations/SAFETY_AND_LIMITATIONS.md</code> in the repository are the
                sources behind every number on this site.
              </p>
            </Callout>
            <div className="row">
              <a
                href={SITE.repoUrl}
                className="btn btn-secondary"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Icon name="github" width={16} height={16} /> Read the source
              </a>
              <Link to="/safety" className="btn btn-ghost">
                Safety &amp; security
              </Link>
            </div>
          </Reveal>
        </div>
      </Section>
    </>
  );
}

export default AboutPage;
