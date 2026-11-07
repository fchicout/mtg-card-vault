import { TestBed } from '@angular/core/testing';

import { NotificationService } from './notification.service';
import { Notifications } from './notifications';

describe('Notifications', () => {
  function render() {
    const fixture = TestBed.createComponent(Notifications);
    fixture.detectChanges();
    return {
      fixture,
      element: fixture.nativeElement as HTMLElement,
      service: TestBed.inject(NotificationService),
    };
  }

  it('renders nothing without notifications', () => {
    expect(render().element.querySelectorAll('clr-alert')).toHaveLength(0);
  });

  it('shows a failure in plain language with the correlation id and fields in the details', () => {
    const { fixture, element, service } = render();
    service.notifyFailure({
      status: 422,
      message: 'Some of the information is not valid.',
      technical: 'Unprocessable Content: The request is invalid.',
      correlationId: 'corr-42',
      fields: [{ field: 'quantity', message: 'must be positive' }],
      retryAfterSeconds: null,
    });
    fixture.detectChanges();

    expect(element.querySelector('[data-testid="alert-message"]')?.textContent).toBe(
      'Some of the information is not valid.',
    );
    expect(element.querySelector('[data-testid="alert-fields"]')?.textContent).toContain(
      'quantity',
    );
    expect(element.querySelector('[data-testid="alert-details"] summary')?.textContent).toBe(
      'Support details',
    );
    expect(element.querySelector('[data-testid="correlation-id"]')?.textContent).toBe('corr-42');
  });

  it('shows a plain message without details', () => {
    const { fixture, element, service } = render();
    service.notify('success', 'Saved');
    fixture.detectChanges();
    expect(element.querySelector('[data-testid="alert-message"]')?.textContent).toBe('Saved');
    expect(element.querySelector('[data-testid="alert-details"]')).toBeNull();
  });
});
