import { Link } from 'react-router-dom';
import { Icon, type IconName } from './Icon';
import type { FeatureEntry } from '../data/site';

const FEATURE_ICON: Record<FeatureEntry['icon'], IconName> = {
  recovery: 'rotate',
  verify: 'shield-check',
  conflict: 'branch',
  refuse: 'shield-x',
  platform: 'globe',
  developer: 'code',
};

export function FeatureCard({ feature }: { feature: FeatureEntry }) {
  return (
    <Link to={`/features#${feature.id}`} className="card card-link" style={{ display: 'block' }}>
      <span className="icon-tile">
        <Icon name={FEATURE_ICON[feature.icon]} />
      </span>
      <h3>{feature.title}</h3>
      <p>{feature.summary}</p>
      <span className="badge" style={{ marginBottom: 'var(--space-4)' }}>
        {feature.statusLabel}
      </span>
      <br />
      <span className="learn">
        Learn more <Icon name="arrow-right" width={14} height={14} />
      </span>
    </Link>
  );
}

export function StatCard({ value, label, caption }: { value: string; label: string; caption: string }) {
  return (
    <div className="stat-card">
      <span className="icon-tile">
        <Icon name="shield-check" />
      </span>
      <div>
        <div className="stat-value">{value}</div>
        <div className="stat-label">{label}</div>
        <div className="stat-caption">{caption}</div>
      </div>
    </div>
  );
}
