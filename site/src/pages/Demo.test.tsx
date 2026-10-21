import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { DemoPage } from './Demo';

function renderDemo() {
  return render(
    <MemoryRouter>
      <DemoPage />
    </MemoryRouter>,
  );
}

function press(label: string | RegExp) {
  fireEvent.click(screen.getByRole('button', { name: label }));
}

/** Runs the deterministic worker forward until it stops ticking. */
function runWorker(ms = 9000) {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
});

describe('Demo page — state transitions through the UI', () => {
  it('walks scenario A to a verified result', () => {
    renderDemo();

    press(/Start incident/i);
    press(/Review changes/i);
    press(/Preview recovery/i);
    press(/Request approval/i);

    expect(screen.getByText(/waiting for explicit approval/i)).toBeTruthy();

    press(/Approve and continue/i);
    runWorker();

    expect(screen.getByText('Recovery verified')).toBeTruthy();
    // The independent-verification log line is exact, so the report block below
    // (which embeds the same log as plain text) cannot satisfy this assertion.
    expect(
      screen.getByText(
        'Recovery successful: integrity verified against captured evidence, no residue.',
      ),
    ).toBeTruthy();
    expect(screen.getAllByText(/match/i).length).toBeGreaterThan(0);
  });

  it('blocks scenario B at the conflict and never reports success', () => {
    renderDemo();

    press(/File changed by a person/i);
    press(/Start incident/i);
    press(/Review changes/i);
    press(/Preview recovery/i);
    press(/Request approval/i);
    press(/Approve and continue/i);
    runWorker();

    expect(screen.getByText('Recovery blocked')).toBeTruthy();
    expect(screen.queryByText('Recovery verified')).toBeNull();
    expect(screen.queryByRole('button', { name: /Approve and continue/i })).toBeNull();

    // The user can open the conflict for review, but cannot force success.
    press(/Review conflict/i);
    expect(screen.getByRole('heading', { name: 'Conflict review open' })).toBeTruthy();
    expect(screen.queryByText('Recovery verified')).toBeNull();
  });

  it('refuses scenario C during planning and reports the refusal', () => {
    renderDemo();

    press(/Unsafe recovery request/i);
    press(/Start incident/i);
    press(/Review changes/i);
    press(/Preview recovery/i);

    expect(screen.getByText('Recovery blocked')).toBeTruthy();
    expect(screen.getByText('Stopped — a safety precondition failed.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Approve and continue/i })).toBeNull();
    expect(screen.getByRole('button', { name: /Reset simulation/i })).toBeTruthy();
  });

  it('marks scenario D incomplete until verification and resume finish', () => {
    renderDemo();

    press(/Recovery interrupted/i);
    press(/Start incident/i);
    press(/Review changes/i);
    press(/Preview recovery/i);
    press(/Request approval/i);
    press(/Approve and continue/i);
    runWorker();

    expect(screen.getByText('Recovery incomplete')).toBeTruthy();
    expect(screen.queryByText('Recovery verified')).toBeNull();

    // The honest order: verify the current state first, then resume.
    press(/Run verification/i);
    runWorker();
    expect(screen.getByText('Recovery incomplete')).toBeTruthy();
    expect(screen.queryByText('Recovery verified')).toBeNull();

    press(/Resume recovery/i);
    runWorker();
    expect(screen.getByText('Recovery verified')).toBeTruthy();
  });

  it('resets to an idle walkthrough with no stale results', () => {
    renderDemo();

    press(/Start incident/i);
    press(/Reset simulation/i);

    expect(screen.getByRole('heading', { name: 'Nothing has happened yet' })).toBeTruthy();
    expect(screen.getByText(/No analysis yet/i)).toBeTruthy();
    expect(screen.queryByText('Recovery verified')).toBeNull();
  });

  it('switching scenarios mid-run clears every result and event', () => {
    renderDemo();

    press(/Start incident/i);
    press(/Review changes/i);
    press(/Preview recovery/i);
    press(/Request approval/i);
    press(/Approve and continue/i);
    runWorker();

    expect(screen.getByText('Recovery verified')).toBeTruthy();

    press(/Unsafe recovery request/i);

    expect(screen.getByRole('heading', { name: 'Nothing has happened yet' })).toBeTruthy();
    expect(screen.queryByText('Recovery verified')).toBeNull();

    const messages = Array.from(document.querySelectorAll('.log-line .msg'));
    expect(messages.filter((el) => el.textContent?.includes('Scenario loaded')).length).toBe(1);
  });
});

describe('Demo page — calm, guided walkthrough', () => {
  it('keeps the fictional-data warning visible and the scenario list in plain words', () => {
    renderDemo();

    expect(document.querySelector('.demo-banner')?.textContent).toMatch(
      /no real files modified/i,
    );
    for (const title of [
      'Successful recovery',
      'File changed by a person',
      'Unsafe recovery request',
      'Recovery interrupted',
    ]) {
      expect(screen.getByRole('button', { name: new RegExp(title) })).toBeTruthy();
    }
  });

  it('shows the workflow as six steps with exactly one current step', () => {
    renderDemo();

    expect(document.querySelectorAll('.phase-step').length).toBe(6);
    press(/Start incident/i);

    const current = document.querySelectorAll('.phase-step.current');
    expect(current.length).toBe(1);
    expect(current[0].textContent).toContain('Review');
  });

  it('gives each step one main task and one main action that explains itself', () => {
    renderDemo();
    press(/Start incident/i);

    expect(screen.getByRole('heading', { name: 'Incident detected' })).toBeTruthy();
    const main = document.querySelectorAll(
      '.demo-actions .btn-primary, .demo-actions .btn-secondary',
    );
    expect(main.length).toBe(1);
    expect(screen.getByRole('button', { name: /Review changes/ })).toBeTruthy();
    expect(screen.getByText(/Classify each fictional file by risk/)).toBeTruthy();
  });

  it('never shows a result before the workflow actually ends', () => {
    renderDemo();

    expect(document.querySelector('.outcome')).toBeNull();
    press(/Start incident/i);
    expect(document.querySelector('.outcome')).toBeNull();
    press(/Review changes/i);
    expect(document.querySelector('.outcome')).toBeNull();
    press(/Preview recovery/i);
    expect(document.querySelector('.outcome')).toBeNull();
  });

  it('states the approval requirement before anything can run', () => {
    renderDemo();

    press(/Start incident/i);
    press(/Review changes/i);
    press(/Preview recovery/i);
    press(/Request approval/i);

    expect(
      screen.getByText(/Explicit approval is required before any restore operation runs/i),
    ).toBeTruthy();

    // Withholding approval leaves every file untouched and claims no result.
    press(/Don't approve/);
    expect(document.querySelector('.outcome')).toBeNull();
    expect(screen.getByRole('heading', { name: 'Recovery ready to preview' })).toBeTruthy();
  });

  it('keeps the advanced detail collapsed until it is asked for', () => {
    renderDemo();

    const details = document.querySelector('details.demo-details') as HTMLDetailsElement | null;
    expect(details).toBeTruthy();
    expect(details?.open).toBe(false);

    // The technical evidence still exists inside it, labelled for assistive tech.
    expect(details?.querySelector('[role="log"][aria-label="Simulated event log"]')).toBeTruthy();
    expect(details?.textContent).toContain('No analysis yet');

    // Asking for it opens the detail without touching the simulation.
    fireEvent.click(screen.getByText('View technical details'));
    expect(details?.open).toBe(true);
  });
});
