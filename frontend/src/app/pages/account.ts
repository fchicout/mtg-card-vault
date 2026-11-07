import { ChangeDetectionStrategy, Component } from '@angular/core';

import { EmptyState } from '../shared/states/empty-state';

/** Placeholder: the feature arrives in its own milestone (docs/01 section 10). */
@Component({
  selector: 'app-account-page',
  imports: [EmptyState],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h1 i18n="@@page.account.title">Account</h1>
    <app-empty-state [heading]="emptyHeading" icon="user">
      <ng-container i18n="@@page.account.text"
        >Sign-in and account settings arrive with the identity feature.</ng-container
      >
    </app-empty-state>
  `,
})
export class AccountPage {
  protected readonly emptyHeading = $localize`:@@page.account.empty:Your account`;
}
