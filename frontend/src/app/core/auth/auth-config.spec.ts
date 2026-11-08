import { fetchAuthConfig, parseAuthConfig } from './auth-config';

const valid = { issuer: 'https://idp.example/', clientId: 'spa', audience: 'api' };

describe('parseAuthConfig', () => {
  it('accepts a complete configuration and trims the issuer', () => {
    expect(parseAuthConfig(valid)).toEqual({
      issuer: 'https://idp.example',
      clientId: 'spa',
      audience: 'api',
    });
  });

  it('accepts http only for loopback hosts', () => {
    expect(parseAuthConfig({ ...valid, issuer: 'http://localhost:9000' })).not.toBeNull();
    expect(parseAuthConfig({ ...valid, issuer: 'http://idp.example' })).toBeNull();
  });

  it.each([
    null,
    'x',
    5,
    {},
    { ...valid, clientId: '' },
    { ...valid, audience: 7 },
    { ...valid, issuer: 'not a url' },
  ])('rejects %j', (raw) => {
    expect(parseAuthConfig(raw)).toBeNull();
  });
});

describe('fetchAuthConfig', () => {
  const answer = (body: unknown, ok = true): typeof fetch =>
    (() => Promise.resolve({ ok, json: () => Promise.resolve(body) })) as unknown as typeof fetch;

  it('reads /config.json', async () => {
    expect(await fetchAuthConfig(answer(valid))).not.toBeNull();
  });

  it('is null when the file is missing, invalid or unreachable', async () => {
    expect(await fetchAuthConfig(answer(valid, false))).toBeNull();
    expect(await fetchAuthConfig(answer({}))).toBeNull();
    expect(
      await fetchAuthConfig((() => Promise.reject(new Error('offline'))) as typeof fetch),
    ).toBeNull();
  });
});
