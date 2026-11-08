import { HttpContextToken, HttpErrorResponse, type HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, from, switchMap, throwError } from 'rxjs';

import { AuthService } from './auth.service';

/** Same-origin API paths; nothing else ever receives the access token (FR-AUTH-01). */
const API_PREFIX = '/api/';

/** Marks the one retry of a request, so a second 401 is final. */
const RETRIED = new HttpContextToken<boolean>(() => false);

/**
 * Adds the bearer token to API calls. A 401 for a request that carried a token means the token
 * ended early: renew once and repeat the request once; if that fails, start the sign-in again
 * (it returns to this page) and report the original error (FR-AUTH-03).
 */
export const authInterceptor: HttpInterceptorFn = (request, next) => {
  if (!request.url.startsWith(API_PREFIX)) {
    return next(request);
  }
  const auth = inject(AuthService);
  const token = auth.accessToken();
  if (!token) {
    return next(request);
  }
  return next(request.clone({ setHeaders: { Authorization: `Bearer ${token}` } })).pipe(
    catchError((error: unknown) => {
      if (
        !(error instanceof HttpErrorResponse) ||
        error.status !== 401 ||
        request.context.get(RETRIED)
      ) {
        return throwError(() => error);
      }
      return from(auth.renew()).pipe(
        switchMap((renewed) => {
          const fresh = renewed ? auth.accessToken() : null;
          if (!fresh) {
            void auth.restartSignIn();
            return throwError(() => error);
          }
          return next(
            request.clone({
              setHeaders: { Authorization: `Bearer ${fresh}` },
              context: request.context.set(RETRIED, true),
            }),
          );
        }),
      );
    }),
  );
};
