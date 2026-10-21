import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { usePageMeta } from '../components/PageMeta';
import { Reveal } from '../components/Reveal';
import { Section, SectionHead } from '../components/Layout';
import { ARTICLES, BLOG_CATEGORIES, readingTime, type BlogCategory } from '../content/blog';

function formatDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00Z`);
  return date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

export function BlogPage() {
  const [category, setCategory] = useState<'All' | BlogCategory>('All');

  const filtered = useMemo(
    () => (category === 'All' ? ARTICLES : ARTICLES.filter((a) => a.category === category)),
    [category],
  );

  usePageMeta({
    title: 'Blog — Interlock V6',
    description:
      'Writing about AI-agent recovery, verification, conflict detection and the honest engineering status of Interlock V6.',
  });

  return (
    <>
      <div className="page-hero">
        <div className="container">
          <Reveal>
            <span className="eyebrow">Blog</span>
            <h1>Notes from the recovery engine.</h1>
            <p className="section-lead">
              Educational writing about agent safety and recovery, plus straightforward project
              status updates. No launch announcements, customer stories or security claims are
              invented here — there are none to tell.
            </p>
          </Reveal>
        </div>
      </div>

      <Section labelledBy="blog-title">
        <h2 id="blog-title" className="sr-only">
          Articles
        </h2>

        <div className="pill-row" role="group" aria-label="Filter articles by category" style={{ marginBottom: 'var(--space-5)' }}>
          {(['All', ...BLOG_CATEGORIES] as const).map((item) => (
            <button
              key={item}
              type="button"
              className="pill"
              aria-pressed={category === item}
              onClick={() => setCategory(item)}
            >
              {item}
            </button>
          ))}
        </div>

        {filtered.length === 0 ? (
          <div className="empty-state">
            <h3>No articles in this category yet</h3>
            <p className="mb-0">
              Nothing has been published under “{category}”. Try another filter, or read the{' '}
              <Link to="/docs">documentation</Link> instead.
            </p>
          </div>
        ) : (
          <div className="blog-grid">
            {filtered.map((article, index) => (
              <Reveal key={article.slug} delay={index * 60}>
                <Link to={`/blog/${article.slug}`} className="blog-card" style={{ height: '100%' }}>
                  <div className="blog-meta">
                    <span>{article.category}</span>
                    <span>{formatDate(article.date)}</span>
                    <span>{readingTime(article)} min read</span>
                  </div>
                  <h3>{article.title}</h3>
                  <p>{article.summary}</p>
                  <span className="read">
                    Read article →{/* inline arrow avoids an extra icon request */}
                  </span>
                </Link>
              </Reveal>
            ))}
          </div>
        )}
      </Section>

      <Section alt className="section-tight">
        <SectionHead
          eyebrow="Documentation"
          title="Want the technical detail?"
          lead="The documentation centre covers the same ground with commands you can run and limitations you can check."
        />
        <div className="row">
          <Link to="/docs" className="btn btn-primary">
            Open documentation
          </Link>
          <Link to="/safety" className="btn btn-secondary">
            Safety &amp; limitations
          </Link>
        </div>
      </Section>
    </>
  );
}

export default BlogPage;
