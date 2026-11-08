import '../testing/resize-observer';
import { HttpErrorResponse } from '@angular/common/http';
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { Api, editVaultEntry, listVaultEntries, removeVaultEntry } from '../api';
import { VaultPage } from './vault';

const item = (name: string, extra: Record<string, unknown> = {}) => ({
  id: `e-${name}`,
  quantity: 2,
  condition: 'NM',
  finish: 'foil',
  created_at: '2026-11-08T10:00:00Z',
  updated_at: '2026-11-08T10:00:00Z',
  card: {
    id: `c-${name}`,
    name,
    type_line: 'Instant',
    set_code: 'lea',
    set_name: 'Alpha',
    collector_number: '161',
    rarity: 'common',
    image_small: 'https://cards.scryfall.io/s.jpg',
  },
  available_finishes: ['nonfoil', 'foil'],
  unit_price: '3.00',
  prices_updated_at: '2026-11-08T09:00:00Z',
  prices_stale: false,
  ...extra,
});
const list = (items: unknown[], total = items.length) => ({ items, page: 1, page_size: 50, total });

describe('VaultPage', () => {
  let invoke: ReturnType<typeof vi.fn>;
  let navigate: ReturnType<typeof vi.spyOn>;

  async function render(inputs: Record<string, string> = {}): Promise<ComponentFixture<VaultPage>> {
    TestBed.configureTestingModule({
      imports: [VaultPage],
      providers: [provideRouter([]), { provide: Api, useValue: { invoke } }],
    });
    navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const fixture = TestBed.createComponent(VaultPage);
    for (const [name, value] of Object.entries(inputs)) {
      fixture.componentRef.setInput(name, value);
    }
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture;
  }
  const q = (f: ComponentFixture<unknown>, s: string): HTMLElement | null =>
    (f.nativeElement as HTMLElement).querySelector(s);
  const all = (f: ComponentFixture<unknown>, s: string): HTMLElement[] =>
    Array.from((f.nativeElement as HTMLElement).querySelectorAll<HTMLElement>(s));
  const settle = async (f: ComponentFixture<unknown>): Promise<void> => {
    await f.whenStable();
    await new Promise<void>((resolve) => setTimeout(resolve));
    f.detectChanges();
  };

  beforeEach(() => {
    invoke = vi.fn();
  });

  it('lists entries with image, name, set, number, finish, condition, quantity and price', async () => {
    invoke.mockResolvedValue(list([item('Lightning Bolt')]));
    const f = await render();
    const row = q(f, '[data-testid="entry"]')!;
    for (const text of ['Lightning Bolt', 'Alpha (LEA)', '161', 'foil', 'NM', '2', '$3.00']) {
      expect(row.textContent).toContain(text);
    }
    expect(row.querySelector('img')?.getAttribute('alt')).toBe('Lightning Bolt');
    expect(q(f, '[data-testid="total"]')?.textContent).toContain('1');
  });

  it('shows the empty state with both ways to add cards', async () => {
    invoke.mockResolvedValue(list([]));
    const f = await render();
    expect(q(f, '[data-testid="empty"]')?.textContent).toContain('Your vault is empty');
    expect(q(f, '[data-testid="empty-scan"]')?.getAttribute('href')).toBe('/scan');
    expect(q(f, '[data-testid="empty-catalogue"]')?.getAttribute('href')).toBe('/catalogue');
  });

  it('says nothing matched instead of showing the empty-vault state when filtering', async () => {
    invoke.mockResolvedValue(list([]));
    const f = await render({ q: 'zzz' });
    expect(q(f, '[data-testid="empty"]')?.textContent).toContain('No entries match');
  });

  it('marks outdated prices and unknown ones', async () => {
    invoke.mockResolvedValue(
      list([item('A', { prices_stale: true }), item('B', { unit_price: null })]),
    );
    const f = await render();
    expect(all(f, '[data-testid="stale"]')).toHaveLength(1);
    expect(all(f, '[data-testid="entry-price"]')[1].textContent).toContain('unknown');
  });

  it('sends the address to the API, with paging', async () => {
    invoke.mockResolvedValue(list([item('A')], 250));
    await render({
      q: 'bolt',
      set: 'lea',
      colors: 'R',
      rarity: 'rare',
      type: 'Instant',
      sort: 'name',
      dir: 'asc',
      page: '3',
      page_size: '100',
    });
    expect(invoke.mock.calls[0][1]).toEqual({
      page: 3,
      page_size: 100,
      q: 'bolt',
      set: 'lea',
      colors: 'R',
      rarity: 'rare',
      type: 'Instant',
      sort: 'name',
      dir: 'asc',
    });
  });

  it('pages: 250 entries at 50 per page are 5 pages', async () => {
    invoke.mockResolvedValue(list([item('A')], 250));
    const f = await render();
    expect(q(f, '[data-testid="page"]')?.textContent).toContain('1 / 5');
    q(f, '[data-testid="next"]')!.click();
    expect(navigate).toHaveBeenLastCalledWith(['/vault'], {
      queryParams: { page: 2 },
      queryParamsHandling: 'merge',
    });
    expect((q(f, '[data-testid="prev"]') as HTMLButtonElement).disabled).toBe(true);
  });

  it('keeps search and filters in the address', async () => {
    invoke.mockResolvedValue(list([]));
    const f = await render();
    (q(f, '#vq') as HTMLInputElement).value = 'Bolt';
    (q(f, '#vset') as HTMLInputElement).value = 'MH2';
    (q(f, '[data-testid="color-R"]') as HTMLInputElement).checked = true;
    q(f, '[data-testid="vault-filters"]')!.dispatchEvent(new Event('submit', { cancelable: true }));
    expect(navigate).toHaveBeenCalledWith(['/vault'], {
      queryParams: expect.objectContaining({ q: 'Bolt', set: 'mh2', colors: 'R', page: undefined }),
    });
  });

  it('sorts by a column and toggles the direction', async () => {
    invoke.mockResolvedValue(list([item('A')]));
    const f = await render({ sort: 'name', dir: 'asc' });
    expect(q(f, '[data-testid="sort-name"]')!.parentElement?.getAttribute('aria-sort')).toBe(
      'ascending',
    );
    q(f, '[data-testid="sort-name"]')!.click();
    expect(navigate).toHaveBeenLastCalledWith(['/vault'], {
      queryParams: { sort: 'name', dir: 'desc', page: undefined },
      queryParamsHandling: 'merge',
    });
    q(f, '[data-testid="sort-price"]')!.click();
    expect(navigate).toHaveBeenLastCalledWith(['/vault'], {
      queryParams: { sort: 'price', dir: 'asc', page: undefined },
      queryParamsHandling: 'merge',
    });
  });

  it('shows an error with retry when the vault cannot be loaded', async () => {
    invoke.mockRejectedValueOnce(new HttpErrorResponse({ status: 500 }));
    invoke.mockResolvedValueOnce(list([item('A')]));
    const f = await render();
    expect(q(f, '[data-testid="error"]')?.textContent).toContain('could not be loaded');
    q(f, '[data-testid="retry"]')!.click();
    await settle(f);
    expect(q(f, '[data-testid="entries"]')).toBeTruthy();
  });

  it('edits an entry and reloads the list', async () => {
    invoke.mockImplementation((fn: unknown) =>
      Promise.resolve(fn === editVaultEntry ? item('A', { quantity: 5 }) : list([item('A')])),
    );
    const f = await render();
    q(f, '[data-testid="edit"]')!.click();
    f.detectChanges();
    (q(f, '#entry-quantity') as HTMLInputElement).value = '5';
    q(f, '[data-testid="entry-form"]')!.dispatchEvent(new Event('submit', { cancelable: true }));
    await settle(f);
    expect(invoke).toHaveBeenCalledWith(
      editVaultEntry,
      { entry_id: 'e-A', body: { quantity: 5, condition: 'NM', finish: 'foil' } },
      expect.anything(),
    );
    expect(q(f, '[data-testid="notice"]')?.textContent).toContain('Saved');
  });

  it('tells the user when an edit merged two entries', async () => {
    invoke.mockImplementation((fn: unknown) =>
      Promise.resolve(
        fn === editVaultEntry ? item('A', { id: 'other', quantity: 5 }) : list([item('A')]),
      ),
    );
    const f = await render();
    q(f, '[data-testid="edit"]')!.click();
    f.detectChanges();
    q(f, '[data-testid="entry-form"]')!.dispatchEvent(new Event('submit', { cancelable: true }));
    await settle(f);
    expect(q(f, '[data-testid="notice"]')?.textContent).toContain('Merged');
    expect(q(f, '[data-testid="notice"]')?.textContent).toContain('5');
  });

  it('shows a validation problem next to the field and keeps the dialog open', async () => {
    invoke.mockImplementation((fn: unknown) =>
      fn === editVaultEntry
        ? Promise.reject(
            new HttpErrorResponse({
              status: 422,
              error: {
                type: 'x',
                title: 't',
                status: 422,
                detail: 'd',
                errors: [{ field: 'quantity', message: 'Too many.' }],
              },
            }),
          )
        : Promise.resolve(list([item('A')])),
    );
    const f = await render();
    q(f, '[data-testid="edit"]')!.click();
    f.detectChanges();
    q(f, '[data-testid="entry-form"]')!.dispatchEvent(new Event('submit', { cancelable: true }));
    await settle(f);
    expect(q(f, '[data-testid="quantity-error"]')?.textContent).toContain('Too many.');
  });

  it('removes only after confirmation', async () => {
    invoke.mockImplementation((fn: unknown) =>
      Promise.resolve(fn === removeVaultEntry ? undefined : list([item('A')])),
    );
    const f = await render();
    q(f, '[data-testid="remove"]')!.click();
    f.detectChanges();
    expect(q(f, '[data-testid="remove-question"]')?.textContent).toContain(
      'Lightning Bolt'.replace('Lightning Bolt', 'A'),
    );
    expect(invoke).not.toHaveBeenCalledWith(removeVaultEntry, expect.anything(), expect.anything());
    q(f, '[data-testid="remove-confirm"]')!.click();
    await settle(f);
    expect(invoke).toHaveBeenCalledWith(removeVaultEntry, { entry_id: 'e-A' }, expect.anything());
    expect(q(f, '[data-testid="notice"]')?.textContent).toContain('removed');
  });

  it('says not found and refreshes when the entry is already gone', async () => {
    invoke.mockImplementation((fn: unknown) =>
      fn === removeVaultEntry
        ? Promise.reject(new HttpErrorResponse({ status: 404 }))
        : Promise.resolve(list([item('A')])),
    );
    const f = await render();
    q(f, '[data-testid="remove"]')!.click();
    f.detectChanges();
    q(f, '[data-testid="remove-confirm"]')!.click();
    await settle(f);
    expect(q(f, '[data-testid="notice"]')?.textContent).toContain('not found');
    expect(invoke.mock.calls.filter((c) => c[0] === listVaultEntries)).toHaveLength(2);
  });
});
