import { HttpClient, HttpContext, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { NotificationService } from '../notifications/notification.service';
import { HANDLES_OWN_ERRORS, errorInterceptor } from './error.interceptor';

describe('errorInterceptor', () => {
  let http: HttpClient;
  let controller: HttpTestingController;
  let notifications: NotificationService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([errorInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    controller = TestBed.inject(HttpTestingController);
    notifications = TestBed.inject(NotificationService);
  });

  afterEach(() => controller.verify());

  /** Runs a GET that fails and returns the error the caller still receives. */
  async function failWith(status: number, body: object | string | null, context?: HttpContext) {
    const result = new Promise<unknown>((resolve) =>
      http.get('/x', { context }).subscribe({ error: resolve }),
    );
    controller.expectOne('/x').flush(body, { status, statusText: 'Err' });
    return result;
  }

  it('shows a plain-language alert with the correlation id and fields from a problem document', async () => {
    await failWith(422, {
      type: 'urn:mtgvault:problem:validation-failed',
      title: 'Unprocessable Content',
      status: 422,
      detail: 'The request is invalid.',
      correlation_id: 'corr-1',
      errors: [{ field: 'name', message: 'is required' }],
    });
    const [alert] = notifications.notifications();
    expect(alert.kind).toBe('danger');
    expect(alert.message).toContain('not valid');
    expect(alert.failure?.correlationId).toBe('corr-1');
    expect(alert.failure?.fields).toEqual([{ field: 'name', message: 'is required' }]);
  });

  it('still rejects, so the caller can react', async () => {
    const error = await failWith(500, 'boom');
    expect(error).toMatchObject({ status: 500 });
  });

  it('does not alert when the request handles its own errors', async () => {
    await failWith(500, 'boom', new HttpContext().set(HANDLES_OWN_ERRORS, true));
    expect(notifications.notifications()).toEqual([]);
  });

  it('does not alert on success', () => {
    http.get('/x').subscribe();
    controller.expectOne('/x').flush({ ok: true });
    expect(notifications.notifications()).toEqual([]);
  });

  it('reports an unreachable server', async () => {
    const result = new Promise<unknown>((resolve) => http.get('/x').subscribe({ error: resolve }));
    controller.expectOne('/x').error(new ProgressEvent('error'));
    await result;
    expect(notifications.notifications()[0].message).toContain('cannot be reached');
  });
});
