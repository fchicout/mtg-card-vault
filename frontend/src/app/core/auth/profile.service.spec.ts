import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { provideApiConfiguration } from '../../api';
import { AuthService } from './auth.service';
import { ProfileService } from './profile.service';

describe('ProfileService', () => {
  const authenticated = signal(false);
  const tokenName = signal<string | null>('Token Name');

  function setup(): { profile: ProfileService; http: HttpTestingController } {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApiConfiguration(''),
        { provide: AuthService, useValue: { authenticated, displayName: tokenName } },
      ],
    });
    return { profile: TestBed.inject(ProfileService), http: TestBed.inject(HttpTestingController) };
  }

  beforeEach(() => {
    authenticated.set(false);
    tokenName.set('Token Name');
  });

  it('calls the API only after sign-in and shows the profile name', async () => {
    const { profile, http } = setup();
    TestBed.tick();
    http.expectNone('/api/v1/me');
    authenticated.set(true);
    TestBed.tick();
    http.expectOne('/api/v1/me').flush({ id: 'u1', display_name: 'Ada', email: null });
    await Promise.resolve();
    await Promise.resolve();
    expect(profile.displayName()).toBe('Ada');
  });

  it('falls back to the token name when the profile cannot be loaded, without an alert', async () => {
    const { profile, http } = setup();
    authenticated.set(true);
    TestBed.tick();
    http.expectOne('/api/v1/me').flush('boom', { status: 500, statusText: 'Server Error' });
    await new Promise<void>((resolve) => setTimeout(resolve));
    expect(profile.displayName()).toBe('Token Name');
  });

  it('forgets the profile when the user signs out', async () => {
    const { profile, http } = setup();
    authenticated.set(true);
    TestBed.tick();
    http.expectOne('/api/v1/me').flush({ id: 'u1', display_name: 'Ada', email: null });
    await new Promise<void>((resolve) => setTimeout(resolve));
    authenticated.set(false);
    TestBed.tick();
    expect(profile.profile()).toBeNull();
  });
});
