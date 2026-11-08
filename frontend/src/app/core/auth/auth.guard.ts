import { inject } from '@angular/core';
import type { CanActivateFn } from '@angular/router';
import { Router } from '@angular/router';

import { AuthService } from './auth.service';

/**
 * Protects the pages that show personal data (US-001). A signed-in user passes. After a reload the
 * guard first tries to restore the session through the provider; otherwise the visitor lands on
 * the sign-in page, which remembers where they wanted to go.
 */
export const authGuard: CanActivateFn = async (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router); // injected before the first await (injection context)
  if (auth.authenticated()) {
    return true;
  }
  await auth.restore(state.url);
  if (auth.authenticated()) {
    return true;
  }
  return router.createUrlTree(['/signin-required'], {
    queryParams: { returnUrl: state.url },
  });
};
