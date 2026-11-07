import { HttpContextToken, HttpErrorResponse, type HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';

import { NotificationService } from '../notifications/notification.service';
import { describeFailure } from './problem';

/** A request that handles its own failure (for example inline) sets this to true. */
export const HANDLES_OWN_ERRORS = new HttpContextToken<boolean>(() => false);

/** Turns every failed API call into a plain-language alert unless the caller opts out. */
export const errorInterceptor: HttpInterceptorFn = (request, next) => {
  const notifications = inject(NotificationService);
  return next(request).pipe(
    catchError((error: unknown) => {
      if (error instanceof HttpErrorResponse && !request.context.get(HANDLES_OWN_ERRORS)) {
        notifications.notifyFailure(describeFailure(error));
      }
      return throwError(() => error);
    }),
  );
};
