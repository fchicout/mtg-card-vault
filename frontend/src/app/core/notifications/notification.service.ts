import { Injectable, signal } from '@angular/core';

import type { FailureDetails } from '../http/problem';

export type NotificationKind = 'danger' | 'warning' | 'success' | 'info';

export interface AppNotification {
  readonly id: number;
  readonly kind: NotificationKind;
  readonly message: string;
  readonly failure: FailureDetails | null;
}

const MAX_VISIBLE = 4;

/** The one place that holds the alerts shown at the top of the page. */
@Injectable({ providedIn: 'root' })
export class NotificationService {
  private nextId = 1;
  private readonly store = signal<readonly AppNotification[]>([]);

  readonly notifications = this.store.asReadonly();

  notify(kind: NotificationKind, message: string, failure: FailureDetails | null = null): void {
    const notification = { id: this.nextId++, kind, message, failure };
    this.store.update((all) => [...all, notification].slice(-MAX_VISIBLE));
  }

  /** Shows a failed request; the same failure twice in a row is shown once. */
  notifyFailure(failure: FailureDetails): void {
    const last = this.store().at(-1);
    if (last?.failure?.correlationId && last.failure.correlationId === failure.correlationId) {
      return;
    }
    this.notify('danger', failure.message, failure);
  }

  dismiss(id: number): void {
    this.store.update((all) => all.filter((n) => n.id !== id));
  }

  clear(): void {
    this.store.set([]);
  }
}
