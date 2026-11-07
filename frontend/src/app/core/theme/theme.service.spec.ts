import { TestBed } from '@angular/core/testing';

import { ThemeService } from './theme.service';

function setup(options: { saved?: string | null; prefersDark?: boolean; storageBroken?: boolean }) {
  const store: Record<string, string> = {};
  if (options.saved) {
    store['mtgvault.theme'] = options.saved;
  }
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation((key) => {
    if (options.storageBroken) throw new Error('blocked');
    return store[key] ?? null;
  });
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation((key, value) => {
    if (options.storageBroken) throw new Error('blocked');
    store[key] = value;
  });
  // The test DOM has no matchMedia: provide one that answers the dark-mode query.
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: vi.fn().mockReturnValue({ matches: !!options.prefersDark }),
  });
  return { store, service: TestBed.inject(ThemeService) };
}

describe('ThemeService', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    document.body.removeAttribute('cds-theme');
  });

  it('follows the system preference until the user chooses', () => {
    expect(setup({ prefersDark: true }).service.theme()).toBe('dark');
    expect(document.body.getAttribute('cds-theme')).toBe('dark');
  });

  it('is light when the system has no preference', () => {
    expect(setup({}).service.theme()).toBe('light');
    expect(document.body.getAttribute('cds-theme')).toBe('light');
  });

  it('prefers the saved choice over the system', () => {
    expect(setup({ saved: 'dark', prefersDark: false }).service.theme()).toBe('dark');
  });

  it('ignores a saved value it does not know', () => {
    expect(setup({ saved: 'purple' }).service.theme()).toBe('light');
  });

  it('toggles, applies the theme to the page and remembers it', () => {
    const { service, store } = setup({});
    service.toggle();
    expect(service.theme()).toBe('dark');
    expect(document.body.getAttribute('cds-theme')).toBe('dark');
    expect(store['mtgvault.theme']).toBe('dark');
    service.toggle();
    expect(service.theme()).toBe('light');
  });

  it('keeps working when the browser blocks storage', () => {
    const { service } = setup({ storageBroken: true, prefersDark: true });
    expect(service.theme()).toBe('dark');
    expect(() => service.toggle()).not.toThrow();
    expect(service.theme()).toBe('light');
  });
});
