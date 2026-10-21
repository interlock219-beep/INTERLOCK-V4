import * as assert from 'assert';
import { platformVerdict, statusLabel } from '../../src/platform';

describe('platform compatibility (extension vs engine)', () => {
  it('reports Windows x64 + NTFS as the recorded primary engine environment', () => {
    const verdict = platformVerdict({ system: 'Windows_NT', machine: 'x86_64', filesystem: 'NTFS' });
    assert.strictEqual(verdict.engineStatus, 'tested_primary');
    assert.ok(verdict.engineValidated);
    assert.ok(verdict.extensionRunsHere);
    assert.strictEqual(statusLabel(verdict.engineStatus), 'TESTED - PRIMARY');
  });

  it('refuses FAT32 as unsupported even on Windows x64', () => {
    const verdict = platformVerdict({ system: 'Windows', machine: 'AMD64', filesystem: 'FAT32' });
    assert.strictEqual(verdict.engineStatus, 'unsupported');
    assert.ok(verdict.warnings.some((warning) => warning.includes('UNSUPPORTED')));
  });

  it('refuses network drives as unsupported', () => {
    const verdict = platformVerdict({
      system: 'Windows',
      machine: 'AMD64',
      filesystem: 'NTFS',
      driveType: 'network',
    });
    assert.strictEqual(verdict.engineStatus, 'unsupported');
  });

  it('marks Windows ARM64 untested', () => {
    const verdict = platformVerdict({ system: 'Windows', machine: 'ARM64', filesystem: 'NTFS' });
    assert.strictEqual(verdict.engineStatus, 'untested');
    assert.ok(!verdict.engineValidated);
  });

  it('warns when Windows long paths are disabled', () => {
    const verdict = platformVerdict({
      system: 'Windows',
      machine: 'AMD64',
      filesystem: 'NTFS',
      longPathsEnabled: 0,
    });
    assert.ok(verdict.warnings.some((warning) => warning.includes('LongPathsEnabled')));
  });

  it('marks macOS arm64 as declared, not validated', () => {
    const verdict = platformVerdict({ system: 'Darwin', machine: 'arm64' });
    assert.strictEqual(verdict.engineStatus, 'declared_ci_pending');
    assert.ok(!verdict.engineValidated);
    assert.ok(verdict.extensionRunsHere);
    assert.ok(verdict.warnings.some((warning) => warning.includes('DECLARED')));
  });

  it('marks macOS Intel as unsupported (dependency-blocked)', () => {
    const verdict = platformVerdict({ system: 'Darwin', machine: 'x86_64' });
    assert.strictEqual(verdict.engineStatus, 'unsupported');
  });

  it('marks Linux as declared pending CI', () => {
    const verdict = platformVerdict({ system: 'Linux', machine: 'x86_64', filesystem: 'ext4' });
    assert.strictEqual(verdict.engineStatus, 'declared_ci_pending');
    assert.ok(!verdict.engineValidated);
  });

  it('never equates "extension installs here" with "engine validated here"', () => {
    // The extension runs everywhere; engine validation is only the primary env.
    const linux = platformVerdict({ system: 'Linux', machine: 'x86_64' });
    assert.ok(linux.extensionRunsHere);
    assert.ok(!linux.engineValidated);
    const unknown = platformVerdict({ system: 'Plan9', machine: 'weird' });
    assert.strictEqual(unknown.engineStatus, 'untested');
    assert.strictEqual(statusLabel(unknown.engineStatus), 'UNTESTED');
  });
});
