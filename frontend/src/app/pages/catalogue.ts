import { ChangeDetectionStrategy, Component } from '@angular/core';

import { EmptyState } from '../shared/states/empty-state';

/** Placeholder: the feature arrives in its own milestone (docs/01 section 10). */
@Component({
  selector: 'app-catalogue-page',
  imports: [EmptyState],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h1 i18n="@@page.catalogue.title">Catalogue</h1>
    <app-empty-state [heading]="emptyHeading" icon="search">
      <ng-container i18n="@@page.catalogue.text"
        >Searching Scryfall cards arrives with the catalogue feature.</ng-container
      >
    </app-empty-state>
  `,
})
export class CataloguePage {
  protected readonly emptyHeading = $localize`:@@page.catalogue.empty:Nothing to search yet`;
}
