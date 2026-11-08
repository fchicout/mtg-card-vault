import { Injectable, InjectionToken, computed, inject, signal } from '@angular/core';
import {
  InMemoryWebStorage,
  UserManager,
  WebStorageStateStore,
  type User,
  type UserManagerSettings,
} from 'oidc-client-ts';

import { AUTH_CONFIG } from './auth-config';

/** The part of oidc-client-ts the application uses; tests provide a fake. */
export interface UserManagerLike {
  signinRedirect(args?: { state?: unknown }): Promise<void>;
  signinRedirectCallback(url?: string): Promise<User>;
  getUser(): Promise<User | null>;
  removeUser(): Promise<void>;
}

export const USER_MANAGER = new InjectionToken<UserManagerLike | null>('USER_MANAGER', {
  factory: () => {
    const config = inject(AUTH_CONFIG).value;
    return config ? new UserManager(userManagerSettings(config, window.location.origin)) : null;
  },
});

export function userManagerSettings(
  config: { issuer: string; clientId: string; audience: string },
  origin: string,
): UserManagerSettings {
  return {
    authority: config.issuer,
    client_id: config.clientId,
    redirect_uri: `${origin}/callback`,
    post_logout_redirect_uri: `${origin}/`,
    response_type: 'code', // authorization code with PKCE S256 (FR-AUTH-01)
    scope: 'openid profile email offline_access',
    // The provider only lists the audience a client may request; the SPA must ask for it.
    extraQueryParams: { audience: config.audience },
    // Tokens live in memory only: never in web storage (FR-AUTH-01). The short-lived sign-in
    // state (state, nonce, PKCE verifier) must survive the redirect, so it uses sessionStorage.
    userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
    stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
    automaticSilentRenew: false,
    loadUserInfo: false,
  };
}

const SESSION_MARKER = 'mtgvault.session';
const RESTORE_ATTEMPT = 'mtgvault.restore-attempt';
const RESTORE_COOLDOWN_MS = 10_000;

interface SignInState {
  returnUrl?: string;
}

/**
 * Browser-side authentication (US-001): redirect to the provider, finish the code exchange,
 * keep the tokens in memory and expose who is signed in.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly manager = inject(USER_MANAGER);
  private readonly current = signal<User | null>(null);

  readonly configured = this.manager !== null;
  readonly authenticated = computed(() => {
    const user = this.current();
    return user !== null && !user.expired;
  });
  /** A name from the token claims; the profile endpoint refines it. */
  readonly displayName = computed(() => {
    const profile = this.current()?.profile;
    return (profile?.name ?? profile?.preferred_username ?? null) as string | null;
  });

  /** The bearer token for API calls, or null when nobody is signed in. */
  accessToken(): string | null {
    const user = this.current();
    return user && !user.expired ? user.access_token : null;
  }

  /** Redirects to the provider; `returnUrl` is where the user lands afterwards. */
  async signIn(returnUrl = '/'): Promise<void> {
    if (!this.manager) {
      throw new Error('The identity provider is not configured');
    }
    await this.manager.signinRedirect({ state: { returnUrl } satisfies SignInState });
  }

  /** Completes the redirect back from the provider and returns the route to open. */
  async completeSignIn(callbackUrl: string = window.location.href): Promise<string> {
    if (!this.manager) {
      throw new Error('The identity provider is not configured');
    }
    const user = await this.manager.signinRedirectCallback(callbackUrl);
    this.current.set(user);
    this.mark(true);
    const target = (user.state as SignInState | undefined)?.returnUrl;
    return target?.startsWith('/') && !target.startsWith('//') ? target : '/';
  }

  /**
   * After a page reload the in-memory tokens are gone. If the visitor was signed in, go through the
   * provider again (it still has its own session, so this is quick), at most once per cooldown.
   */
  async restore(returnUrl: string): Promise<void> {
    if (!this.manager || this.authenticated() || !this.marker()) {
      return;
    }
    const last = Number(this.read(RESTORE_ATTEMPT) ?? 0);
    if (Date.now() - last < RESTORE_COOLDOWN_MS) {
      return;
    }
    this.write(RESTORE_ATTEMPT, String(Date.now()));
    await this.signIn(returnUrl);
  }

  /** Forgets the local session (used by sign-out and by a failed renewal). */
  async clear(): Promise<void> {
    this.current.set(null);
    this.mark(false);
    await this.manager?.removeUser();
  }

  private marker(): boolean {
    return this.read(SESSION_MARKER) === '1';
  }

  private mark(signedIn: boolean): void {
    if (signedIn) {
      this.write(SESSION_MARKER, '1');
    } else {
      try {
        sessionStorage.removeItem(SESSION_MARKER);
      } catch {
        // Storage can be blocked; nothing to remove then.
      }
    }
  }

  private read(key: string): string | null {
    try {
      return sessionStorage.getItem(key);
    } catch {
      return null;
    }
  }

  private write(key: string, value: string): void {
    try {
      sessionStorage.setItem(key, value);
    } catch {
      // Without storage a reload simply starts signed out.
    }
  }
}
