import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { authInterceptor } from './auth.interceptor';
import { AuthService } from './auth.service';

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
