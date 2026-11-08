import { HttpContext } from '@angular/common/http';
import { Injectable, computed, effect, inject, signal, untracked } from '@angular/core';

import { Api, getMe, type Me } from '../../api';
import { HANDLES_OWN_ERRORS } from '../http/error.interceptor';
import { AuthService } from './auth.service';

/** The signed-in user's profile from the API (provisioned on the first call, US-004). */
@Injectable({ providedIn: 'root' })
export class ProfileService {
  private readonly api = inject(Api);
  private readonly auth = inject(AuthService);
  private readonly loaded = signal<Me | null>(null);

  readonly profile = this.loaded.asReadonly();
  /** The best name we have: the profile, else the token claim, else nothing. */
  readonly displayName = computed(() => this.loaded()?.display_name ?? this.auth.displayName());

  constructor() {
    effect(() => {
      if (this.auth.authenticated()) {
        untracked(() => void this.load());
      } else {
        this.loaded.set(null);
      }
    });
  }

  private async load(): Promise<void> {
    try {
      // A failure here must not raise an alert: the header falls back to the token's name.
      const context = new HttpContext().set(HANDLES_OWN_ERRORS, true);
      this.loaded.set(await this.api.invoke(getMe, undefined, context));
    } catch {
      this.loaded.set(null);
    }
  }
}
