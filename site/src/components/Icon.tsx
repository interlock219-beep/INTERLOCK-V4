import type { SVGProps } from 'react';

export type IconName =
  | 'shield'
  | 'shield-check'
  | 'shield-x'
  | 'rotate'
  | 'check'
  | 'check-circle'
  | 'x'
  | 'x-circle'
  | 'alert'
  | 'info'
  | 'arrow-right'
  | 'arrow-left'
  | 'chevron-down'
  | 'menu'
  | 'copy'
  | 'refresh'
  | 'play'
  | 'terminal'
  | 'code'
  | 'branch'
  | 'globe'
  | 'lock'
  | 'file'
  | 'folder'
  | 'clock'
  | 'github'
  | 'windows'
  | 'apple'
  | 'linux'
  | 'search'
  | 'book'
  | 'download'
  | 'spark'
  | 'database'
  | 'eye'
  | 'vscode';

const STROKE_PATHS: Record<string, string> = {
  shield: 'M12 3l7.5 3.2v5.1c0 4.4-3 7.6-7.5 9-4.5-1.4-7.5-4.6-7.5-9V6.2L12 3z',
  'shield-check': 'M12 3l7.5 3.2v5.1c0 4.4-3 7.6-7.5 9-4.5-1.4-7.5-4.6-7.5-9V6.2L12 3z M8.8 12.1l2.3 2.3 4.3-4.6',
  'shield-x': 'M12 3l7.5 3.2v5.1c0 4.4-3 7.6-7.5 9-4.5-1.4-7.5-4.6-7.5-9V6.2L12 3z M9.6 9.8l4.8 4.8 M14.4 9.8l-4.8 4.8',
  rotate: 'M4.5 12a7.5 7.5 0 1 0 2.2-5.3 M4 4.5v5h5',
  check: 'M5 12.6l4.6 4.6L19 7.5',
  'check-circle': 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M8 12.3l2.7 2.7L16 9.6',
  x: 'M6.5 6.5l11 11 M17.5 6.5l-11 11',
  'x-circle': 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M9.4 9.4l5.2 5.2 M14.6 9.4l-5.2 5.2',
  alert: 'M12 4.2L21 19.5H3L12 4.2z M12 10v4 M12 16.8h.01',
  info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 11v5 M12 7.8h.01',
  'arrow-right': 'M4.5 12h14 M13 6l6 6-6 6',
  'arrow-left': 'M19.5 12h-14 M11 6l-6 6 6 6',
  'chevron-down': 'M6 9.5l6 6 6-6',
  menu: 'M4 7h16 M4 12h16 M4 17h16',
  copy: 'M9 8.5h9.5V20H9z M5.5 15.5V4h9.5',
  refresh: 'M19.5 12a7.5 7.5 0 1 1-2.2-5.3 M20 4.5v5h-5',
  play: 'M8.5 5.8l10 6.2-10 6.2V5.8z',
  terminal: 'M5 6.5l5.5 5.5L5 17.5 M12.5 17.5h6.5',
  code: 'M9 6.5L3.5 12 9 17.5 M15 6.5L20.5 12 15 17.5',
  branch: 'M7 6.5v11 M7 8a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z M17 10.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z M17 10.5v1.5a4 4 0 0 1-4 4H7',
  globe: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M3.3 9.5h17.4 M3.3 14.5h17.4 M12 3c2.4 2.4 3.6 5.4 3.6 9S14.4 18.6 12 21c-2.4-2.4-3.6-5.4-3.6-9S9.6 5.4 12 3z',
  lock: 'M7.5 10.5V8a4.5 4.5 0 0 1 9 0v2.5 M5.5 10.5h13V20h-13z',
  file: 'M7 3.5h6.5L18 8v12.5H7z M13.5 3.5V8H18',
  folder: 'M3.5 6.5h5.2l2 2.2h9.8v10.8H3.5z',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 7.5V12l3.2 1.9',
  search: 'M10.8 18.2a7.4 7.4 0 1 0 0-14.8 7.4 7.4 0 0 0 0 14.8z M16.2 16.2L21 21',
  book: 'M4.5 5.2A2 2 0 0 1 6.5 4H19v14.5H6.9a2 2 0 0 0-2.4 1.5V5.2z M4.5 18.5a2 2 0 0 1 2-1.5H19',
  download: 'M12 4v10 M8 10.5l4 4 4-4 M4.5 19.5h15',
  spark: 'M12 3.5l1.9 4.9 4.9 1.9-4.9 1.9L12 17.1l-1.9-4.9L5.2 10.3l4.9-1.9L12 3.5z',
  database: 'M12 7.6c4.4 0 8-1.2 8-2.6S16.4 2.4 12 2.4 4 3.6 4 5s3.6 2.6 8 2.6z M4 5v14c0 1.4 3.6 2.6 8 2.6s8-1.2 8-2.6V5 M4 12c0 1.4 3.6 2.6 8 2.6s8-1.2 8-2.6',
  eye: 'M2.5 12S6 5.8 12 5.8 21.5 12 21.5 12 18 18.2 12 18.2 2.5 12 2.5 12z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  vscode: 'M4 5.5h16v13H4z M9.9 9.4L7.3 12l2.6 2.6 M12.9 15.4l3.5-6.8',
};

/** Filled glyphs (logos) use `fill`, everything else uses strokes. */
const FILLED_PATHS: Record<string, string> = {
  github:
    'M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12',
  windows:
    'M3 5.4l7.6-1v7.2H3V5.4zm8.7-1.2L21 3v8.6h-9.3V4.2zM3 12.8h7.6v7.1L3 18.7v-5.9zm8.7 0H21V21l-9.3-1.3v-6.9z',
  apple:
    'M16.4 12.7c0-2 1.6-3 1.7-3-1-1.4-2.4-1.6-2.9-1.6-1.3-.1-2.5.7-3.1.7-.6 0-1.6-.7-2.7-.7-1.4 0-2.7.8-3.4 2-1.5 2.5-.4 6.3 1 8.4.7 1 1.6 2.1 2.7 2.1 1.1 0 1.5-.7 2.8-.7s1.6.7 2.7.7c1.1 0 1.9-1 2.6-2 .8-1.2 1.1-2.3 1.1-2.4-.1 0-2.2-.8-2.2-3.5zM14.5 6.4c.6-.7 1-1.7.9-2.7-.9 0-2 .6-2.6 1.3-.6.6-1.1 1.6-.9 2.6 1 .1 2-.5 2.6-1.2z',
  linux:
    'M12 3.2c2.6 0 4.3 2.1 4.3 5 0 1.5.8 2.5 1.7 3.9.9 1.4 1.3 2.5 1.3 3.5 0 1.5-1.4 2.6-3.3 2.6-1.1 0-2.5-.4-4-.4s-2.9.4-4 .4c-1.9 0-3.3-1.1-3.3-2.6 0-1 .4-2.1 1.3-3.5.9-1.4 1.7-2.4 1.7-3.9 0-2.9 1.7-5 4.3-5zM10.4 8.3a.7.7 0 1 0 0-1.4.7.7 0 0 0 0 1.4zm3.2 0a.7.7 0 1 0 0-1.4.7.7 0 0 0 0 1.4zM12 9.9c1.4 0 2.6 1 3.1 2.4-1 .9-2 1.4-3.1 1.4s-2.1-.5-3.1-1.4c.5-1.4 1.7-2.4 3.1-2.4z',
};

export interface IconProps extends Omit<SVGProps<SVGSVGElement>, 'name'> {
  name: IconName;
  /** Accessible label; when omitted the icon is decorative (aria-hidden). */
  title?: string;
}

export function Icon({ name, title, width = 18, height = 18, ...rest }: IconProps) {
  const filled = FILLED_PATHS[name];
  const stroke = STROKE_PATHS[name];
  const decorative = title === undefined;

  return (
    <svg
      viewBox="0 0 24 24"
      className="icon"
      width={width}
      height={height}
      fill={filled ? 'currentColor' : 'none'}
      stroke={filled ? 'none' : 'currentColor'}
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={decorative ? 'presentation' : 'img'}
      aria-hidden={decorative || undefined}
      focusable="false"
      {...rest}
    >
      {title ? <title>{title}</title> : null}
      {filled ? <path d={filled} /> : <path d={stroke} />}
    </svg>
  );
}

export default Icon;
