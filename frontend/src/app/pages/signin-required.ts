import { ChangeDetectionStrategy, Component } from '@angular/core';

import { EmptyState } from '../shared/states/empty-state';

/** Placeholder for the page shown when a protected page is opened without a session (US-001). */
@Component({
  selector: 'app-signin-required-page',
  imports: [EmptyState],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h1 i18n="@@page.signin.title">Sign in required</h1>
    <app-empty-state [heading]="heading" icon="user">
      <ng-container i18n="@@page.signin.text">You need to sign in to see this page.</ng-container>
    </app-empty-state>
  `,
})
export class SigninRequiredPage {
  protected readonly heading = $localize`:@@page.signin.empty:Please sign in`;
}
