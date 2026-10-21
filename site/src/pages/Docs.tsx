import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { usePageMeta } from '../components/PageMeta';
import { Icon } from '../components/Icon';
import { renderBlock } from '../components/BlockRenderer';
import { DOCS, DOC_GROUPS, docPlainText, getDoc, type Block } from '../docs/content';

export function DocsPage() {
  const { slug } = useParams();
  const doc = getDoc(slug);
  const [query, setQuery] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [activeHeading, setActiveHeading] = useState<string | null>(null);

  const searchable = useMemo(
    () => DOCS.map((entry) => ({ slug: entry.slug, text: docPlainText(entry) })),
    [],
  );

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return null;
    return searchable.filter((entry) => entry.text.includes(q)).map((entry) => entry.slug);
  }, [query, searchable]);

  const headings = useMemo(
    () => (doc ? doc.blocks.filter((block): block is Extract<Block, { kind: 'h2' }> => block.kind === 'h2') : []),
    [doc],
  );

  const index = doc ? DOCS.findIndex((entry) => entry.slug === doc.slug) : -1;
  const prev = index > 0 ? DOCS[index - 1] : null;
  const next = index >= 0 && index < DOCS.length - 1 ? DOCS[index + 1] : null;

  usePageMeta({
    title: doc ? `${doc.title} — Interlock V6 docs` : 'Documentation — Interlock V6',
    description: doc
      ? doc.summary
      : 'Interlock V6 documentation: installation, recovery model, verification, conflict handling, safety, limitations, troubleshooting and platform status.',
  });

  // Scroll-spy for the table of contents.
  useEffect(() => {
    if (!doc || headings.length === 0 || typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (visible) setActiveHeading(visible.target.id);
      },
      { rootMargin: '-80px 0px -70% 0px' },
    );
    headings.forEach((heading) => {
      const node = document.getElementById(heading.id);
      if (node) observer.observe(node);
    });
    return () => observer.disconnect();
  }, [doc, headings]);

  return (
    <div className="container" style={{ paddingBlock: 'var(--space-6)' }}>
      <div className="docs-layout">
        {/* ---------------- sidebar ---------------- */}
        <div className={`docs-sidebar${sidebarOpen ? ' open' : ''}`}>
          <button
            type="button"
            className="btn btn-secondary docs-mobile-toggle"
            aria-expanded={sidebarOpen}
            onClick={() => setSidebarOpen((value) => !value)}
          >
            <Icon name="menu" /> {sidebarOpen ? 'Hide documentation menu' : 'Browse documentation'}
          </button>

          <label className="sr-only" htmlFor="docs-search">
            Search documentation
          </label>
          <input
            id="docs-search"
            className="docs-search"
            type="search"
            placeholder="Search docs…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />

          {results ? (
            <div className="docs-search-results">
              <p className="faint small">
                {results.length} result{results.length === 1 ? '' : 's'} for “{query}”
              </p>
              {results.length === 0 ? (
                <p className="small mb-0">
                  Nothing matched. Try “recovery”, “verification”, “install” or “conflict”.
                </p>
              ) : (
                <ul className="footer-links" style={{ margin: 0 }}>
                  {results.map((slugResult) => {
                    const entry = DOCS.find((item) => item.slug === slugResult);
                    return (
                      <li key={slugResult}>
                        <Link to={`/docs/${slugResult}`}>{entry?.title ?? slugResult}</Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          ) : null}

          {DOC_GROUPS.map((group) => (
            <div className="docs-group" key={group}>
              <h4>{group}</h4>
              {DOCS.filter((entry) => entry.group === group).map((entry) => (
                <Link
                  key={entry.slug}
                  to={`/docs/${entry.slug}`}
                  className={`docs-link${entry.slug === doc?.slug ? ' active' : ''}`}
                  aria-current={entry.slug === doc?.slug ? 'page' : undefined}
                >
                  {entry.title}
                </Link>
              ))}
            </div>
          ))}
        </div>

        {/* ---------------- article ---------------- */}
        <article className="docs-article">
          {!slug ? (
            <>
              <h1>Documentation</h1>
              <p className="section-lead" style={{ fontSize: 'var(--text-base)' }}>
                Twelve articles written against the code, not around it. Every command here was
                checked against the repository before it was published. Start with the
                introduction, or search the sidebar.
              </p>
              {DOC_GROUPS.map((group) => (
                <section key={group} className="docs-index-group">
                  <h2>{group}</h2>
                  <ul className="docs-index-list">
                    {DOCS.filter((entry) => entry.group === group).map((entry) => (
                      <li key={entry.slug}>
                        <Link to={`/docs/${entry.slug}`}>{entry.title}</Link>
                        <p className="faint small mb-0">{entry.summary}</p>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </>
          ) : doc ? (
            <>
              <p className="breadcrumbs">
                <Link to="/docs">Docs</Link> / {doc.group} / {doc.title}
              </p>
              <h1>{doc.title}</h1>
              <p className="section-lead" style={{ fontSize: 'var(--text-base)' }}>
                {doc.summary}
              </p>

              {doc.blocks.map(renderBlock)}

              <nav className="docs-pager" aria-label="Documentation pagination">
                {prev ? (
                  <Link to={`/docs/${prev.slug}`}>
                    <span className="dir">← Previous</span>
                    <span className="ttl">{prev.title}</span>
                  </Link>
                ) : (
                  <span />
                )}
                {next ? (
                  <Link to={`/docs/${next.slug}`} className="next">
                    <span className="dir">Next →</span>
                    <span className="ttl">{next.title}</span>
                  </Link>
                ) : null}
              </nav>
            </>
          ) : (
            <div className="empty-state">
              <h1>Document not found</h1>
              <p>
                There is no documentation page at <code>/docs/{slug}</code>.
              </p>
              <Link to="/docs/introduction" className="btn btn-primary">
                Go to the introduction
              </Link>
            </div>
          )}
        </article>

        {/* ---------------- table of contents ---------------- */}
        <aside className="docs-toc" aria-label="On this page">
          {headings.length > 0 ? (
            <>
              <h2>On this page</h2>
              {headings.map((heading) => (
                <a
                  key={heading.id}
                  href={`#${heading.id}`}
                  className={activeHeading === heading.id ? 'active' : undefined}
                >
                  {heading.text}
                </a>
              ))}
              <div style={{ marginTop: 'var(--space-5)' }}>
                <h2>Related</h2>
                <Link to="/docs/safety-model" className="docs-link">
                  Safety model
                </Link>
                <Link to="/docs/limitations" className="docs-link">
                  Limitations
                </Link>
                <Link to="/download" className="docs-link">
                  Install guide
                </Link>
              </div>
            </>
          ) : null}
        </aside>
      </div>
    </div>
  );
}

export default DocsPage;
