import { HttpErrorResponse } from '@angular/common/http';
import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { Api, addVaultEntry, getCard, getCardPrintings } from '../api';
import { CardDetailPage } from './card-detail';

const detail = (extra: Record<string, unknown> = {}) => ({
  id: 'c1',
  name: 'Lightning Bolt',
  type_line: 'Instant',
  mana_cost: '{R}',
  oracle_text: 'Deal 3 damage.\nAnother line.',
  set_code: 'lea',
  set_name: 'Alpha',
  collector_number: '161',
  rarity: 'common',
  lang: 'en',
  layout: 'normal',
  colors: ['R'],
  finishes: ['nonfoil', 'foil'],
  image_normal: 'https://cards.scryfall.io/normal/x.jpg',
  image_small: null,
  faces: [],
  prices: { usd: '1.50', usd_foil: '3.00', eur: null },
  ...extra,
});
const printing = (id: string) => ({
  id,
  set_code: 'm10',
  set_name: 'Magic 2010',
  collector_number: '146',
  lang: 'en',
  rarity: 'common',
  finishes: ['nonfoil'],
  image_small: null,
  prices: {},
});

describe('CardDetailPage', () => {
  let invoke: ReturnType<typeof vi.fn>;
  let navigate: ReturnType<typeof vi.spyOn>;
  let answers: { card: unknown; printings: unknown; added?: unknown };

  async function render(): Promise<ComponentFixture<CardDetailPage>> {
    invoke.mockImplementation((fn: unknown) => {
      const answer =
        fn === getCard ? answers.card : fn === addVaultEntry ? answers.added : answers.printings;
      return answer instanceof HttpErrorResponse ? Promise.reject(answer) : Promise.resolve(answer);
    });
    TestBed.configureTestingModule({
      imports: [CardDetailPage],
      providers: [provideRouter([]), { provide: Api, useValue: { invoke } }],
    });
    navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const fixture = TestBed.createComponent(CardDetailPage);
    fixture.componentRef.setInput('id', 'c1');
    fixture.detectChanges();
    await fixture.whenStable();
    await new Promise<void>((resolve) => setTimeout(resolve));
    fixture.detectChanges();
    return fixture;
  }

  const q = (f: ComponentFixture<unknown>, s: string): HTMLElement | null =>
    (f.nativeElement as HTMLElement).querySelector(s);
  const all = (f: ComponentFixture<unknown>, s: string): HTMLElement[] =>
    Array.from((f.nativeElement as HTMLElement).querySelectorAll<HTMLElement>(s));

  beforeEach(() => {
    invoke = vi.fn();
    answers = {
      card: detail(),
      printings: { items: [printing('c1'), printing('c2')], page: 1, has_more: true, total: 40 },
    };
  });

  it('shows the card with image, text, set, number, rarity and prices', async () => {
    const f = await render();
    expect(q(f, '[data-testid="card-name"]')?.textContent).toBe('Lightning Bolt');
    expect(q(f, '[data-testid="art"]')?.getAttribute('alt')).toBe('Lightning Bolt');
    expect(q(f, '[data-testid="mana"]')?.textContent).toBe('{R}');
    expect(q(f, '[data-testid="oracle"]')?.textContent).toContain('Deal 3 damage.');
    expect(q(f, '[data-testid="set"]')?.textContent).toBe('Alpha (LEA)');
    expect(q(f, '[data-testid="number"]')?.textContent).toBe('161');
    expect(q(f, '[data-testid="prices"]')?.textContent).toContain('$1.50');
    expect(q(f, '[data-testid="prices"]')?.textContent).toContain('USD foil');
    expect(q(f, '[data-testid="prices"]')?.textContent).not.toContain('EUR');
  });

  it('says when there is no price instead of showing zero', async () => {
    answers.card = detail({ prices: {} });
    const f = await render();
    expect(q(f, '[data-testid="no-prices"]')).toBeTruthy();
  });

  it('shows every face of a double-faced card', async () => {
    answers.card = detail({
      faces: [
        { name: 'Delver', mana_cost: '{U}', type_line: 'Creature', oracle_text: 'Flip.' },
        { name: 'Insectile', mana_cost: null, type_line: 'Creature', oracle_text: 'Flying' },
      ],
    });
    const f = await render();
    expect(all(f, '[data-testid="face"]')).toHaveLength(2);
  });

  it('lists the printings with set, number, language and finishes and marks the shown one', async () => {
    const f = await render();
    const rows = all(f, '[data-testid="printing"]');
    expect(rows).toHaveLength(2);
    expect(rows[1].textContent).toContain('Magic 2010 (M10)');
    expect(rows[1].textContent).toContain('146');
    expect(rows[1].textContent).toContain('nonfoil');
    expect(rows[0].getAttribute('aria-current')).toBe('true');
    expect(rows[0].querySelector('[data-testid="select"]')).toBeNull();
  });

  it('opens another printing when it is selected', async () => {
    const f = await render();
    q(f, '[data-testid="select"]')!.click();
    expect(navigate).toHaveBeenCalledWith(['/catalogue', 'c2']);
  });

  it('pages through long printing lists', async () => {
    const f = await render();
    q(f, '[data-testid="printings-next"]')!.click();
    await f.whenStable();
    expect(invoke).toHaveBeenLastCalledWith(
      getCardPrintings,
      { card_id: 'c1', page: 2 },
      expect.anything(),
    );
  });

  it('adds the printing with the chosen quantity, condition and finish', async () => {
    const f = await render();
    q(f, '[data-testid="add"]')!.click();
    f.detectChanges();
    (q(f, '#entry-quantity') as HTMLInputElement).value = '2';
    (q(f, '#entry-condition') as HTMLSelectElement).value = 'LP';
    (q(f, '#entry-finish') as HTMLSelectElement).value = 'foil';
    answers.added = { id: 'e1', quantity: 2, condition: 'LP', finish: 'foil' };
    q(f, '[data-testid="entry-form"]')!.dispatchEvent(new Event('submit', { cancelable: true }));
    await f.whenStable();
    await new Promise<void>((resolve) => setTimeout(resolve));
    f.detectChanges();
    expect(invoke).toHaveBeenCalledWith(
      addVaultEntry,
      { body: { card_id: 'c1', quantity: 2, condition: 'LP', finish: 'foil' } },
      expect.anything(),
    );
    expect(q(f, '[data-testid="added"]')?.textContent).toContain('You now own 2');
  });

  it('only offers the finishes the printing exists in', async () => {
    answers.card = detail({ finishes: ['foil'] });
    const f = await render();
    q(f, '[data-testid="add"]')!.click();
    f.detectChanges();
    const options = Array.from((q(f, '#entry-finish') as HTMLSelectElement).options).map(
      (o) => o.value,
    );
    expect(options).toEqual(['foil']);
  });

  it('shows the server problems next to their fields and sends nothing invalid', async () => {
    const f = await render();
    q(f, '[data-testid="add"]')!.click();
    f.detectChanges();
    (q(f, '#entry-quantity') as HTMLInputElement).value = '0';
    q(f, '[data-testid="entry-form"]')!.dispatchEvent(new Event('submit', { cancelable: true }));
    f.detectChanges();
    expect(q(f, '[data-testid="quantity-error"]')?.textContent).toContain('1 to 9999');
    expect(invoke).not.toHaveBeenCalledWith(addVaultEntry, expect.anything(), expect.anything());

    (q(f, '#entry-quantity') as HTMLInputElement).value = '3';
    answers.added = new HttpErrorResponse({
      status: 422,
      error: {
        type: 'x',
        title: 'Unprocessable',
        status: 422,
        detail: 'd',
        errors: [{ field: 'finish', message: 'Allowed finishes for this printing: foil.' }],
      },
    });
    q(f, '[data-testid="entry-form"]')!.dispatchEvent(new Event('submit', { cancelable: true }));
    await f.whenStable();
    await new Promise<void>((resolve) => setTimeout(resolve));
    f.detectChanges();
    expect(q(f, '[data-testid="finish-error"]')?.textContent).toContain('Allowed finishes');
  });

  it.each([
    [404, 'could not find this card'],
    [503, 'temporarily unavailable'],
    [429, 'busy'],
    [500, 'could not be loaded'],
  ])('explains a %i answer for the card', async (status, words) => {
    answers.card = new HttpErrorResponse({ status });
    const f = await render();
    expect(q(f, '[data-testid="error"]')?.textContent).toContain(words);
  });

  it('keeps the card when only the printings fail', async () => {
    answers.printings = new HttpErrorResponse({ status: 503 });
    const f = await render();
    expect(q(f, '[data-testid="card-name"]')).toBeTruthy();
    expect(all(f, '[data-testid="error"]')).toHaveLength(1);
  });

  it('shows an empty state when a card has no printings', async () => {
    answers.printings = { items: [], page: 1, has_more: false, total: 0 };
    const f = await render();
    expect(q(f, '[data-testid="empty"]')?.textContent).toContain('No printings found');
  });
});
