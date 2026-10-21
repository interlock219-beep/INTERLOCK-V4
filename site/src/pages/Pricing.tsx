import { Link } from 'react-router-dom';
import { usePageMeta } from '../components/PageMeta';
import { Icon } from '../components/Icon';
import { Reveal } from '../components/Reveal';
import { Section, SectionHead } from '../components/Layout';
import { Callout } from '../components/CodeBlock';
import { Accordion } from '../components/Accordion';

const PLANS = [
  {
    id: 'beta',
    name: 'Free evaluation',
    price: '$0',
    unit: 'available now — no account',
    status: 'available' as const,
    statusLabel: 'Available',
    note: 'Controlled beta, disposable projects, Windows x64.',
    features: [
      ['Full source, installed from the public repository', true],
      ['Recovery engine, verification and conflict protection', true],
      ['Safe demonstration and first-run guide', true],
      ['Browser-based interactive demo (no install)', true],
      ['Structured bug-report template and coordinator support', true],
      ['Any hosted service or dashboard — does not exist', false],
    ] as [string, boolean][],
    cta: { label: 'Join the beta', to: '/beta' },
  },
  {
    id: 'credits',
    name: 'Individual credits (proposed)',
    price: 'TBD',
    unit: 'concept, not for sale',
    status: 'proposed' as const,
    statusLabel: 'Proposed',
    note: 'A pricing concept under evaluation. Nothing here can be purchased.',
    features: [
      ['One credit = one completed recovery workflow (plan → restore → verify) over a single project of up to 50 files', true],
      ['Refused and conflicted runs cost no credit — only a completed, verified run does', true],
      ['Credits would never be charged for retries of the same idempotency key', true],
      ['Published price per credit — not decided', false],
      ['Checkout, invoicing or refund policy — does not exist', false],
    ] as [string, boolean][],
    cta: { label: 'Give feedback in the beta', to: '/beta' },
  },
  {
    id: 'team',
    name: 'Team & enterprise (proposed)',
    price: '—',
    unit: 'not offered today',
    status: 'unavailable' as const,
    statusLabel: 'Not offered',
    note: 'Described only to show direction. There is no team product, contract or SLA.',
    features: [
      ['Shared recovery policy and audit evidence export', true],
      ['Multiple-operator approval workflows', true],
      ['Seat-based or usage-based billing — undecided', true],
      ['Terms, privacy policy, support policy — required first, not written', false],
      ['Invoicing, contracts, tax handling — do not exist', false],
    ] as [string, boolean][],
    cta: { label: 'See the roadmap in docs', to: '/docs/limitations' },
  },
];

const FAQ = [
  {
    id: 'buy',
    q: 'Can I buy something today?',
    a: 'No. There is no billing system, no checkout, no payment processing, no account system and no invoice path anywhere in this project. The pricing on this page is either free-and-available or explicitly marked proposed.',
  },
  {
    id: 'why',
    q: 'Why is there no real price yet?',
    a: 'The release-readiness review concluded that charging customers today is not justified: no customer interviews have happened, willingness to pay is unknown, and the legal, support and incident-response apparatus required for a paid beta does not exist. The recommended path is a consent-based free pilot first.',
  },
  {
    id: 'credits',
    q: 'How would credits work if they are ever built?',
    a: 'The proposal charges for a unit of work you can point at: one completed recovery workflow that reaches a verified result. Refusals, conflicts, retries of the same idempotency key and failed verification would not consume credits, so you are never billed for an ambiguous event or for the tool declining to act.',
  },
  {
    id: 'payment',
    q: 'Is there any payment integration in the code?',
    a: 'The repository contains experimental payment-provider scaffolding that is not wired to a product, not configured with credentials and not reachable from any customer flow. It is not evidence of a purchasable product, and no payment functionality is exposed on this website.',
  },
  {
    id: 'enterprise',
    q: 'Do you offer enterprise agreements?',
    a: 'Not today. There is no enterprise product, no contract template and no service-level commitment. Any statement to the contrary would be invented.',
  },
];

export function PricingPage() {
  usePageMeta({
    title: 'Pricing — Interlock V6',
    description:
      'Interlock is free to evaluate during the controlled beta. Credit and team pricing are proposals only — no checkout, billing system or account exists today.',
  });

  return (
    <>
      <div className="page-hero">
        <div className="container">
          <Reveal>
            <span className="eyebrow">Pricing</span>
            <h1>Free to evaluate. Honest about the rest.</h1>
            <p className="section-lead">
              There is no billing system in this project: nothing here can be purchased, and no
              checkout, invoice or payment flow will ever appear on this site. Everything below is
              either available now for free, or clearly labelled as a proposal.
            </p>
          </Reveal>
        </div>
      </div>

      <Section labelledBy="plans-title">
        <SectionHead
          id="plans-title"
          eyebrow="Plans"
          title="One real option, two honest proposals."
          lead="The free evaluation is genuinely available. The other two rows describe a direction, not a product you can buy."
        />

        <div className="pricing-grid">
          {PLANS.map((plan, index) => (
            <Reveal key={plan.id} delay={index * 70}>
              <article
                className={`price-card${plan.status === 'available' ? ' featured' : ''}`}
                style={{ height: '100%' }}
              >
                <div className="spread" style={{ marginBottom: 'var(--space-3)' }}>
                  <span className="price-name">{plan.name}</span>
                  <span
                    className={`badge ${plan.status === 'available' ? 'badge-green' : 'badge-amber'}`}
                  >
                    <span className="status-dot" /> {plan.statusLabel}
                  </span>
                </div>
                <div className="price-amount">{plan.price}</div>
                <div className="price-note">{plan.unit}</div>
                <p className="small muted">{plan.note}</p>
                <ul className="price-features">
                  {plan.features.map(([label, included]) => (
                    <li key={label} className={included ? undefined : 'off'}>
                      <Icon name={included ? 'check' : 'x'} />
                      <span>{label}</span>
                    </li>
                  ))}
                </ul>
                <Link to={plan.cta.to} className={`btn ${plan.status === 'available' ? 'btn-primary' : 'btn-secondary'} btn-block`}>
                  {plan.cta.label}
                </Link>
              </article>
            </Reveal>
          ))}
        </div>

        <Reveal>
          <Callout type="warn" title="No fake checkout, ever">
            <p>
              If a future version of this site offers a way to pay, it will be attached to a real
              billing system with published terms. Until then, any button that says “Buy”, “Upgrade”
              or “Confirm payment” would be a lie — so none exists.
            </p>
          </Callout>
        </Reveal>
      </Section>

      <Section alt labelledBy="credit-model-title">
        <div className="grid grid-2" style={{ alignItems: 'start' }}>
          <Reveal>
            <span className="eyebrow">Proposed credit model</span>
            <h2 id="credit-model-title">Charge for a unit you can audit.</h2>
            <p className="section-lead">
              If a credit model is ever introduced, the unit of usage would be a completed recovery
              workflow that reaches a verified result — not an ambiguous event, and never a refusal.
            </p>
            <ul className="prose-list">
              {[
                'Counts: plan → restore → verification passes.',
                'Does not count: refused plans, conflicted runs, withheld approval, failed verification.',
                'Never double-charges: retries of the same idempotency key are free.',
                'Recorded: each charge would tie to a verifiable evidence manifest in your own logs.',
              ].map((item) => (
                <li key={item}>
                  <Icon name="check" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </Reveal>
          <Reveal delay={80}>
            <div className="card">
              <h3>What has to exist before charging</h3>
              <ul className="compare-list">
                {[
                  'Customer demand evidence from real interviews and a completed pilot.',
                  'Terms of service, privacy policy, refund policy and a support policy.',
                  'An incident-response runbook with a rehearsed drill.',
                  'External security review of the release candidate.',
                  'Working payment, invoicing and tax handling — none of which exists today.',
                ].map((item) => (
                  <li key={item}>
                    <Icon name="alert" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
              <p className="faint small mb-0">
                Source: the release-readiness report’s “Is charging customers justified today?”
                section, which answers “No”.
              </p>
            </div>
          </Reveal>
        </div>
      </Section>

      <Section labelledBy="pricing-faq-title">
        <div className="grid grid-2" style={{ alignItems: 'start' }}>
          <Reveal>
            <span className="eyebrow">FAQ</span>
            <h2 id="pricing-faq-title">Questions about money.</h2>
            <p className="section-lead">The short answers are above each full one.</p>
          </Reveal>
          <Reveal delay={80}>
            <Accordion items={FAQ.map((item) => ({ id: item.id, question: item.q, answer: <p>{item.a}</p> }))} />
          </Reveal>
        </div>

        <Reveal>
          <div className="cta-band" style={{ marginTop: 'var(--space-6)' }}>
            <div>
              <h2>Try it before anyone talks about money.</h2>
              <p>
                Run the simulated console in your browser, or install from source against a
                disposable project. Both are free, and neither needs an account.
              </p>
            </div>
            <div className="row">
              <Link to="/demo" className="btn btn-primary btn-lg">
                <Icon name="play" /> Try the demo
              </Link>
              <Link to="/beta" className="btn btn-secondary btn-lg">
                Join the beta
              </Link>
            </div>
          </div>
        </Reveal>
      </Section>
    </>
  );
}

export default PricingPage;
