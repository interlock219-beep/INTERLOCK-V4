/**
 * Structured output channel with secret-safe writes.
 *
 * Every line is redacted and size-capped before it reaches the channel, so
 * subprocess output, engine messages, and paths can never leak credentials
 * into the log.
 */

import * as vscode from 'vscode';
import { redact, truncate } from './redact';

const MAX_LINE_CHARS = 8000;

export class InterlockLog implements vscode.Disposable {
  private readonly channel: vscode.OutputChannel;

  constructor() {
    this.channel = vscode.window.createOutputChannel('Interlock');
  }

  private write(level: string, message: string): void {
    const stamp = new Date().toISOString();
    this.channel.appendLine(`[${stamp}] ${level} ${redact(truncate(message, MAX_LINE_CHARS))}`);
  }

  info(message: string): void {
    this.write('INFO ', message);
  }

  warn(message: string): void {
    this.write('WARN ', message);
  }

  error(message: string): void {
    this.write('ERROR', message);
  }

  /** Multi-line detail block (each line redacted and capped). */
  detail(label: string, body: string): void {
    this.write('INFO ', label);
    for (const line of truncate(body, MAX_LINE_CHARS * 4).split(/\r?\n/)) {
      this.channel.appendLine(`        ${redact(truncate(line, MAX_LINE_CHARS))}`);
    }
  }

  show(): void {
    this.channel.show(true);
  }

  dispose(): void {
    this.channel.dispose();
  }
}
