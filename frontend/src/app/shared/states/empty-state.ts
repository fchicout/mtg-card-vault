import { CUSTOM_ELEMENTS_SCHEMA, ChangeDetectionStrategy, Component, input } from '@angular/core';

/** Empty pattern: a headline, an explanation (projected) and optional actions (projected). */
@Component({
  selector: 'app-empty-state',
  changeDetection: ChangeDetectionStrategy.OnPush,
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  template: `
    <section class="card" data-testid="empty">
      <div class="card-block">
        <h2 class="card-title">
          @if (icon(); as shape) {
            <cds-icon [attr.shape]="shape" aria-hidden="true"></cds-icon>
          }
          {{ heading() }}
        </h2>
        <div class="card-text"><ng-content /></div>
      </div>
      <div class="card-footer"><ng-content select="[actions]" /></div>
    </section>
  `,
})
export class EmptyState {
  readonly heading = input.required<string>();
  readonly icon = input<string | null>(null);
}
