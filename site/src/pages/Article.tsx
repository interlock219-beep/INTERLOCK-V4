import { Link, useParams } from 'react-router-dom';
import { usePageMeta } from '../components/PageMeta';
import { Reveal } from '../components/Reveal';
import { Section } from '../components/Layout';
import { renderBlock } from '../components/BlockRenderer';
import { getArticle, readingTime } from '../content/blog';

function formatDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00Z`);
  return date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

export function ArticlePage() {
  const { slug } = useParams();
  const article = getArticle(slug);

  usePageMeta({
    title: article ? `${article.title} — Interlock V6 blog` : 'Article not found — Interlock V6',
    description: article?.summary ?? 'This blog article does not exist.',
  });

  if (!article) {
    return (
      <Section>
        <div className="empty-state">
          <h1>Article not found</h1>
          <p>
            There is no article at <code>/blog/{slug}</code>.
          </p>
          <Link to="/blog" className="btn btn-primary">
            Back to the blog
          </Link>
        </div>
      </Section>
    );
  }

  return (
    <>
      <div className="page-hero">
        <div className="container container-narrow">
          <Reveal>
            <p className="breadcrumbs">
              <Link to="/blog">Blog</Link> / {article.category}
            </p>
            <h1>{article.title}</h1>
            <div className="article-meta">
              <span>{article.category}</span>
              <span>{formatDate(article.date)}</span>
              <span>{readingTime(article)} min read</span>
            </div>
            <p className="section-lead" style={{ fontSize: 'var(--text-base)' }}>
              {article.summary}
            </p>
          </Reveal>
        </div>
      </div>

      <Section>
        <div className="container-narrow" style={{ marginInline: 0 }}>
          <div className="article-body">{article.blocks.map(renderBlock)}</div>

          <div className="docs-pager">
            <Link to="/blog">
              <span className="dir">← Back</span>
              <span className="ttl">All articles</span>
            </Link>
            <Link to="/docs" className="next">
              <span className="dir">Docs →</span>
              <span className="ttl">Documentation centre</span>
            </Link>
          </div>
        </div>
      </Section>
    </>
  );
}

export default ArticlePage;
