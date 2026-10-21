import { useState, type ReactNode } from 'react';
import { Icon } from './Icon';

interface CodeBlockProps {
  code: string;
  language?: string;
  filename?: string;
  caption?: ReactNode;
  copyable?: boolean;
}

async function writeClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through to the textarea fallback */
  }
  try {
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(area);
    return ok;
  } catch {
    return false;
  }
}

export function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle');

  return (
    <button
      type="button"
      className="copy-btn"
      onClick={() => {
        void writeClipboard(text).then((ok) => {
          setState(ok ? 'copied' : 'failed');
          window.setTimeout(() => setState('idle'), 2200);
        });
      }}
    >
      {state === 'copied' ? 'Copied' : state === 'failed' ? 'Copy failed' : label}
    </button>
  );
}

export function CodeBlock({ code, language, filename, caption, copyable = true }: CodeBlockProps) {
  return (
    <div className="code-block">
      <div className="code-head">
        <span>{filename ?? language ?? 'code'}</span>
        {copyable ? <CopyButton text={code} /> : null}
      </div>
      <pre className="code-body" tabIndex={0}>
        <code>{code}</code>
      </pre>
      {caption ? <div className="code-head">{caption}</div> : null}
    </div>
  );
}

interface TerminalProps {
  title?: string;
  lines: { kind: 'prompt' | 'out' | 'ok' | 'warn'; text: string }[];
}

export function Terminal({ title = 'interlock — zsh', lines }: TerminalProps) {
  const plain = lines
    .map((line) => (line.kind === 'prompt' ? `$ ${line.text}` : line.text))
    .join('\n');

  return (
    <div className="terminal">
      <div className="terminal-bar">
        <span className="terminal-dot" />
        <span className="terminal-dot" />
        <span className="terminal-dot" />
        <span className="terminal-title">{title}</span>
        <span style={{ marginLeft: 'auto' }}>
          <CopyButton text={plain} label="Copy all" />
        </span>
      </div>
      <div className="terminal-body">
        {lines.map((line, index) => (
          <div
            key={`${index}-${line.text.slice(0, 12)}`}
            className={`term-line ${
              line.kind === 'prompt'
                ? 'term-prompt'
                : line.kind === 'ok'
                  ? 'term-ok'
                  : line.kind === 'warn'
                    ? 'term-warn'
                    : 'term-out'
            }`}
          >
            {line.kind === 'prompt' ? `$ ${line.text}` : line.text}
          </div>
        ))}
      </div>
    </div>
  );
}

interface CalloutProps {
  type?: 'info' | 'warn' | 'danger' | 'tip';
  title?: string;
  children: ReactNode;
}

const CALLOUT_ICON = {
  info: 'info',
  warn: 'alert',
  danger: 'shield-x',
  tip: 'check-circle',
} as const;

export function Callout({ type = 'info', title, children }: CalloutProps) {
  return (
    <div className={`callout callout-${type}`} role={type === 'danger' ? 'alert' : undefined}>
      <Icon name={CALLOUT_ICON[type]} style={{ flex: 'none', marginTop: 2, color: 'inherit' }} />
      <div>
        {title ? <strong className="callout-title">{title}</strong> : null}
        {children}
      </div>
    </div>
  );
}

export default CodeBlock;
