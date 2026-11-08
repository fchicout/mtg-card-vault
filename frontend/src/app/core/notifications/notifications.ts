import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { ClrAlertModule } from '@clr/angular';

import type { AppNotification } from './notification.service';
import { NotificationService } from './notification.service';

/** Alerts at the top of the content area; a failure offers its technical details on demand. */
@Component({
  selector: 'app-notifications',
  imports: [ClrAlertModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @for (item of service.notifications(); track item.id) {
      <clr-alert
        [clrAlertType]="item.kind"
        [clrAlertClosable]="true"
        (clrAlertClosedChange)="service.dismiss(item.id)"
      >
        <clr-alert-item>
          <span class="alert-text" data-testid="alert-message">{{ item.message }}</span>
        </clr-alert-item>
        @if (item.failure; as failure) {
          @if (failure.fields.length) {
            <clr-alert-item>
              <ul class="list alert-text" data-testid="alert-fields">
                @for (field of failure.fields; track field.field) {
                  <li>
                    <strong>{{ field.field }}</strong
                    >: {{ field.message }}
                  </li>
                }
              </ul>
            </clr-alert-item>
          }
          <clr-alert-item>
            <details class="alert-text" data-testid="alert-details">
              <summary i18n="@@alert.details">Support details</summary>
              <p>
                <span i18n="@@alert.status">Status</span>: {{ failure.status || '-' }} ·
                {{ failure.technical }}
              </p>
              @if (failure.correlationId) {
                <p>
                  <span i18n="@@alert.correlation">Correlation id</span>:
                  <code data-testid="correlation-id">{{ failure.correlationId }}</code>
                </p>
              }
            </details>
          </clr-alert-item>
        }
      </clr-alert>
    }
  `,
})
export class Notifications {
  protected readonly service = inject(NotificationService);

  protected readonly trackById = (item: AppNotification): number => item.id;
}
