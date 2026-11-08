import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { provideApiConfiguration } from '../api';
import { NotificationService } from '../core/notifications/notification.service';
import { errorInterceptor } from '../core/http/error.interceptor';
import { HomePage } from './home';

describe('HomePage', () => {
  let fixture: ComponentFixture<HomePage>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HomePage],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideApiConfiguration('')],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(HomePage);
  });

  afterEach(() => http.verify());

  const text = (testId: string): string | undefined =>
    (fixture.nativeElement as HTMLElement)
      .querySelector(`[data-testid="${testId}"]`)
      ?.textContent?.trim();

  async function settle(): Promise<void> {
    await fixture.whenStable();
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
    await fixture.whenStable();
    fixture.detectChanges();
  }

  it('shows the loading pattern first', () => {
    fixture.detectChanges();
    expect(text('loading')).toBe('Loading…');
    http.expectOne('/hello');
  });

  it('renders the greeting returned by the API', async () => {
    fixture.detectChanges();
    http.expectOne('/hello').flush({ message: 'Hello, MTG Vault!' });
    await settle();
    expect(text('greeting')).toBe('Hello, MTG Vault!');
    expect(text('error')).toBeUndefined();
  });

  it('shows the error pattern when the API fails and loads again on retry', async () => {
    fixture.detectChanges();
    http.expectOne('/hello').flush('boom', { status: 500, statusText: 'Server Error' });
    await settle();
    expect(text('error')).toBe('The greeting could not be loaded.');
    expect(text('greeting')).toBeUndefined();

    (fixture.nativeElement as HTMLElement)
      .querySelector<HTMLButtonElement>('[data-testid="retry"]')!
      .click();
    http.expectOne('/hello').flush({ message: 'Back again' });
    await settle();
    expect(text('greeting')).toBe('Back again');
  });

  it('a failure also raises the global alert, which carries the correlation id', async () => {
    TestBed.resetTestingModule();
    await TestBed.configureTestingModule({
      imports: [HomePage],
      providers: [
        provideHttpClient(withInterceptors([errorInterceptor])),
        provideHttpClientTesting(),
        provideApiConfiguration(''),
      ],
    }).compileComponents();
    const local = TestBed.createComponent(HomePage);
    const controller = TestBed.inject(HttpTestingController);
    local.detectChanges();
    controller.expectOne('/hello').flush(
      {
        type: 't',
        title: 'Internal Server Error',
        status: 500,
        detail: 'x',
        correlation_id: 'corr-9',
      },
      { status: 500, statusText: 'Server Error' },
    );
    await local.whenStable();
    const [alert] = TestBed.inject(NotificationService).notifications();
    expect(alert.message).toContain('on our side');
    expect(alert.failure?.correlationId).toBe('corr-9');
  });
});
