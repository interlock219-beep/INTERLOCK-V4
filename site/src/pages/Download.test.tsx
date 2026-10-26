import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { DownloadPage } from './Download';
import { CopyButton } from '../components/CodeBlock';
import { SITE } from '../data/site';

function renderPage() {
  return render(
    <MemoryRouter>
      <DownloadPage />
    </MemoryRouter>,
  );
}

const hrefs = () =>
  Array.from(document.querySelectorAll('a[href]')).map((a) => a.getAttribute('href'));

afterEach(() => {
  Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
});

describe('Install page — two-workflow installation experience', () => {
  it('renders the prescribed workflow section copy and both option cards', () => {
    renderPage();

    expect(screen.getByText('CHOOSE YOUR WORKFLOW')).toBeTruthy();
    expect(
      screen.getByRole('heading', { level: 2, name: 'One engine. Two ways to work.' }),
    ).toBeTruthy();
    expect(
      screen.getByText('Use Interlock inside VS Code or run it directly from your terminal.'),
    ).toBeTruthy();
    expect(document.body.textContent).toContain(
      'Both interfaces are designed to use the same underlying Interlock engine.',
    );

    expect(
      screen.getByRole('heading', { level: 3, name: 'Install for VS Code' }),
    ).toBeTruthy();
    expect(screen.getByRole('heading', { level: 3, name: 'Run in Terminal' })).toBeTruthy();
    expect(
      screen.getByText('Bring Interlock into your development workflow.'),
    ).toBeTruthy();
    expect(
      screen.getByText('Use Interlock directly from your command line.'),
    ).toBeTruthy();

    const cardTitles = Array.from(document.querySelectorAll('.wf-card h3')).map(
      (node) => node.textContent,
    );
    expect(cardTitles).toEqual(['Install for VS Code', 'Run in Terminal']);
  });

  it('no longer renders the OS-specific installation cards or their CTAs', () => {
    renderPage();

    expect(screen.queryByText('Install on Windows')).toBeNull();
    expect(screen.queryByRole('link', { name: /Install on Windows/ })).toBeNull();
    expect(screen.queryByText('Join the POSIX beta slot')).toBeNull();
    expect(screen.queryByText('Operating-system compatibility')).toBeNull();
    expect(screen.queryByText('Install for Windows')).toBeNull();
    expect(screen.queryByText('Install for macOS')).toBeNull();
    expect(screen.queryByText('Install for Linux')).toBeNull();
    expect(screen.queryByText('Download for Windows')).toBeNull();
    expect(screen.queryByText('Download for macOS')).toBeNull();
    expect(screen.queryByText('Download for Linux')).toBeNull();

    // Compatibility truth is still on the page (not hidden by the redesign).
    expect(document.body.textContent).toContain('Validation in progress');
    expect(document.body.textContent).toContain('macOS and Linux have not completed native validation');
    expect(document.body.textContent).toContain('Compatibility status');
  });

  it('shows the published VS Code extension state with a real Marketplace link', () => {
    renderPage();

    const cta = screen.getAllByRole('link', { name: 'Install from VS Code Marketplace' })[0];
    expect(cta.getAttribute('href')).toBe(SITE.vscodeMarketplaceUrl);

    expect(document.body.textContent).toContain('Published on the VS Code Marketplace');
    expect(document.body.textContent).toContain('interlock.interlock-vscode');
    expect(document.body.textContent).not.toMatch(/installed successfully|installation complete/i);

    // A VSIX installer is also offered for manual installation.
    const vsix = screen.getAllByRole('link', { name: /Download VSIX Installer/i });
    expect(vsix.length).toBeGreaterThan(0);

    // No invented or placeholder download destinations.
    expect(hrefs().filter((h) => h === '#' || h === '')).toHaveLength(0);
  });

  it('gives both cards functional primary and secondary destinations', () => {
    renderPage();

    const vsInstructions = screen.getByRole('link', { name: /View installation instructions/ });
    expect(vsInstructions.getAttribute('href')).toBe('#install-vscode');

    const terminalPrimary = screen.getByRole('link', { name: 'View Terminal Instructions' });
    expect(terminalPrimary.getAttribute('href')).toBe('#install-terminal');

    const cliDocs = screen.getByRole('link', { name: /View CLI documentation/ });
    expect(cliDocs.getAttribute('href')).toBe('/docs/cli-api');

    // Instruction targets really exist on this page.
    expect(document.getElementById('install-vscode')).toBeTruthy();
    expect(document.getElementById('install-terminal')).toBeTruthy();
  });

  it('links the compatibility note to the real compatibility guide', () => {
    renderPage();

    expect(document.body.textContent).toContain(
      'Platform support depends on the validated engine, dependencies, and installation method.',
    );
    const link = screen.getByRole('link', { name: 'See the compatibility guide' });
    expect(link.getAttribute('href')).toBe('/docs/supported-platforms');
  });

  it('documents both methods, separating validated from pending instructions', () => {
    renderPage();

    expect(screen.getByRole('heading', { level: 2, name: 'Install for VS Code.' })).toBeTruthy();
    expect(screen.getByRole('heading', { level: 2, name: 'Install for Terminal.' })).toBeTruthy();
    expect(document.body.textContent).toContain('Validated today');
    expect(document.body.textContent).toContain('Pending validation');
    expect(document.body.textContent).toContain('Common dependency errors');
    // Real package name + no invented console binary.
    expect(document.body.textContent).toContain('intentlock');
    expect(document.body.textContent).toContain('pip install -e ".[dev,security]"');
  });
});

describe('Copy behaviour for install commands', () => {
  it('reports success only after the clipboard write succeeds', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    });

    render(<CopyButton text="pip install -e '.[dev,security]'" />);
    const button = screen.getByRole('button', { name: 'Copy' });

    expect(button.textContent).toBe('Copy');
    fireEvent.click(button);

    expect(await screen.findByRole('button', { name: 'Copied' })).toBeTruthy();
    expect(writeText).toHaveBeenCalledWith("pip install -e '.[dev,security]'");
  });

  it('does not claim success when clipboard access is unavailable', async () => {
    render(<CopyButton text="python -m pip check" />);
    const button = screen.getByRole('button', { name: 'Copy' });

    fireEvent.click(button);

    // jsdom has neither navigator.clipboard nor a working execCommand fallback.
    expect(await screen.findByRole('button', { name: 'Copy failed' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Copied' })).toBeNull();
  });
});
