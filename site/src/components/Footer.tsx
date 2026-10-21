import { Link } from 'react-router-dom';
import { Icon } from './Icon';
import { FOOTER_NAV, SITE } from '../data/site';

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="container">
        <div className="footer-grid">
          <div className="footer-brand">
            <Link to="/" className="brand">
              <Icon name="shield" className="brand-mark" />
              <span>INTERLOCK</span>
              <span className="brand-version">{SITE.version}</span>
            </Link>
            <p>
              Recovery and verification for AI agent changes. Undo what an agent broke, prove the
              result, and refuse anything unsafe — on supported, disposable projects.
            </p>
            <p className="faint small">
              {SITE.package} {SITE.packageVersion} · evidence verified {SITE.evidenceDate}
            </p>
          </div>

          {FOOTER_NAV.map((group) => (
            <div className="footer-col" key={group.title}>
              <h2>{group.title}</h2>
              <ul className="footer-links">
                {group.links.map((link) => (
                  <li key={link.to}>
                    <Link to={link.to}>{link.label}</Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="footer-bottom">
          <span>
            Interlock is in controlled beta. Not production-ready, not a substitute for your own
            backups.
          </span>
          <span>
            <a href={SITE.repoUrl} target="_blank" rel="noopener noreferrer">
              Source on GitHub
            </a>{' '}
            ·{' '}
            <a href={`${SITE.repoUrl}/security`} target="_blank" rel="noopener noreferrer">
              Security policy
            </a>{' '}
            · <Link to="/safety">Safety</Link>
          </span>
        </div>
      </div>
    </footer>
  );
}

export default Footer;
