import { InjectionToken } from '@angular/core';

/** What the SPA needs to know about the identity provider; served as /config.json at run time. */
export interface AuthConfig {
  readonly issuer: string;
  readonly clientId: string;
  readonly audience: string;
}

/** Set by the application initializer once /config.json has been read; null = not configured. */
export const AUTH_CONFIG = new InjectionToken<{ value: AuthConfig | null }>('AUTH_CONFIG', {
  factory: () => ({ value: null }),
});

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value.trim() : null;
}

/** Accepts only a complete, https (or loopback http) configuration; anything else is "none". */
export function parseAuthConfig(raw: unknown): AuthConfig | null {
  if (typeof raw !== 'object' || raw === null) {
    return null;
  }
  const record = raw as Record<string, unknown>;
  const issuer = text(record['issuer'])?.replace(/\/+$/, '') ?? null;
  const clientId = text(record['clientId']);
  const audience = text(record['audience']);
  if (!issuer || !clientId || !audience) {
    return null;
  }
  try {
    const url = new URL(issuer);
    const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
    if (url.protocol !== 'https:' && !(url.protocol === 'http:' && loopback)) {
      return null;
    }
  } catch {
    return null;
  }
  return { issuer, clientId, audience };
}

export async function fetchAuthConfig(
  fetcher: typeof fetch = (input, init) => fetch(input, init),
): Promise<AuthConfig | null> {
  try {
    const response = await fetcher('/config.json', { cache: 'no-store' });
    return response.ok ? parseAuthConfig(await response.json()) : null;
  } catch {
    return null;
  }
}
