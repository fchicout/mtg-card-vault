import { provideHttpClient } from '@angular/common/http';
import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';

import { provideRouter } from '@angular/router';

import { provideApiConfiguration } from './api';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideHttpClient(),
    provideRouter(routes),
    // Same origin: the reverse proxy (or the dev-server proxy) routes API paths to the back end.
    provideApiConfiguration(''),
  ],
};
