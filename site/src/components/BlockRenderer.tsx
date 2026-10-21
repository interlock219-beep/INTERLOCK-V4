import { Callout, CodeBlock } from './CodeBlock';
import type { Block } from '../docs/content';
import { Inline } from '../docs/Inline';

/** Renders a documentation/blog content block as safe React nodes. */
export function renderBlock(block: Block, index: number) {
  switch (block.kind) {
    case 'p':
      return (
        <p key={index}>
          <Inline text={block.text} />
        </p>
      );
    case 'h2':
      return (
        <h2 key={index} id={block.id}>
          {block.text}
        </h2>
      );
    case 'h3':
      return (
        <h3 key={index} id={block.id}>
          {block.text}
        </h3>
      );
    case 'ul':
      return (
        <ul key={index}>
          {block.items.map((item) => (
            <li key={item}>
              <Inline text={item} />
            </li>
          ))}
        </ul>
      );
    case 'ol':
      return (
        <ol key={index}>
          {block.items.map((item) => (
            <li key={item}>
              <Inline text={item} />
            </li>
          ))}
        </ol>
      );
    case 'code':
      return (
        <CodeBlock key={index} code={block.code} language={block.language} filename={block.filename} />
      );
    case 'callout':
      return (
        <Callout key={index} type={block.type} title={block.title}>
          <p>
            <Inline text={block.text} />
          </p>
        </Callout>
      );
    case 'table':
      return (
        <div className="code-block" key={index} style={{ padding: 0 }}>
          <div style={{ overflowX: 'auto' }}>
            <table className="risk-table" style={{ minWidth: '100%' }}>
              <thead>
                <tr>
                  {block.head.map((cell) => (
                    <th key={cell} scope="col">
                      {cell}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.rows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {row.map((cell, cellIndex) => (
                      <td key={cellIndex}>
                        <Inline text={cell} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      );
    default:
      return null;
  }
}

export default renderBlock;
