import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  ApplicationConfig,
  Injector,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';

import { provideApiConfiguration } from './api';
import { routes } from './app.routes';
import { AUTH_CONFIG, fetchAuthConfig } from './core/auth/auth-config';
import { authInterceptor } from './core/auth/auth.interceptor';
import { AuthService } from './core/auth/auth.service';
import { errorInterceptor } from './core/http/error.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    // Run-time settings of the identity provider (/config.json); the app still starts without them.
    provideAppInitializer(async () => {
      const holder = inject(AUTH_CONFIG);
      const injector = inject(Injector);
      holder.value = await fetchAuthConfig();
      // A reload drops the in-memory tokens: a visitor who was signed in goes through the
      // provider again before any page renders (the provider still has its own session).
      const { pathname, search } = window.location;
      if (!pathname.startsWith('/callback')) {
        await injector.get(AuthService).restore(pathname + search);
      }
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
