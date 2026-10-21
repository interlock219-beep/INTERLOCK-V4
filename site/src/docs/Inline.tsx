import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

const TOKEN = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;

/**
 * Renders a tiny, safe inline markup subset (`**bold**`, `` `code` ``,
 * `[label](/target)`) as React nodes. No `dangerouslySetInnerHTML`, so
 * content strings can never inject markup.
 */
export function Inline({ text }: { text: string }): ReactNode[] {
  const parts = text.split(TOKEN).filter((part) => part.length > 0);

  return parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return <code key={index}>{part.slice(1, -1)}</code>;
    }
    const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part);
    if (link) {
      const [, label, href] = link;
      if (href.startsWith('/')) {
        return (
          <Link key={index} to={href}>
            {label}
          </Link>
        );
      }
      return (
        <a key={index} href={href} target="_blank" rel="noopener noreferrer">
          {label}
        </a>
      );
    }
    return <span key={index}>{part}</span>;
  });
}

export default Inline;
