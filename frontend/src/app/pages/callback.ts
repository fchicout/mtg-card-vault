import { ChangeDetectionStrategy, Component, OnInit, inject } from '@angular/core';
import { Router } from '@angular/router';

import { AuthService } from '../core/auth/auth.service';
import { LoadingState } from '../shared/states/loading-state';

/** The redirect target of the identity provider: finishes the sign-in, then opens the saved route. */
@Component({
  selector: 'app-callback-page',
  imports: [LoadingState],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<app-loading-state />`,
})
export class CallbackPage implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  async ngOnInit(): Promise<void> {
    try {
      const target = await this.auth.completeSignIn();
      await this.router.navigateByUrl(target, { replaceUrl: true });
    } catch {
      // Cancelled, expired or tampered sign-in: explain it on the sign-in page, with a retry.
      await this.router.navigate(['/signin-required'], {
        queryParams: { failed: '1' },
        replaceUrl: true,
      });
    }
  }
}
