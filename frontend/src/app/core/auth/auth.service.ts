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
  signinSilent(): Promise<User | null>;
  getUser(): Promise<User | null>;
  removeUser(): Promise<void>;
  revokeTokens(types?: ('access_token' | 'refresh_token')[]): Promise<void>;
}

/** Leaves the application for another address; replaced in tests. */
export const NAVIGATE = new InjectionToken<(url: string) => void>('NAVIGATE', {
  factory: () => (url: string) => window.location.assign(url),
});

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

/** Renew this long before expiry (shorter for short-lived tokens), but never sooner than 1 s. */
const RENEW_LEAD_MS = 60_000;
const MAX_TIMER_MS = 2_147_483_647;

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
  private readonly config = inject(AUTH_CONFIG).value;
  private readonly navigate = inject(NAVIGATE);
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
    this.adopt(user);
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

  /**
   * Signs out (US-002): revokes the refresh token (best effort), discards every token and leaves
   * through the provider's own logout page, which returns to the start page. The provider has no
   * OIDC end-session endpoint, so its portal logout address is derived from the issuer.
   */
  async signOut(): Promise<void> {
    try {
      await this.manager?.revokeTokens(['refresh_token']);
    } catch {
      // An unreachable provider must not keep the user signed in here.
    }
    await this.clear();
    if (this.config) {
      const back = encodeURIComponent(`${window.location.origin}/`);
      this.navigate(`${this.config.issuer}/logout?rd=${back}`);
    }
  }

  /**
   * Gets a new access token with the refresh token (rotation: the provider returns a new refresh
   * token each time). Callers that arrive while a renewal is running share it, so a burst of
   * requests causes exactly one refresh call. Any failure ends the local session and returns false.
   */
  renew(): Promise<boolean> {
    if (!this.manager) {
      return Promise.resolve(false);
    }
    this.renewal ??= this.renewOnce(this.manager).finally(() => {
      this.renewal = null;
    });
    return this.renewal;
  }

  /** Goes through the provider again and comes back to the current page. */
  restartSignIn(): Promise<void> {
    this.restarting ??= this.signIn(window.location.pathname + window.location.search);
    return this.restarting;
  }

  private restarting: Promise<void> | null = null;

  private renewal: Promise<boolean> | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;

  private async renewOnce(manager: UserManagerLike): Promise<boolean> {
    try {
      const user = await manager.signinSilent();
      if (!user) {
        throw new Error('no user returned');
      }
      this.adopt(user);
      return true;
    } catch {
      // Includes the provider answering 4xx or 5xx: either way this session cannot continue.
      await this.clear();
      return false;
    }
  }

  /** Makes this the signed-in user and plans the next renewal. */
  private adopt(user: User): void {
    this.current.set(user);
    this.cancelTimer();
    const lifetimeMs = (user.expires_in ?? 0) * 1000;
    if (lifetimeMs <= 0) {
      return;
    }
    const lead = Math.min(RENEW_LEAD_MS, lifetimeMs * 0.2);
    const delay = Math.min(Math.max(lifetimeMs - lead, 1000), MAX_TIMER_MS);
    this.timer = setTimeout(() => {
      void this.renew().then((ok) => (ok ? undefined : this.restartSignIn()));
    }, delay);
  }

  private cancelTimer(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  /** Forgets the local session (used by sign-out and by a failed renewal). */
  async clear(): Promise<void> {
    this.cancelTimer();
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
