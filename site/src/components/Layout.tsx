import type { ReactNode } from 'react';
import { Reveal } from './Reveal';

interface LayoutProps {
  children: ReactNode;
}

/** Page shell: skip link lives in Header; this wraps content for the router. */
export function Layout({ children }: LayoutProps) {
  return <>{children}</>;
}

interface SectionProps {
  children: ReactNode;
  id?: string;
  className?: string;
  alt?: boolean;
  labelledBy?: string;
}

export function Section({ children, id, className = '', alt, labelledBy }: SectionProps) {
  return (
    <section
      id={id}
      aria-labelledby={labelledBy}
      className={`section${alt ? ' section-alt' : ''}${className ? ` ${className}` : ''}`}
    >
      <div className="container">{children}</div>
    </section>
  );
}

interface SectionHeadProps {
  eyebrow?: string;
  title: string;
  lead?: string;
  sub?: string;
  center?: boolean;
  id?: string;
}

export function SectionHead({ eyebrow, title, lead, sub, center, id }: SectionHeadProps) {
  return (
    <Reveal>
      <div className={`section-head${center ? ' center' : ''}`}>
        {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
        <h2 id={id}>{title}</h2>
        {lead ? <p className="section-lead">{lead}</p> : null}
        {sub ? <p className="sub">{sub}</p> : null}
      </div>
    </Reveal>
  );
}

export default Layout;
