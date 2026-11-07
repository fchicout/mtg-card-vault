import { ChangeDetectionStrategy, Component } from '@angular/core';

import { EmptyState } from '../shared/states/empty-state';

/** Placeholder: the feature arrives in its own milestone (docs/01 section 10). */
@Component({
  selector: 'app-vault-page',
  imports: [EmptyState],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h1 i18n="@@page.vault.title">Vault</h1>
    <app-empty-state [heading]="emptyHeading" icon="library">
      <ng-container i18n="@@page.vault.text"
        >Cards you add will appear here. This page is ready for the vault feature.</ng-container
      >
    </app-empty-state>
  `,
})
export class VaultPage {
  protected readonly emptyHeading = $localize`:@@page.vault.empty:Your vault is empty`;
}
