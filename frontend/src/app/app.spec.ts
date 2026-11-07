import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { provideApiConfiguration } from './api';
import { App } from './app';

describe('App', () => {
  let fixture: ComponentFixture<App>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideApiConfiguration('')],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(App);
  });

  afterEach(() => http.verify());

  const text = (testId: string): string | undefined =>
    (fixture.nativeElement as HTMLElement)
      .querySelector(`[data-testid="${testId}"]`)
      ?.textContent?.trim();

  /** Lets the component's awaited Promise continuation run, then renders the result. */
  async function settle(): Promise<void> {
    await fixture.whenStable();
    await new Promise<void>((resolve) => setTimeout(resolve, 0));
    await fixture.whenStable();
    fixture.detectChanges();
  }

  it('shows a spinner while the greeting is loading', () => {
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('.spinner')).toBeTruthy();
    http.expectOne('/hello');
  });

  it('renders the greeting returned by the API', async () => {
    fixture.detectChanges();
    http.expectOne('/hello').flush({ message: 'Hello, MTG Vault!' });
    await settle();
    expect(text('greeting')).toBe('Hello, MTG Vault!');
    expect(text('error')).toBeUndefined();
  });

  it('shows an accessible error alert when the API fails', async () => {
    fixture.detectChanges();
    http.expectOne('/hello').flush('boom', { status: 500, statusText: 'Server Error' });
    await settle();
    expect(text('error')).toBe('The API could not be reached.');
    expect(text('greeting')).toBeUndefined();
  });
});
