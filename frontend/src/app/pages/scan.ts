import { ChangeDetectionStrategy, Component } from '@angular/core';

import { EmptyState } from '../shared/states/empty-state';

/** Placeholder: the feature arrives in its own milestone (docs/01 section 10). */
@Component({
  selector: 'app-scan-page',
  imports: [EmptyState],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h1 i18n="@@page.scan.title">Scan</h1>
    <app-empty-state [heading]="emptyHeading" icon="camera">
      <ng-container i18n="@@page.scan.text"
        >Adding cards with your camera arrives with the scanning feature.</ng-container
      >
    </app-empty-state>
  `,
})
export class ScanPage {
  protected readonly emptyHeading = $localize`:@@page.scan.empty:The scanner is not available yet`;
}
