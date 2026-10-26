import { useEffect, useState } from 'react';
import { usePageMeta } from '../components/PageMeta';
import { Reveal } from '../components/Reveal';
import { Section, SectionHead } from '../components/Layout';
import { Callout } from '../components/CodeBlock';

const API_BASE = 'http://localhost:8000/api/v1';

interface UsageResponse {
  resource_type: string;
  current: number;
  limit: number | null;
  period_start: string;
  period_end: string;
  percentage: number | null;
}

interface CreditSummary {
  plan_tier: string;
  plan_name: string;
  subscription_status: string;
  billing_enforced: boolean;
  allocated: number;
  consumed: number;
  reserved: number;
  available: number;
  allowance: number;
  period_start: string | null;
  period_end: string | null;
  next_renewal: string | null;
}

interface UsageState {
  status: 'loading' | 'ok' | 'error';
  error?: string;
  usage: UsageResponse[] | null;
  credits: CreditSummary | null;
}

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return iso;
  }
}

function usageLabel(type: string): string {
  const labels: Record<string, string> = {
    recovery_credits: 'Recovery credits',
    intents_per_day: 'Daily intents',
    recovery_executions: 'Recovery executions',
  };
  return labels[type] ?? type.replace(/_/g, ' ');
}

function ProgressBar({ percentage }: { percentage: number | null }) {
  if (percentage === null) {
    return <span className="faint small">Unlimited</span>;
  }
  const pct = Math.min(100, Math.max(0, percentage));
  const getColor = (p: number) => {
    if (p >= 90) return 'var(--color-danger, #e74c3c)';
    if (p >= 75) return 'var(--color-warning, #f39c12)';
    return 'var(--color-success, #27ae60)';
  };
  return (
    <div style={{ width: '100%', minWidth: 160 }}>
      <div
        className="progress-bar"
        style={{
          height: 10,
          background: '#eee',
          borderRadius: 5,
          overflow: 'hidden',
        }}
      >
        <div
          className="progress-fill"
          style={{
            width: `${pct}%`,
            height: '100%',
            background: getColor(pct),
            transition: 'width 0.3s ease',
          }}
        />
      </div>
      <div className="faint small" style={{ marginTop: 2 }}>
        {Math.round(pct)}%
      </div>
    </div>
  );
}

export function UsagePage() {
  const [state, setState] = useState<UsageState>({ status: 'loading', usage: null, credits: null });

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const [usageRes, creditsRes] = await Promise.all([
          fetch(`${API_BASE}/billing/usage`, {
            signal: controller.signal,
            credentials: 'include',
            cache: 'no-store',
          }),
          fetch(`${API_BASE}/billing/credits`, {
            signal: controller.signal,
            credentials: 'include',
            cache: 'no-store',
          }),
        ]);

        if (!usageRes.ok || !creditsRes.ok) {
          throw new Error(`API returned ${usageRes.status},${creditsRes.status}`);
        }

        const usage: UsageResponse[] = await usageRes.json();
        const credits: CreditSummary = await creditsRes.json();
        setState({ status: 'ok', usage, credits });
      } catch (err) {
        if (err instanceof Error && err.name !== 'AbortError') {
          setState({ status: 'error', error: err.message, usage: null, credits: null });
        }
      }
    })();

    return () => controller.abort();
  }, []);

  usePageMeta({
    title: 'Usage & billing — Interlock V6',
    description:
      'Monitor your recovery-credit allowance, usage quotas and billing period. One credit per completed-and-verified recovery.',
  });

  const credits = state.credits;
  const usage = state.usage;

  return (
    <>
      <div className="page-hero">
        <div className="container">
          <Reveal>
            <span className="eyebrow">Usage &amp; billing</span>
            <h1>Recovery-credit allowance and quota usage.</h1>
            <p className="section-lead">
              Credits are consumed only by completed-and-verified recovery executions. This page reads
              the live server-side ledger — the counts here are what the backend enforces.
            </p>
          </Reveal>
        </div>
      </div>

      <Section labelledBy="usage-title">
        <Reveal>
          <SectionHead
            id="usage-title"
            eyebrow="Credit wallet"
            title="This period's recovery credits."
            lead="Allocated at the start of each paid period. Unused credits expire — they never roll over."
          />
        </Reveal>

        {state.status === 'loading' && (
          <p style={{ color: 'var(--color-muted)' }}>Loading usage…</p>
        )}

        {state.status === 'error' && (
          <Callout type="danger" title="Could not load usage">
            <p>
              No billing backend was reachable at <code>{API_BASE}</code>. The usage meter reads the
              live FastAPI billing endpoints (<code>/billing/usage</code> and <code>/billing/credits</code>
              ). Start the server with <code>uvicorn app.main:app --port 8000</code> and reload this page.
            </p>
          </Callout>
        )}

        {state.status === 'ok' && credits && (
          <>
            <div className="grid grid-3" style={{ marginTop: 'var(--space-5)' }}>
              <Reveal delay={0}>
                <div className="card">
                  <div className="stat-value">{credits.allocated}</div>
                  <div className="stat-label">Allocated this period</div>
                  <div className="stat-caption">plan: {credits.plan_name || credits.plan_tier || '—'}</div>
                </div>
              </Reveal>
              <Reveal delay={50}>
                <div className="card">
                  <div className="stat-value">{credits.consumed}</div>
                  <div className="stat-label">Consumed</div>
                  <div className="stat-caption">completed &amp; verified recoveries</div>
                </div>
              </Reveal>
              <Reveal delay={100}>
                <div className="card">
                  <div className="stat-value">{credits.available}</div>
                  <div className="stat-label">Available</div>
                  <div className="stat-caption">
                    {credits.billing_enforced ? 'enforced — bills apply' : 'evaluation mode'}
                  </div>
                </div>
              </Reveal>
            </div>

            <div className="card" style={{ marginTop: 'var(--space-5)' }}>
              <h3>Period</h3>
              <p className="muted small">
                Started: {formatDate(credits.period_start)} — Ends: {formatDate(credits.period_end)}
                <br />
                Next renewal: {formatDate(credits.next_renewal)}
              </p>
              {credits.subscription_status && (
                <p className="muted small">
                  Subscription: {credits.subscription_status}
                </p>
              )}
            </div>
          </>
        )}

        {state.status === 'ok' && usage && usage.length > 0 && (
          <div className="card" style={{ marginTop: 'var(--space-5)' }}>
            <h3>Quota usage</h3>
            <table className="risk-table" style={{ minWidth: '100%' }}>
              <thead>
                <tr>
                  <th>Resource</th>
                  <th>Current</th>
                  <th>Limit</th>
                  <th>Use</th>
                </tr>
              </thead>
              <tbody>
                {usage.map((u) => (
                  <tr key={u.resource_type}>
                    <td>{usageLabel(u.resource_type)}</td>
                    <td>{u.current}</td>
                    <td>{u.limit === null ? 'Unlimited' : u.limit.toLocaleString()}</td>
                    <td>
                      <ProgressBar percentage={u.percentage} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted small" style={{ marginTop: 'var(--space-3)' }}>
              Period: {formatDate(usage[0]?.period_start)} — {formatDate(usage[0]?.period_end)}
            </p>
          </div>
        )}
      </Section>
    </>
  );
}

export default UsagePage;
