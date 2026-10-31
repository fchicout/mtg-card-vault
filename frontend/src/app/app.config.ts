import { provideHttpClient } from '@angular/common/http';
import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';

import { provideApiConfiguration } from './api';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideHttpClient(),
    // Same origin: the reverse proxy (or the dev-server proxy) routes API paths to the back end.
    provideApiConfiguration(''),
  ],
};
