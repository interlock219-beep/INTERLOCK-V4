import type { Block } from '../docs/content';

export type BlogCategory = 'Engineering' | 'Safety' | 'Project';

export interface BlogArticle {
  slug: string;
  title: string;
  summary: string;
  category: BlogCategory;
  date: string;
  blocks: Block[];
}

export const BLOG_CATEGORIES: BlogCategory[] = ['Engineering', 'Safety', 'Project'];

function plain(blocks: Block[]): string {
  const parts: string[] = [];
  blocks.forEach((block) => {
    switch (block.kind) {
      case 'p':
      case 'h2':
      case 'h3':
        parts.push(block.text);
        break;
      case 'ul':
      case 'ol':
        parts.push(...block.items);
        break;
      case 'callout':
        parts.push(block.title ?? '', block.text);
        break;
      case 'code':
        parts.push(block.code);
        break;
      case 'table':
        parts.push(...block.head, ...block.rows.flat());
        break;
      default:
        break;
    }
  });
  return parts.join(' ');
}

/** Reading time calculated from the article's actual content (~200 wpm). */
export function readingTime(article: BlogArticle): number {
  const words = `${article.title} ${article.summary} ${plain(article.blocks)}`
    .split(/\s+/)
    .filter(Boolean).length;
  return Math.max(1, Math.round(words / 200));
}

export function articleText(article: BlogArticle): string {
  return `${article.title} ${article.summary} ${plain(article.blocks)}`.toLowerCase();
}

export const ARTICLES: BlogArticle[] = [
  {
    slug: 'what-agent-recovery-actually-means',
    title: 'What AI agent recovery actually means',
    summary:
      'Recovery is not “undo”. It is evidence capture, a gated plan, an atomic restore and an independent check — in that order.',
    category: 'Engineering',
    date: '2026-10-18',
    blocks: [
      {
        kind: 'p',
        text: 'The word “rollback” hides most of the difficulty. Anyone can write a file twice; the hard part is knowing what the file used to be, knowing whether that is still what you want, and proving afterwards that you got it.',
      },
      { kind: 'h2', id: 'evidence', text: '1. Evidence comes before the action' },
      {
        kind: 'p',
        text: 'A recovery system that starts thinking at the moment of failure is already too late. Interlock records a before-snapshot — content hash, size, timestamps, mode — while the action is still being authorised. If the snapshot does not exist, there is nothing to restore, and the honest answer is refusal rather than a plausible guess.',
      },
      {
        kind: 'callout',
        type: 'info',
        title: 'Evidence-driven, not predictive',
        text: 'You cannot recover what you never observed. This is the single most important limitation of the design, and it is why “missing pre-action evidence” is a hard refusal instead of a warning.',
      },
      { kind: 'h2', id: 'gate', text: '2. The plan is gated, not trusted' },
      {
        kind: 'p',
        text: 'Between analysis and execution sits a gate that a human opens deliberately. Preconditions are evaluated here: is the path inside the confinement boundary, does evidence exist for every target, does the current content still match what the plan expects? Any failure stops the run before a single byte is written.',
      },
      { kind: 'h2', id: 'atomic', text: '3. The restore is atomic by construction' },
      {
        kind: 'p',
        text: 'Content is written to a staging file created in the target directory, then swapped with `os.replace`. Because staging shares the target’s volume, a cross-device move cannot happen by construction, and an interruption leaves a staging file rather than half-written content at your target.',
      },
      { kind: 'h2', id: 'verify', text: '4. Verification decides the outcome' },
      {
        kind: 'p',
        text: 'The result is computed, not announced. Bytes are re-read, digests recomputed, and the comparison decides whether the run is a success. Every other outcome — conflict, refusal, interruption, mismatch — must be reported as exactly what it is.',
      },
      {
        kind: 'callout',
        type: 'tip',
        title: 'Try it in the browser',
        text: 'The [interactive demo](/demo) walks the same four stages over fictional files, including the cases that must not end in success.',
      },
    ],
  },
  {
    slug: 'verification-beats-confidence',
    title: 'Verification beats confidence',
    summary:
      'A recovery tool that reports success because it did not throw is guessing. Here is what an honest check looks like.',
    category: 'Safety',
    date: '2026-10-12',
    blocks: [
      {
        kind: 'p',
        text: 'Most failures in automated recovery are quiet: the operation returned without an exception, the log line was green, and the file was subtly wrong. Confidence is cheap. Verification costs a re-read and a hash — and it is the only thing that converts “we ran it” into “we know the state”.',
      },
      { kind: 'h2', id: 'independent', text: 'The check must be independent' },
      {
        kind: 'ul',
        items: [
          'The component that performed the write must not be the only component that confirms it.',
          'Digests are recomputed from the bytes on disk, not copied from the writer’s own bookkeeping.',
          'A mismatch is a typed failure with evidence preserved — never a warning buried in a log.',
          'Your own `sha256sum` or `Get-FileHash` should reproduce the result. If it cannot, that is the bug.',
        ],
      },
      { kind: 'h2', id: 'partial', text: 'Partial work must look partial' },
      {
        kind: 'p',
        text: 'Interruption is the case that catches teams out. If a workflow stops halfway, the interface has to say “incomplete”, not “done”. In the demo, the interrupted scenario deliberately lets you verify before resuming — the check fails, the state stays incomplete, and success only appears after a resume followed by a passing comparison.',
      },
      {
        kind: 'callout',
        type: 'warn',
        title: 'Simulation limits',
        text: 'The browser demo proves nothing about real crash recovery. The evidence for that is a real process-kill drill — 20 runs on Windows with zero torn writes — which is a Windows result and nothing more.',
      },
      { kind: 'h2', id: 'refusals', text: 'Refusals are results too' },
      {
        kind: 'p',
        text: '`blocked_by_conflict` and refusal states carry information: a human edit was preserved, or an unsafe precondition could not be proven. A reporting system that treats anything short of success as failure will push operators to disable the very checks protecting them.',
      },
    ],
  },
  {
    slug: 'conflict-detection-says-no',
    title: 'Conflict detection: the part that says no',
    summary:
      'The most valuable behaviour in a recovery tool is refusing to overwrite the fix a human applied after the agent broke things.',
    category: 'Safety',
    date: '2026-10-05',
    blocks: [
      {
        kind: 'p',
        text: 'Agent incidents are rarely discovered instantly. Between the mistake and the recovery there is almost always a human edit — a hotfix, a config tweak, a comment explaining what went wrong. A recovery tool that blindly restores the pre-incident bytes destroys that work.',
      },
      { kind: 'h2', id: 'drift', text: 'Drift is a first-class signal' },
      {
        kind: 'p',
        text: 'Before the atomic swap, current bytes are compared against the state the plan expects. If they differ, the restore for that file is skipped and the run reports `blocked_by_conflict`. Nothing is written, nothing is reverted, and the human decision remains possible.',
      },
      { kind: 'h2', id: 'duplicate', text: 'The same rule handles duplicates' },
      {
        kind: 'p',
        text: 'Idempotency keys give the same protection to replays: a duplicate delivery of the same compensation is refused rather than applied twice. Both cases are the same principle — do not act when the world has moved on from your assumption.',
      },
      { kind: 'h2', id: 'honesty', text: 'Being honest about the window' },
      {
        kind: 'p',
        text: 'There is a micro-second window between the existence check and the swap. Interlock documents it instead of pretending it away: the design assumes a single writer, concurrent-writer behaviour is mocked in tests, and the limitation appears in the support matrix rather than being quietly omitted.',
      },
      {
        kind: 'callout',
        type: 'tip',
        title: 'See it happen',
        text: 'Scenario B of the [interactive demo](/demo) blocks recovery mid-workflow and forces a review or reset — it cannot reach a success state while the conflict stands.',
      },
    ],
  },
  {
    slug: 'where-interlock-stands',
    title: 'Where Interlock V6 stands today',
    summary:
      'A plain status read of the release-readiness evidence: what is tested, what is declared, and what is openly not ready.',
    category: 'Project',
    date: '2026-10-18',
    blocks: [
      {
        kind: 'p',
        text: 'Projects lose credibility the moment their status page is optimistic. This is the current position of Interlock V6, taken directly from the release-readiness report and the support matrix rather than from a marketing brief.',
      },
      { kind: 'h2', id: 'ready', text: 'What is ready' },
      {
        kind: 'ul',
        items: [
          'Controlled beta on consenting volunteers using disposable projects, Windows x64, Python 3.11.9, offline.',
          'A full-suite record of 2922 passed tests with 83.81% coverage.',
          'Real failure evidence: 20/20 hard process-kill drills, real permission-denial drill, conflict and refusal paths.',
          'A wheel build verified to install in a clean environment with a byte-exact restore smoke test.',
        ],
      },
      { kind: 'h2', id: 'pending', text: 'What is pending' },
      {
        kind: 'ul',
        items: [
          'Native macOS and Linux validation — declared in the CI matrix, never executed.',
          'The real disk-full drill — procedure prepared, authorisation not granted. Mocked ENOSPC is not a pass.',
          'Cross-platform CI evidence — workflows exist but their results are not yet part of the record.',
        ],
      },
      { kind: 'h2', id: 'not-ready', text: 'What is openly not ready' },
      {
        kind: 'ul',
        items: [
          'General availability: blocked on the items above plus an external audit and an operational runbook.',
          'Paid beta: no customer-demand evidence, no terms, no privacy or refund policy, no support apparatus.',
          'Database and migration recovery: known defects, out of scope by prohibition.',
        ],
      },
      {
        kind: 'callout',
        type: 'warn',
        title: 'What this site does not claim',
        text: 'No customer counts, downloads, revenue, success rates, tokens processed, performance benchmarks, certifications, testimonials or star counts appear anywhere here — because none exist to cite.',
      },
      { kind: 'h2', id: 'next', text: 'The honest next steps' },
      {
        kind: 'ol',
        items: [
          'Run the cross-platform CI matrix so POSIX evidence stops being declared and starts being recorded.',
          'Execute the disk-full drill behind its authorisation gate.',
          'Send the invitation package to the first independent testers and listen to what they report.',
        ],
      },
      {
        kind: 'p',
        text: 'Want to be one of those testers? The [beta page](/beta) describes exactly what is involved, including the stop conditions and the privacy boundaries.',
      },
    ],
  },
];

export function getArticle(slug: string | undefined): BlogArticle | undefined {
  return ARTICLES.find((article) => article.slug === slug);
}
