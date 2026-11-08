import { TestBed } from '@angular/core/testing';

import type { FailureDetails } from '../http/problem';
import { NotificationService } from './notification.service';

const failure = (correlationId: string | null): FailureDetails => ({
  status: 500,
  message: 'Something went wrong',
  technical: 'x',
  correlationId,
  fields: [],
  retryAfterSeconds: null,
});

describe('NotificationService', () => {
  let service: NotificationService;

  beforeEach(() => {
    service = TestBed.inject(NotificationService);
  });

  it('adds, dismisses and clears notifications', () => {
    service.notify('success', 'Saved');
    service.notify('info', 'FYI');
    expect(service.notifications().map((n) => n.message)).toEqual(['Saved', 'FYI']);

    service.dismiss(service.notifications()[0].id);
    expect(service.notifications().map((n) => n.message)).toEqual(['FYI']);

    service.clear();
    expect(service.notifications()).toEqual([]);
  });

  it('keeps only the four newest', () => {
    for (let i = 1; i <= 6; i++) {
      service.notify('info', `n${i}`);
    }
    expect(service.notifications().map((n) => n.message)).toEqual(['n3', 'n4', 'n5', 'n6']);
  });

  it('shows the same failure twice in a row only once', () => {
    service.notifyFailure(failure('same'));
    service.notifyFailure(failure('same'));
    service.notifyFailure(failure('other'));
    service.notifyFailure(failure(null));
    service.notifyFailure(failure(null));
    expect(service.notifications()).toHaveLength(4);
  });
});
