import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { Icon } from './Icon';
import { PRIMARY_NAV, SITE } from '../data/site';

function isActive(pathname: string, to: string): boolean {
  if (to === '/') return pathname === '/';
  return pathname === to || pathname.startsWith(`${to}/`);
}

export function Header() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const toggleRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        toggleRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  return (
    <header className="site-header">
      <div className="container header-inner">
        <Link to="/" className="brand">
          <Icon name="shield" className="brand-mark" />
          <span>INTERLOCK</span>
          <span className="brand-version">{SITE.version}</span>
        </Link>

        <nav className="nav" aria-label="Primary">
          {PRIMARY_NAV.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.to === '/'}
              className={({ isActive: active }) => `nav-link${active ? ' active' : ''}`}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="header-actions">
          <a
            className="gh-link"
            href={SITE.repoUrl}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`GitHub repository ${SITE.repoLabel} (opens in a new tab)`}
          >
            <Icon name="github" width={17} height={17} />
            <span>GitHub</span>
          </a>
          <Link to="/beta" className="btn btn-primary btn-sm">
            Get Started <Icon name="arrow-right" />
          </Link>
          <button
            ref={toggleRef}
            type="button"
            className="mobile-toggle"
            aria-expanded={open}
            aria-controls="mobile-nav"
            onClick={() => setOpen((value) => !value)}
          >
            <Icon name={open ? 'x' : 'menu'} width={18} height={18} />
            {open ? 'Close' : 'Menu'}
          </button>
        </div>
      </div>

      <nav
        id="mobile-nav"
        className={`mobile-nav${open ? ' open' : ''}`}
        aria-label="Primary mobile"
        hidden={!open}
      >
        {PRIMARY_NAV.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.to === '/'}
            className={({ isActive: active }) => `nav-link${active ? ' active' : ''}`}
            aria-current={isActive(location.pathname, link.to) ? 'page' : undefined}
          >
            {link.label}
          </NavLink>
        ))}
        <Link to="/download" className="btn btn-primary">
          Get Started <Icon name="arrow-right" />
        </Link>
      </nav>
    </header>
  );
}

export default Header;
