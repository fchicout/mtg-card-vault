import { TestBed } from '@angular/core/testing';
import type { User } from 'oidc-client-ts';

import { AUTH_CONFIG } from './auth-config';
import {
  AuthService,
  NAVIGATE,
  USER_MANAGER,
  userManagerSettings,
  type UserManagerLike,
} from './auth.service';

function user(overrides: Partial<User> = {}): User {
  return {
    access_token: 'access-abc',
    expired: false,
    profile: { name: 'Ada', sub: 'u1' },
    state: { returnUrl: '/vault' },
    ...overrides,
  } as unknown as User;
}

let revokeFails = false;
let silentResult: User | null | Error = null;

function fakeManager(result: User | Error): UserManagerLike & { calls: string[] } {
  const calls: string[] = [];
  return {
    calls,
    signinRedirect: (args) => {
      calls.push(`redirect:${JSON.stringify(args?.state)}`);
      return Promise.resolve();
    },
    signinSilent: () => {
      calls.push('silent');
      return silentResult instanceof Error
        ? Promise.reject(silentResult)
        : Promise.resolve(silentResult);
    },
    signinRedirectCallback: () =>
      result instanceof Error ? Promise.reject(result) : Promise.resolve(result),
    getUser: () => Promise.resolve(null),
    removeUser: () => {
      calls.push('remove');
      return Promise.resolve();
    },
    revokeTokens: (types) => {
      calls.push(`revoke:${types?.join(',')}`);
      return revokeFails ? Promise.reject(new Error('provider down')) : Promise.resolve();
    },
  };
}

function service(manager: UserManagerLike | null): AuthService {
  TestBed.configureTestingModule({ providers: [{ provide: USER_MANAGER, useValue: manager }] });
  return TestBed.inject(AuthService);
}

describe('AuthService', () => {
  beforeEach(() => sessionStorage.clear());

  it('is unconfigured and signed out without a provider', async () => {
    const auth = service(null);
    expect(auth.configured).toBe(false);
    expect(auth.authenticated()).toBe(false);
    expect(auth.accessToken()).toBeNull();
    await expect(auth.signIn()).rejects.toThrow('not configured');
  });

  it('redirects to the provider with the return route as state', async () => {
    const manager = fakeManager(user());
    await service(manager).signIn('/vault');
    expect(manager.calls).toEqual(['redirect:{"returnUrl":"/vault"}']);
  });

  it('completes the sign-in, keeps the token in memory and returns the saved route', async () => {
    const auth = service(fakeManager(user()));
    expect(await auth.completeSignIn('https://app/callback?code=1')).toBe('/vault');
    expect(auth.authenticated()).toBe(true);
    expect(auth.accessToken()).toBe('access-abc');
    expect(auth.displayName()).toBe('Ada');
    expect(JSON.stringify({ ...localStorage })).not.toContain('access-abc');
    expect(JSON.stringify({ ...sessionStorage })).not.toContain('access-abc');
  });

  it.each(['//evil.example', 'https://evil.example', undefined])(
    'never returns an off-site route (%s)',
    async (returnUrl) => {
      const auth = service(fakeManager(user({ state: { returnUrl } } as Partial<User>)));
      expect(await auth.completeSignIn('x')).toBe('/');
    },
  );

  it('does not treat an expired user as signed in', async () => {
    const auth = service(fakeManager(user({ expired: true })));
    await auth.completeSignIn('x');
    expect(auth.authenticated()).toBe(false);
    expect(auth.accessToken()).toBeNull();
  });

  it('a failed exchange leaves the user signed out', async () => {
    const auth = service(fakeManager(new Error('access_denied')));
    await expect(auth.completeSignIn('x')).rejects.toThrow('access_denied');
    expect(auth.authenticated()).toBe(false);
  });

  it('clear forgets the session', async () => {
    const manager = fakeManager(user());
    const auth = service(manager);
    await auth.completeSignIn('x');
    await auth.clear();
    expect(auth.authenticated()).toBe(false);
    expect(manager.calls).toContain('remove');
  });

  it('restores a previous session through the provider, but not in a loop', async () => {
    const manager = fakeManager(user());
    const auth = service(manager);
    await auth.completeSignIn('x');
    await auth.clear();
    sessionStorage.setItem('mtgvault.session', '1');
    await auth.restore('/vault');
    await auth.restore('/vault');
    expect(manager.calls.filter((c) => c.startsWith('redirect'))).toHaveLength(1);
  });

  it('does not restore when nobody was signed in', async () => {
    const manager = fakeManager(user());
    await service(manager).restore('/');
    expect(manager.calls).toEqual([]);
  });
});

describe('AuthService renewal', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.useFakeTimers();
    silentResult = null;
  });
  afterEach(() => vi.useRealTimers());

  const withLifetime = (seconds: number, token = 'access-abc'): User =>
    user({ expires_in: seconds, access_token: token } as Partial<User>);

  it('shares one refresh call between concurrent callers and adopts the new token', async () => {
    const manager = fakeManager(withLifetime(600));
    const auth = service(manager);
    await auth.completeSignIn('x');
    silentResult = withLifetime(600, 'access-new');
    const results = await Promise.all([auth.renew(), auth.renew(), auth.renew()]);
    expect(results).toEqual([true, true, true]);
    expect(manager.calls.filter((c) => c === 'silent')).toHaveLength(1);
    expect(auth.accessToken()).toBe('access-new');
  });

  it('renews on its own shortly before the token expires', async () => {
    const manager = fakeManager(withLifetime(600));
    const auth = service(manager);
    await auth.completeSignIn('x');
    silentResult = withLifetime(600, 'access-new');
    await vi.advanceTimersByTimeAsync(539_000); // 60 s before the end of 600 s
    expect(manager.calls).not.toContain('silent');
    await vi.advanceTimersByTimeAsync(2_000);
    expect(manager.calls.filter((c) => c === 'silent')).toHaveLength(1);
    expect(auth.accessToken()).toBe('access-new');
  });

  it('plans short-lived tokens at 80 % of their life', async () => {
    const manager = fakeManager(withLifetime(10));
    const auth = service(manager);
    await auth.completeSignIn('x');
    silentResult = withLifetime(10, 'access-new');
    await vi.advanceTimersByTimeAsync(8_100);
    expect(manager.calls).toContain('silent');
    expect(auth.accessToken()).toBe('access-new');
  });

  it.each([
    ['the provider rejects the refresh token', new Error('invalid_grant')],
    ['the provider answers HTTP 500', new Error('Internal Server Error')],
    ['no user comes back', null],
  ])('ends the session when %s', async (_name, outcome) => {
    const manager = fakeManager(withLifetime(600));
    const auth = service(manager);
    await auth.completeSignIn('x');
    silentResult = outcome;
    expect(await auth.renew()).toBe(false);
    expect(auth.authenticated()).toBe(false);
    expect(manager.calls).toContain('remove');
  });

  it('restarts the sign-in when the planned renewal fails', async () => {
    const manager = fakeManager(withLifetime(10));
    const auth = service(manager);
    await auth.completeSignIn('x');
    silentResult = new Error('invalid_grant');
    await vi.advanceTimersByTimeAsync(8_100);
    expect(manager.calls.some((c) => c.startsWith('redirect'))).toBe(true);
  });

  it('stops the timer when the user signs out', async () => {
    const manager = fakeManager(withLifetime(10));
    const auth = service(manager);
    await auth.completeSignIn('x');
    await auth.clear();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(manager.calls).not.toContain('silent');
  });

  it('cannot renew without a provider', async () => {
    expect(await service(null).renew()).toBe(false);
  });
});

describe('AuthService sign-out', () => {
  const navigations: string[] = [];

  function withConfig(manager: UserManagerLike): AuthService {
    revokeFails = false;
    navigations.length = 0;
    TestBed.configureTestingModule({
      providers: [
        { provide: USER_MANAGER, useValue: manager },
        {
          provide: AUTH_CONFIG,
          useValue: { value: { issuer: 'https://idp.example', clientId: 'spa', audience: 'api' } },
        },
        { provide: NAVIGATE, useValue: (url: string) => navigations.push(url) },
      ],
    });
    return TestBed.inject(AuthService);
  }

  it('revokes the refresh token, drops every token and leaves through the provider logout', async () => {
    const manager = fakeManager(user());
    const auth = withConfig(manager);
    await auth.completeSignIn('x');
    await auth.signOut();
    expect(manager.calls).toEqual(expect.arrayContaining(['revoke:refresh_token', 'remove']));
    expect(auth.authenticated()).toBe(false);
    expect(auth.accessToken()).toBeNull();
    expect(navigations).toEqual([
      `https://idp.example/logout?rd=${encodeURIComponent(window.location.origin + '/')}`,
    ]);
    expect(sessionStorage.getItem('mtgvault.session')).toBeNull();
  });

  it('still signs out locally when the provider cannot be reached', async () => {
    const auth = withConfig(fakeManager(user()));
    await auth.completeSignIn('x');
    revokeFails = true;
    await auth.signOut();
    expect(auth.authenticated()).toBe(false);
    expect(navigations).toHaveLength(1);
  });
});

describe('userManagerSettings', () => {
  const settings = userManagerSettings(
    { issuer: 'https://idp.example', clientId: 'spa', audience: 'api' },
    'https://app.example',
  );

  it('uses the code flow, the audience and the callback route', () => {
    expect(settings.response_type).toBe('code');
    expect(settings.extraQueryParams).toEqual({ audience: 'api' });
    expect(settings.redirect_uri).toBe('https://app.example/callback');
    expect(settings.scope).toContain('offline_access');
  });

  it('keeps tokens out of web storage', () => {
    expect(settings.automaticSilentRenew).toBe(false);
    const userStore = settings.userStore as unknown as { _store: Storage };
    expect(userStore._store).not.toBe(window.localStorage);
    expect(userStore._store).not.toBe(window.sessionStorage);
  });
});
