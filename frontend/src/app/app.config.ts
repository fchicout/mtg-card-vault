import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  ApplicationConfig,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';

import { provideApiConfiguration } from './api';
import { routes } from './app.routes';
import { AUTH_CONFIG, fetchAuthConfig } from './core/auth/auth-config';
import { authInterceptor } from './core/auth/auth.interceptor';
import { errorInterceptor } from './core/http/error.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    // Run-time settings of the identity provider (/config.json); the app still starts without them.
    provideAppInitializer(async () => {
      inject(AUTH_CONFIG).value = await fetchAuthConfig();
    }),
    provideHttpClient(
      // The error alert wraps the authentication handling: a 401 that renewal fixes raises no alert.
      withInterceptors([errorInterceptor, authInterceptor]),
    ),
    provideRouter(routes, withComponentInputBinding()),
    // Same origin: the reverse proxy (or the dev-server proxy) routes API paths to the back end.
    provideApiConfiguration(''),
  ],
};
