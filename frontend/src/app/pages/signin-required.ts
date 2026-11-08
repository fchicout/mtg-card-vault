import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';

import { AuthService } from '../core/auth/auth.service';
import { EmptyState } from '../shared/states/empty-state';

/** Shown when a protected page is opened without a session, or when a sign-in failed (US-001). */
@Component({
  selector: 'app-signin-required-page',
  imports: [EmptyState],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h1 i18n="@@page.signin.title">Sign in required</h1>
    <app-empty-state [heading]="heading()" icon="user">
      @if (!auth.configured) {
        <ng-container i18n="@@page.signin.unavailable"
          >Signing in is not available right now. Please contact the administrator.</ng-container
        >
      } @else if (didFail()) {
        <ng-container i18n="@@page.signin.failed"
          >The sign-in was cancelled or could not be completed. You can try again.</ng-container
        >
      } @else {
        <ng-container i18n="@@page.signin.text">You need to sign in to see this page.</ng-container>
      }
      <div actions>
        @if (auth.configured) {
          <button
            type="button"
            class="btn btn-primary"
            data-testid="signin-retry"
            (click)="signIn()"
          >
            @if (didFail()) {
              <ng-container i18n="@@page.signin.retry">Try again</ng-container>
            } @else {
              <ng-container i18n="@@page.signin.action">Sign in</ng-container>
            }
          </button>
        }
      </div>
    </app-empty-state>
  `,
})
export class SigninRequiredPage {
  protected readonly auth = inject(AuthService);

  /** Bound from the query string (withComponentInputBinding). */
  readonly returnUrl = input<string | undefined>();
  readonly failed = input<string | undefined>();
  protected readonly didFail = computed(() => this.failed() === '1');

  protected readonly heading = computed(() =>
    this.didFail()
      ? $localize`:@@page.signin.failedHeading:Sign-in did not complete`
      : $localize`:@@page.signin.empty:Please sign in`,
  );

  protected signIn(): void {
    const target = this.returnUrl();
    void this.auth.signIn(target?.startsWith('/') && !target.startsWith('//') ? target : '/');
  }
}
