import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { ClrAlertModule } from '@clr/angular';

/** Error pattern: an inline alert with a retry action, for a view that cannot show its data. */
@Component({
  selector: 'app-error-state',
  imports: [ClrAlertModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <clr-alert clrAlertType="danger" [clrAlertClosable]="false">
      <clr-alert-item>
        <span class="alert-text" data-testid="error">{{ message() }}</span>
        <div class="alert-actions">
          <button type="button" class="btn alert-action" data-testid="retry" (click)="retry.emit()">
            <ng-container i18n="@@state.retry">Try again</ng-container>
          </button>
        </div>
      </clr-alert-item>
    </clr-alert>
  `,
})
export class ErrorState {
  readonly message = input.required<string>();
  readonly retry = output<void>();
}
