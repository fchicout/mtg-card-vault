import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { authInterceptor } from './auth.interceptor';
import { AuthService } from './auth.service';

interface FakeAuth {
  accessToken: () => string | null;
  renew: () => Promise<boolean>;
  restartSignIn: () => Promise<void>;
}

function setupWith(auth: FakeAuth): { http: HttpClient; controller: HttpTestingController } {
  TestBed.configureTestingModule({
    providers: [
      provideHttpClient(withInterceptors([authInterceptor])),
      provideHttpClientTesting(),
      { provide: AuthService, useValue: auth },
    ],
  });
  return { http: TestBed.inject(HttpClient), controller: TestBed.inject(HttpTestingController) };
}

function setup(token: string | null): { http: HttpClient; controller: HttpTestingController } {
  TestBed.configureTestingModule({
    providers: [
      provideHttpClient(withInterceptors([authInterceptor])),
      provideHttpClientTesting(),
      { provide: AuthService, useValue: { accessToken: () => token } },
    ],
  });
  return { http: TestBed.inject(HttpClient), controller: TestBed.inject(HttpTestingController) };
}

describe('authInterceptor', () => {
  it('adds the bearer token to API calls', () => {
    const { http, controller } = setup('tok');
    http.get('/api/v1/me').subscribe();
    expect(controller.expectOne('/api/v1/me').request.headers.get('Authorization')).toBe(
      'Bearer tok',
    );
  });

  it.each(['https://scryfall.example/cards', '/config.json', '/healthz', '//evil.example/api/x'])(
    'sends no token to %s',
    (url) => {
      const { http, controller } = setup('tok');
      http.get(url).subscribe();
      expect(controller.expectOne(url).request.headers.has('Authorization')).toBe(false);
    },
  );

  it('sends API calls without a header when nobody is signed in', () => {
    const { http, controller } = setup(null);
    http.get('/api/v1/me').subscribe();
    expect(controller.expectOne('/api/v1/me').request.headers.has('Authorization')).toBe(false);
  });
});

describe('authInterceptor: a 401 for a token that ended early', () => {
  const unauthorized = { status: 401, statusText: 'Unauthorized' };

  it('renews once and repeats the request once with the new token', async () => {
    let token = 'old';
    const renew = vi.fn(() => {
      token = 'new';
      return Promise.resolve(true);
    });
    const { http, controller } = setupWith({
      accessToken: () => token,
      renew,
      restartSignIn: () => Promise.resolve(),
    });
    let body: unknown;
    http.get('/api/v1/me').subscribe((value) => (body = value));
    controller.expectOne('/api/v1/me').flush('x', unauthorized);
    await Promise.resolve();
    await Promise.resolve();
    const retry = controller.expectOne('/api/v1/me');
    expect(retry.request.headers.get('Authorization')).toBe('Bearer new');
    retry.flush({ ok: true });
    expect(body).toEqual({ ok: true });
    expect(renew).toHaveBeenCalledTimes(1);
  });

  it('gives up after a second 401 (no loop)', async () => {
    const renew = vi.fn(() => Promise.resolve(true));
    const { http, controller } = setupWith({
      accessToken: () => 't',
      renew,
      restartSignIn: () => Promise.resolve(),
    });
    let failure: unknown;
    http.get('/api/v1/me').subscribe({ error: (e: unknown) => (failure = e) });
    controller.expectOne('/api/v1/me').flush('x', unauthorized);
    await Promise.resolve();
    await Promise.resolve();
    controller.expectOne('/api/v1/me').flush('x', unauthorized);
    expect(failure).toBeTruthy();
    expect(renew).toHaveBeenCalledTimes(1);
  });

  it('restarts the sign-in and reports the error when renewal fails', async () => {
    const restartSignIn = vi.fn(() => Promise.resolve());
    const { http, controller } = setupWith({
      accessToken: () => null,
      renew: () => Promise.resolve(false),
      restartSignIn,
    });
    let token: string | null = 'old';
    // The token was present when the request left, gone after the failed renewal.
    const auth = TestBed.inject(AuthService) as unknown as FakeAuth;
    auth.accessToken = () => token;
    auth.renew = () => {
      token = null;
      return Promise.resolve(false);
    };
    let failure: unknown;
    http.get('/api/v1/me').subscribe({ error: (e: unknown) => (failure = e) });
    controller.expectOne('/api/v1/me').flush('x', unauthorized);
    await Promise.resolve();
    await Promise.resolve();
    expect(restartSignIn).toHaveBeenCalledTimes(1);
    expect(failure).toBeTruthy();
    controller.verify();
  });

  it('leaves other statuses and anonymous calls alone', () => {
    const renew = vi.fn(() => Promise.resolve(true));
    const { http, controller } = setupWith({
      accessToken: () => null,
      renew,
      restartSignIn: () => Promise.resolve(),
    });
    http.get('/api/v1/me').subscribe({ error: () => undefined });
    controller.expectOne('/api/v1/me').flush('x', unauthorized);
    expect(renew).not.toHaveBeenCalled();
  });
});
