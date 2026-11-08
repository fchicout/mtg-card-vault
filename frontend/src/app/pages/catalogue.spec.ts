import { HttpErrorResponse } from '@angular/common/http';
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { Api, type CardPage } from '../api';
import { CataloguePage } from './catalogue';

const card = (name: string, extra: Record<string, unknown> = {}) => ({
  id: `id-${name.replaceAll(' ', '-')}`,
  name,
  type_line: 'Instant',
  set_code: 'lea',
  set_name: 'Limited Edition Alpha',
  collector_number: '161',
  rarity: 'common',
  image_small: `https://cards.scryfall.io/small/${name}.jpg`,
  ...extra,
});
const page = (items: unknown[], has_more = false): CardPage =>
  ({ items, page: 1, has_more, total: items.length }) as CardPage;

describe('CataloguePage', () => {
  let invoke: ReturnType<typeof vi.fn>;
  let navigate: ReturnType<typeof vi.spyOn>;

  async function render(
    inputs: Record<string, string> = {},
  ): Promise<ComponentFixture<CataloguePage>> {
    TestBed.configureTestingModule({
      imports: [CataloguePage],
      providers: [provideRouter([]), { provide: Api, useValue: { invoke } }],
    });
    navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const fixture = TestBed.createComponent(CataloguePage);
    for (const [name, value] of Object.entries(inputs)) {
      fixture.componentRef.setInput(name, value);
    }
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture;
  }

  const text = (f: ComponentFixture<unknown>): string =>
    (f.nativeElement as HTMLElement).textContent ?? '';
  const q = (f: ComponentFixture<unknown>, selector: string): HTMLElement | null =>
    (f.nativeElement as HTMLElement).querySelector(selector);

  beforeEach(() => {
    invoke = vi.fn();
  });

  it('starts with an invitation and calls nothing', async () => {
    const f = await render();
    expect(text(f)).toContain('Find a card');
    expect(invoke).not.toHaveBeenCalled();
  });

  it('shows matching cards with image, name, type line and set', async () => {
    invoke.mockResolvedValue(page([card('Lightning Bolt')]));
    const f = await render({ q: 'bolt' });
    const result = q(f, '[data-testid="result"]')!;
    expect(result.textContent).toContain('Lightning Bolt');
    expect(result.textContent).toContain('Instant');
    expect(result.textContent).toContain('Limited Edition Alpha (LEA)');
    const img = result.querySelector('img')!;
    expect(img.getAttribute('alt')).toBe('Lightning Bolt');
    expect(img.getAttribute('src')).toContain('cards.scryfall.io');
    expect(result.getAttribute('href')).toBe('/catalogue/id-Lightning-Bolt');
  });

  it('sends the filters from the address to the API', async () => {
    invoke.mockResolvedValue(page([card('Shivan Dragon')]));
    await render({
      q: 'dragon',
      colors: 'R',
      rarity: 'rare',
      set: 'lea',
      type: 'Creature',
      page: '2',
    });
    expect(invoke.mock.calls[0][1]).toEqual({
      q: 'dragon',
      set: 'lea',
      colors: 'R',
      type: 'Creature',
      rarity: 'rare',
      page: 2,
    });
  });

  it('says so when nothing matches', async () => {
    invoke.mockResolvedValue(page([]));
    const f = await render({ q: 'zzzz' });
    expect(text(f)).toContain('No cards found');
  });

  it('shows a friendly message, not a stack trace, when the catalogue is down', async () => {
    invoke.mockRejectedValue(new HttpErrorResponse({ status: 503 }));
    const f = await render({ q: 'bolt' });
    expect(q(f, '[data-testid="error"]')?.textContent).toContain('temporarily unavailable');
  });

  it.each([
    [429, 'busy'],
    [422, 'not valid'],
    [500, 'could not be completed'],
  ])('explains a %i answer', async (status, words) => {
    invoke.mockRejectedValue(new HttpErrorResponse({ status }));
    const f = await render({ q: 'bolt' });
    expect(q(f, '[data-testid="error"]')?.textContent).toContain(words);
  });

  it('retries the search', async () => {
    invoke.mockRejectedValueOnce(new HttpErrorResponse({ status: 503 }));
    invoke.mockResolvedValueOnce(page([card('Lightning Bolt')]));
    const f = await render({ q: 'bolt' });
    q(f, '[data-testid="retry"]')!.click();
    await f.whenStable();
    f.detectChanges();
    expect(q(f, '[data-testid="results"]')).toBeTruthy();
  });

  it('keeps the search in the address when submitted', async () => {
    invoke.mockResolvedValue(page([]));
    const f = await render({ q: 'old' });
    (q(f, '#q') as HTMLInputElement).value = 'Dragon';
    (q(f, '#set') as HTMLInputElement).value = 'LEA';
    (q(f, '[data-testid="color-R"]') as HTMLInputElement).checked = true;
    (q(f, '[data-testid="color-G"]') as HTMLInputElement).checked = true;
    (q(f, '#rarity') as HTMLSelectElement).value = 'rare';
    q(f, '[data-testid="search-form"]')!.dispatchEvent(new Event('submit', { cancelable: true }));
    expect(navigate).toHaveBeenCalledWith(['/catalogue'], {
      queryParams: {
        q: 'Dragon',
        set: 'lea',
        colors: 'RG',
        type: undefined,
        rarity: 'rare',
        page: undefined,
      },
    });
  });

  it('pages forward and back through the address', async () => {
    invoke.mockResolvedValue(page([card('A')], true));
    const f = await render({ q: 'a', page: '2' });
    q(f, '[data-testid="next"]')!.click();
    expect(navigate).toHaveBeenLastCalledWith(['/catalogue'], {
      queryParams: { page: 3 },
      queryParamsHandling: 'merge',
    });
    q(f, '[data-testid="prev"]')!.click();
    expect(navigate).toHaveBeenLastCalledWith(['/catalogue'], {
      queryParams: { page: undefined },
      queryParamsHandling: 'merge',
    });
    expect(q(f, '[data-testid="prev"]')).toBeTruthy();
  });

  it('disables paging at the ends and clears the filters', async () => {
    invoke.mockResolvedValue(page([card('A')], false));
    const f = await render({ q: 'a' });
    expect((q(f, '[data-testid="prev"]') as HTMLButtonElement).disabled).toBe(true);
    expect((q(f, '[data-testid="next"]') as HTMLButtonElement).disabled).toBe(true);
    q(f, '[data-testid="clear"]')!.click();
    expect(navigate).toHaveBeenLastCalledWith(['/catalogue']);
  });

  it('shows a placeholder for a card without an image', async () => {
    invoke.mockResolvedValue(page([card('Odd', { image_small: null })]));
    const f = await render({ q: 'odd' });
    expect(text(f)).toContain('No image');
  });
});
