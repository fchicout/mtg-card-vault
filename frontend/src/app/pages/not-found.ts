import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';

import { EmptyState } from '../shared/states/empty-state';

@Component({
  selector: 'app-not-found-page',
  imports: [EmptyState, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h1 i18n="@@page.notfound.title">Page not found</h1>
    <app-empty-state [heading]="heading" icon="exclamation-circle">
      <ng-container i18n="@@page.notfound.text">The address does not match any page.</ng-container>
      <a actions routerLink="/" class="btn btn-primary" i18n="@@page.notfound.home"
        >Back to the start page</a
      >
    </app-empty-state>
  `,
})
export class NotFoundPage {
  protected readonly heading = $localize`:@@page.notfound.empty:We could not find that page`;
}
