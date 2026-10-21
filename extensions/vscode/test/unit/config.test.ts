import * as assert from 'assert';
import {
  DEFAULTS,
  isAllowedDocumentationUrl,
  normalizeSettings,
} from '../../src/config';

describe('configuration validation', () => {
  it('returns safe defaults for empty input', () => {
    const { settings, issues } = normalizeSettings({});
    assert.deepStrictEqual(settings, DEFAULTS);
    assert.strictEqual(issues.length, 0);
  });

  it('accepts a valid configuration', () => {
    const { settings, issues } = normalizeSettings({
      pythonPath: '  C:\\venv\\Scripts\\python.exe  ',
      engineRoot: 'C:\\repo',
      autoDetectEngine: false,
      timeoutSeconds: 120,
      maxBaselineBytes: 1024 * 1024,
      showGitChanges: false,
      allowedDocumentationUrls: ['https://github.com/interlock219-beep/INTERLOCK-V4'],
    });
    assert.strictEqual(settings.pythonPath, 'C:\\venv\\Scripts\\python.exe');
    assert.strictEqual(settings.engineRoot, 'C:\\repo');
    assert.strictEqual(settings.autoDetectEngine, false);
    assert.strictEqual(settings.timeoutSeconds, 120);
    assert.strictEqual(settings.showGitChanges, false);
    assert.strictEqual(issues.length, 0);
  });

  it('rejects out-of-range timeouts and falls back', () => {
    for (const bad of [1, 5000, Number.NaN]) {
      const { settings, issues } = normalizeSettings({ timeoutSeconds: bad });
      if (Number.isNaN(bad)) {
        assert.strictEqual(settings.timeoutSeconds, DEFAULTS.timeoutSeconds);
        assert.ok(issues.some((issue) => issue.key === 'interlock.timeoutSeconds'));
      } else {
        assert.strictEqual(settings.timeoutSeconds, DEFAULTS.timeoutSeconds);
        assert.ok(issues.some((issue) => issue.key === 'interlock.timeoutSeconds'));
      }
    }
  });

  it('rejects non-numeric timeouts', () => {
    const { settings, issues } = normalizeSettings({ timeoutSeconds: 'soon' });
    assert.strictEqual(settings.timeoutSeconds, DEFAULTS.timeoutSeconds);
    assert.ok(issues.some((issue) => issue.key === 'interlock.timeoutSeconds'));
  });

  it('rejects interpreter paths containing control characters', () => {
    const { settings, issues } = normalizeSettings({
      pythonPath: 'C:\\python.exe\u0000\u0001',
    });
    assert.strictEqual(settings.pythonPath, '');
    assert.ok(issues.some((issue) => issue.key === 'interlock.pythonPath'));
  });

  it('rejects baseline sizes outside the allowed range', () => {
    const { settings, issues } = normalizeSettings({ maxBaselineBytes: 10 });
    assert.strictEqual(settings.maxBaselineBytes, DEFAULTS.maxBaselineBytes);
    assert.ok(issues.some((issue) => issue.key === 'interlock.maxBaselineBytes'));
  });

  it('rejects non-https documentation URLs', () => {
    const { settings, issues } = normalizeSettings({
      allowedDocumentationUrls: ['http://evil.example.com', 'javascript:alert(1)', 'not a url'],
    });
    assert.deepStrictEqual(settings.allowedDocumentationUrls, DEFAULTS.allowedDocumentationUrls);
    assert.ok(issues.length >= 2);
  });

  it('keeps only https URLs when the list is mixed', () => {
    const { settings } = normalizeSettings({
      allowedDocumentationUrls: [
        'https://github.com/interlock219-beep/INTERLOCK-V4',
        'ftp://nope.example.com',
      ],
    });
    assert.strictEqual(settings.allowedDocumentationUrls.length, 1);
    assert.ok(settings.allowedDocumentationUrls[0].startsWith('https://'));
  });

  describe('isAllowedDocumentationUrl', () => {
    const allow = ['https://github.com/interlock219-beep/INTERLOCK-V4'];

    it('accepts the verified repository origin', () => {
      assert.ok(isAllowedDocumentationUrl('https://github.com/interlock219-beep/INTERLOCK-V4', allow));
      assert.ok(
        isAllowedDocumentationUrl(
          'https://github.com/interlock219-beep/INTERLOCK-V4/blob/master/README.md',
          allow,
        ),
      );
    });

    it('rejects other origins, http, and malformed URLs', () => {
      assert.ok(!isAllowedDocumentationUrl('https://evil.example.com/docs', allow));
      assert.ok(!isAllowedDocumentationUrl('http://github.com/x', allow));
      assert.ok(!isAllowedDocumentationUrl('file:///etc/passwd', allow));
      assert.ok(!isAllowedDocumentationUrl('javascript:alert(1)', allow));
      assert.ok(!isAllowedDocumentationUrl('not-a-url', allow));
    });
  });

  describe('automatic baseline protection', () => {
    it('is enabled by default', () => {
      assert.strictEqual(DEFAULTS.automaticBaselineProtection, true);
      assert.deepStrictEqual(DEFAULTS.baselineExclusions, []);
    });

    it('can be switched off explicitly', () => {
      const { settings, issues } = normalizeSettings({ automaticBaselineProtection: false });
      assert.strictEqual(settings.automaticBaselineProtection, false);
      assert.strictEqual(issues.length, 0);
    });

    it('ignores non-boolean values without claiming a change', () => {
      const { settings } = normalizeSettings({ automaticBaselineProtection: 'yes' });
      assert.strictEqual(settings.automaticBaselineProtection, true);
    });

    it('keeps valid exclusion patterns and reports nothing', () => {
      const { settings, issues } = normalizeSettings({
        baselineExclusions: ['docs/generated/**', ' *.min.js ', 'build/'],
      });
      assert.deepStrictEqual(settings.baselineExclusions, [
        'docs/generated/**',
        '*.min.js',
        'build/',
      ]);
      assert.strictEqual(issues.length, 0);
    });

    it('drops blank and non-string entries without failing the run', () => {
      const { settings } = normalizeSettings({
        baselineExclusions: ['', '   ', 42, null, 'ok/**'],
      });
      assert.deepStrictEqual(settings.baselineExclusions, ['ok/**']);
    });

    it('rejects patterns with control characters or excessive length', () => {
      const { settings, issues } = normalizeSettings({
        baselineExclusions: ['bad\u0000pattern', 'x'.repeat(201), 'good/**'],
      });
      assert.deepStrictEqual(settings.baselineExclusions, ['good/**']);
      assert.strictEqual(
        issues.filter((issue) => issue.key === 'interlock.baselineExclusions').length,
        2,
      );
    });

    it('caps the list at 50 patterns and says so', () => {
      const many = Array.from({ length: 60 }, (_, i) => `dir${i}/**`);
      const { settings, issues } = normalizeSettings({ baselineExclusions: many });
      assert.strictEqual(settings.baselineExclusions.length, 50);
      assert.ok(issues.some((issue) => issue.key === 'interlock.baselineExclusions'));
    });
  });

  describe('approver identity (engine audit field)', () => {
    it('is empty by default - nothing is invented', () => {
      const { settings, issues } = normalizeSettings({});
      assert.strictEqual(settings.approverIdentity, '');
      assert.strictEqual(issues.length, 0);
    });

    it('keeps a trimmed identity and reports nothing', () => {
      const { settings, issues } = normalizeSettings({ approverIdentity: '  ada@example.com  ' });
      assert.strictEqual(settings.approverIdentity, 'ada@example.com');
      assert.strictEqual(issues.length, 0);
    });

    it('ignores identities with line breaks, NULs or excessive length', () => {
      for (const bad of ['ada\nada', 'ada\u0000ada', 'x'.repeat(201)]) {
        const { settings, issues } = normalizeSettings({ approverIdentity: bad });
        assert.strictEqual(settings.approverIdentity, '');
        assert.ok(issues.some((issue) => issue.key === 'interlock.approverIdentity'));
      }
    });

    it('ignores non-string values without failing the run', () => {
      const { settings, issues } = normalizeSettings({ approverIdentity: { name: 'ada' } });
      assert.strictEqual(settings.approverIdentity, '');
      assert.strictEqual(issues.length, 0);
    });
  });
});
