import { TestBed } from '@angular/core/testing';
import {
  Router,
  UrlTree,
  type ActivatedRouteSnapshot,
  type RouterStateSnapshot,
} from '@angular/router';

import { authGuard } from './auth.guard';
import { AuthService } from './auth.service';

interface FakeAuth {
  authenticated: () => boolean;
  restore: (url: string) => Promise<void>;
}

function run(auth: FakeAuth): Promise<boolean | UrlTree> {
  TestBed.configureTestingModule({ providers: [{ provide: AuthService, useValue: auth }] });
  return TestBed.runInInjectionContext(() =>
    authGuard({} as ActivatedRouteSnapshot, { url: '/vault?x=1' } as RouterStateSnapshot),
  ) as Promise<boolean | UrlTree>;
}

describe('authGuard', () => {
  it('lets a signed-in user through without contacting the provider', async () => {
    const restore = vi.fn();
    expect(await run({ authenticated: () => true, restore })).toBe(true);
    expect(restore).not.toHaveBeenCalled();
  });

  it('sends a visitor to the sign-in page and remembers the target', async () => {
    const result = await run({ authenticated: () => false, restore: () => Promise.resolve() });
    expect(result).toBeInstanceOf(UrlTree);
    const router = TestBed.inject(Router);
    expect(router.serializeUrl(result as UrlTree)).toBe(
      '/signin-required?returnUrl=%2Fvault%3Fx%3D1',
    );
  });

  it('tries to restore the session first, and passes if that worked', async () => {
    let signedIn = false;
    const result = await run({
      authenticated: () => signedIn,
      restore: () => {
        signedIn = true;
        return Promise.resolve();
      },
    });
    expect(result).toBe(true);
  });
});
