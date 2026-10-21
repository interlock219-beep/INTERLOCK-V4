import { Link } from 'react-router-dom';
import { usePageMeta } from '../components/PageMeta';
import { Icon } from '../components/Icon';
import { PRIMARY_NAV } from '../data/site';

export function NotFoundPage() {
  usePageMeta({
    title: 'Page not found — Interlock V6',
    description: 'The page you requested does not exist.',
  });

  return (
    <div className="notfound container">
      <div>
        <div className="code">404</div>
        <h1>That route does not exist.</h1>
        <p className="muted" style={{ maxWidth: '52ch', marginInline: 'auto' }}>
          No page is served at this path — and no broken link should have brought you here. Pick a
          real destination below.
        </p>
        <div className="row" style={{ justifyContent: 'center' }}>
          <Link to="/" className="btn btn-primary">
            <Icon name="shield" /> Back to home
          </Link>
          <Link to="/docs" className="btn btn-secondary">
            Documentation
          </Link>
        </div>
        <div className="pill-row" style={{ justifyContent: 'center', marginTop: 'var(--space-5)' }}>
          {PRIMARY_NAV.filter((link) => link.to !== '/').map((link) => (
            <Link key={link.to} to={link.to} className="pill" style={{ display: 'inline-block' }}>
              {link.label}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}

export default NotFoundPage;
