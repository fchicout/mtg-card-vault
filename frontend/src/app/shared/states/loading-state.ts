import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** Loading pattern: one spinner with an accessible label. */
@Component({
  selector: 'app-loading-state',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="spinner spinner-md" role="status" data-testid="loading">{{
    label()
  }}</span>`,
})
export class LoadingState {
  readonly label = input($localize`:@@state.loading:Loading…`);
}
