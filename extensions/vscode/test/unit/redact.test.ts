import * as assert from 'assert';
import { redact, redactObject, truncate } from '../../src/redact';

describe('secret-safe logging (redact)', () => {
  it('redacts bearer tokens', () => {
    const out = redact('Authorization: Bearer abcdefghijklmnop123456');
    assert.ok(!out.includes('abcdefghijklmnop123456'));
    assert.ok(out.includes('Bearer [redacted]'));
  });

  it('redacts JWT-shaped tokens', () => {
    const jwt = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdef123456';
    const out = redact(`token is ${jwt} here`);
    assert.ok(!out.includes(jwt));
    assert.ok(out.includes('[redacted-jwt]'));
  });

  it('redacts password/secret/token assignments in any casing', () => {
    for (const sample of [
      'password=hunter2',
      'PASSWORD: hunter2',
      'api_key=abc123',
      'SECRET=xyz',
      'token = t0psecret',
    ]) {
      const out = redact(sample);
      assert.ok(!out.includes(sample.split(/[=:]/)[1].trim()), `leaked: ${out}`);
      assert.ok(out.includes('[redacted]'), `not redacted: ${out}`);
    }
  });

  it('redacts PEM private key blocks', () => {
    const pem =
      '-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAqEA\n-----END RSA PRIVATE KEY-----';
    const out = redact(`key material:\n${pem}\ndone`);
    assert.ok(!out.includes('MIIEpAIBAAKCAqEA'));
    assert.ok(out.includes('[redacted-private-key]'));
  });

  it('redacts AWS access key ids', () => {
    const out = redact('id=AKIAIOSFODNN7EXAMPLE');
    assert.ok(!out.includes('AKIAIOSFODNN7EXAMPLE'));
  });

  it('leaves ordinary diagnostics untouched', () => {
    const message = 'conflict detected: concurrent_mutation for src/config.yaml';
    assert.strictEqual(redact(message), message);
  });

  it('redactObject masks secret-named keys and nested strings', () => {
    const masked = redactObject({
      password: 'hunter2',
      nested: { api_key: 'abc', note: 'Bearer abcdefghijklmnop' },
      count: 3,
      flag: true,
    }) as Record<string, unknown>;
    assert.strictEqual(masked['password'], '[redacted]');
    assert.strictEqual((masked['nested'] as Record<string, unknown>)['api_key'], '[redacted]');
    assert.ok(
      !String((masked['nested'] as Record<string, unknown>)['note']).includes('abcdefghijklmnop'),
    );
    assert.strictEqual(masked['count'], 3);
    assert.strictEqual(masked['flag'], true);
  });

  it('truncates oversized text with a clear marker', () => {
    const out = truncate('x'.repeat(5000), 100);
    assert.ok(out.includes('[truncated 4900 characters]'));
    assert.ok(out.length < 200);
    assert.strictEqual(truncate('short', 100), 'short');
  });
});
