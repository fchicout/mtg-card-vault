import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { provideApiConfiguration } from './api';
import { App } from './app';
import { routes } from './app.routes';

describe('App shell', () => {
  let element: HTMLElement;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApiConfiguration(''),
        provideRouter(routes),
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    element = fixture.nativeElement as HTMLElement;
  });

  it('shows the product name in the header', () => {
    expect(element.querySelector('.header .title')?.textContent?.trim()).toBe('MTG Card Vault');
  });

  it('offers the four sections in the navigation, as links', () => {
    const links = [...element.querySelectorAll('clr-vertical-nav a')].map((a) => [
      a.textContent?.trim(),
      a.getAttribute('href'),
    ]);
    expect(links).toEqual([
      ['Vault', '/vault'],
      ['Catalogue', '/catalogue'],
      ['Scan', '/scan'],
      ['Account', '/account'],
    ]);
    expect(element.querySelector('clr-vertical-nav')?.getAttribute('aria-label')).toBe(
      'Main navigation',
    );
  });

  it('always shows the Scryfall attribution and the unofficial Fan Content notice (NFR-LEG-01)', () => {
    const footer = element.querySelector('[data-testid="footer"]');
    expect(footer?.querySelector('a[href="https://scryfall.com"]')?.textContent).toContain(
      'Scryfall',
    );
    expect(footer?.textContent).toContain('unofficial Fan Content');
    expect(footer?.textContent).toContain('not approved or endorsed by Wizards of the Coast');
    expect(footer?.querySelector('a')?.getAttribute('rel')).toContain('noopener');
  });

  it('has one main landmark with the notifications area inside', () => {
    expect(element.querySelectorAll('main')).toHaveLength(1);
    expect(element.querySelector('main app-notifications')).toBeTruthy();
  });

  it('the theme switch also works with the Space key, like a real button', () => {
    const toggle = element.querySelector<HTMLAnchorElement>('[data-testid="theme-toggle"]')!;
    const before = document.body.getAttribute('cds-theme');
    toggle.dispatchEvent(
      new KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true }),
    );
    expect(document.body.getAttribute('cds-theme')).not.toBe(before);
  });

  it('switches between the light and the dark Clarity theme', () => {
    const toggle = element.querySelector<HTMLAnchorElement>('[data-testid="theme-toggle"]')!;
    const before = document.body.getAttribute('cds-theme');
    toggle.click();
    expect(document.body.getAttribute('cds-theme')).not.toBe(before);
  });
});

describe('routes', () => {
  let harness: RouterTestingHarness;
  let http: HttpTestingController;

  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApiConfiguration(''),
        provideRouter(routes),
      ],
    });
    http = TestBed.inject(HttpTestingController);
    harness = await RouterTestingHarness.create();
  });

  it.each([
    ['/vault', 'Vault'],
    ['/catalogue', 'Catalogue'],
    ['/scan', 'Scan'],
    ['/account', 'Account'],
    ['/signin-required', 'Sign in required'],
    ['/nothing-here', 'Page not found'],
  ])('%s is a lazy page with the heading "%s"', async (url, heading) => {
    await harness.navigateByUrl(url);
    expect(harness.routeNativeElement?.querySelector('h1')?.textContent?.trim()).toBe(heading);
  });

  it('sets a distinct document title per page', async () => {
    await harness.navigateByUrl('/vault');
    expect(document.title).toBe('Vault - MTG Card Vault');
    await harness.navigateByUrl('/nothing-here');
    expect(document.title).toBe('Page not found - MTG Card Vault');
  });

  it('the 404 page offers a way back', async () => {
    await harness.navigateByUrl('/nothing-here');
    expect(harness.routeNativeElement?.querySelector('a[href="/"]')).toBeTruthy();
  });

  it('the start page shows the skeleton greeting until /hello goes away', async () => {
    const navigation = harness.navigateByUrl('/');
    await navigation;
    http.expectOne('/hello').flush({ message: 'Hello, MTG Vault!' });
    await harness.fixture.whenStable();
    await new Promise<void>((resolve) => setTimeout(resolve));
    harness.detectChanges();
    expect(
      harness.routeNativeElement?.querySelector('[data-testid="greeting"]')?.textContent?.trim(),
    ).toBe('Hello, MTG Vault!');
  });
});
