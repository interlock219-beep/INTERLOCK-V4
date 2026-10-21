import { Link } from 'react-router-dom';
import { usePageMeta } from '../components/PageMeta';
import { Icon } from '../components/Icon';
import { Reveal } from '../components/Reveal';
import { Section, SectionHead } from '../components/Layout';
import { Callout } from '../components/CodeBlock';
import { Accordion } from '../components/Accordion';

const PLANS = [
  {
    id: 'free',
    name: 'Free evaluation',
    price: '$0',
    unit: 'available now — no account',
    status: 'available' as const,
    statusLabel: 'Available',
    featured: true,
    note: 'Local evaluation tier: the full engine runs unbilled, exactly as before subscriptions existed.',
    features: [
      ['Full source, installed from the public repository', true],
      ['Recovery engine, verification and conflict protection', true],
      ['Unbilled executions in evaluation mode (no wallet, no credits)', true],
      ['Browser-based interactive demo (no install)', true],
      ['Emergency containment and previews — never gated on credits', true],
      ['Recovery-credit allowance — not included', false],
    ] as [string, boolean][],
    cta: { label: 'Join the beta', to: '/beta' },
  },
  {
    id: 'starter',
    name: 'Starter',
    price: '$15',
    unit: 'per month (or $180/year = 12 monthly payments)',
    status: 'soon' as const,
    statusLabel: 'Stripe checkout: per deployment',
    featured: false,
    note: 'For a single operator running regular recoveries. 100 credits every month.',
    features: [
      ['100 recovery credits per month', true],
      ['One credit = one completed AND verified recovery', true],
      ['Failed, partial, unverified or previewed runs cost nothing', true],
      ['Retries and resumes of a billed plan are free', true],
      ['Append-only credit ledger, visible in your billing page', true],
      ['1,000 intents/day, email support, 30-day audit retention', true],
    ] as [string, boolean][],
    cta: { label: 'Join the beta', to: '/beta' },
  },
  {
    id: 'pro',
    name: 'Pro',
    price: '$30',
    unit: 'per month (or $360/year = 12 monthly payments)',
    status: 'soon' as const,
    statusLabel: 'Stripe checkout: per deployment',
    featured: false,
    note: 'For teams that recover often and want the ledger, upgrades and renewals handled automatically.',
    features: [
      ['250 recovery credits per month', true],
      ['Everything in Starter, plus:', true],
      ['Mid-period upgrades grant the difference immediately', true],
      ['Renewals allocate the next allowance exactly once (idempotent)', true],
      ['10,000 intents/day, priority email support, 60-day audit retention', true],
      ['99.9% SLA target', true],
    ] as [string, boolean][],
    cta: { label: 'Join the beta', to: '/beta' },
  },
];

const FAQ = [
  {
    id: 'buy',
    q: 'Can I subscribe today?',
    a: 'The free evaluation is open to everyone with no account. Paid checkout runs through Stripe and activates per deployment once the operator has connected a Stripe account (until then, subscriptions are provisioned server-side in test mode). The prices on this page are the real prices the backend charges — nothing here is a mock-up.',
  },
  {
    id: 'credit',
    q: 'What exactly costs one credit?',
    a: 'One credit is consumed at a single billable point: a recovery plan execution that the engine reports as completed AND independently verified. Previews and simulations are never billed. Failed, stopped, partial or unverified runs release their held credit back to the wallet. A plan consumes at most one credit for its lifetime, so retries and resumes are always free.',
  },
  {
    id: 'ledger',
    q: 'How do I know I was charged correctly?',
    a: 'Every balance change is an entry in an append-only credit ledger: allocations on verified payments, holds placed before executions, consumptions tied to the recovery plan that earned them, releases, expiries and upgrade adjustments. The ledger is tenant-scoped, read-only for customers and reconciles against the wallet on every entry.',
  },
  {
    id: 'expiry',
    q: 'Do unused credits roll over?',
    a: 'No. Unused credits expire when the paid period ends; the expiry is recorded as a ledger entry, and the next renewal allocates the new period’s allowance exactly once. Duplicate or replayed payment webhooks can never allocate twice — allocations are keyed by subscription and billing period.',
  },
  {
    id: 'exhausted',
    q: 'What happens when I run out of credits?',
    a: 'Billable executions are refused with HTTP 402 and a response that states your remaining balance and the renewal time. Previews, planning, evidence review and emergency containment are never blocked by billing — an empty wallet can’t stop you from containing an incident.',
  },
  {
    id: 'enterprise',
    q: 'Do you offer enterprise agreements?',
    a: 'Not today. There is no enterprise product, no contract template and no service-level commitment beyond the Pro SLA target. Any statement to the contrary would be invented.',
  },
];

export function PricingPage() {
  usePageMeta({
    title: 'Pricing — Interlock V6',
    description:
      'Free evaluation tier, plus Starter at $15/month (100 recovery credits) and Pro at $30/month (250 credits). One credit = one completed, verified recovery — enforced by a server-side ledger.',
  });

  return (
    <>
      <div className="page-hero">
        <div className="container">
          <Reveal>
            <span className="eyebrow">Pricing</span>
            <h1>Free to evaluate. Priced on verified recoveries.</h1>
            <p className="section-lead">
              The evaluation tier is free and needs no account. Paid plans grant a monthly
              recovery-credit allowance, and the backend charges exactly one credit per recovery
              it completes and independently verifies — nothing else is ever billed.
            </p>
          </Reveal>
        </div>
      </div>

      <Section labelledBy="plans-title">
        <SectionHead
          id="plans-title"
          eyebrow="Plans"
          title="Three tiers, one billing rule."
          lead="Prices are fixed in a single server-side plan registry the checkout charges from — the client never sets an amount. Yearly billing is always twelve monthly payments."
        />

        <div className="pricing-grid">
          {PLANS.map((plan, index) => (
            <Reveal key={plan.id} delay={index * 70}>
              <article
                className={`price-card${plan.featured ? ' featured' : ''}`}
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
                <Link to={plan.cta.to} className={`btn ${plan.featured ? 'btn-primary' : 'btn-secondary'} btn-block`}>
                  {plan.cta.label}
                </Link>
              </article>
            </Reveal>
          ))}
        </div>

        <Reveal>
          <Callout type="info" title="How paid checkout goes live">
            <p>
              Payments run through Stripe. Checkout buttons appear on deployments where the
              operator has connected a Stripe account; while an account is unconnected (or in
              test mode), the free evaluation tier remains fully open and paid plans are
              provisioned server-side. Every charge still comes from the server-side plan record
              — a client can never submit its own price.
            </p>
          </Callout>
        </Reveal>
      </Section>

      <Section alt labelledBy="credit-model-title">
        <div className="grid grid-2" style={{ alignItems: 'start' }}>
          <Reveal>
            <span className="eyebrow">The credit rule</span>
            <h2 id="credit-model-title">Charge for a unit you can audit.</h2>
            <p className="section-lead">
              A credit is consumed at one precisely defined billable point — a recovery plan
              execution the engine reports as completed and independently verified. The rule is
              enforced by the server, not by the interface.
            </p>
            <ul className="prose-list">
              {[
                'Counts: plan → restore → independent verification passes (one credit, once per plan).',
                'Never counts: previews, simulations, refused or conflicted runs, withheld approval, failed or partial verification.',
                'Never double-charges: a plan that was already billed runs free on every retry and resume; duplicate payment events allocate once.',
                'Auditable: every movement lands in an append-only, tenant-scoped ledger you can read from the billing page.',
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
              <h3>Always free, wallet or not</h3>
              <ul className="compare-list">
                {[
                  'Emergency containment — billing never gates an incident response.',
                  'Previews and simulations of any plan.',
                  'The evaluation tier: tenants without a wallet execute unbilled.',
                  'Re-running a recovery that already consumed its credit.',
                  'Reading your own ledger and invoice history.',
                ].map((item) => (
                  <li key={item}>
                    <Icon name="check" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
              <p className="faint small mb-0">
                Enforcement is a wallet flag on the server: tenants that were never billed have
                no wallet, so nothing about the free tier’s behavior changed when subscriptions
                were added.
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
