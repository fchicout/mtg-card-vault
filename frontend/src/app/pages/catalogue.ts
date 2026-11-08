import { HttpContext, HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  signal,
  untracked,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { Api, searchCards, type CardPage } from '../api';
import { HANDLES_OWN_ERRORS } from '../core/http/error.interceptor';
import { EmptyState } from '../shared/states/empty-state';
import { ErrorState } from '../shared/states/error-state';
import { LoadingState } from '../shared/states/loading-state';

const COLORS: readonly { code: string; label: string }[] = [
  { code: 'W', label: $localize`:@@color.white:White` },
  { code: 'U', label: $localize`:@@color.blue:Blue` },
  { code: 'B', label: $localize`:@@color.black:Black` },
  { code: 'R', label: $localize`:@@color.red:Red` },
  { code: 'G', label: $localize`:@@color.green:Green` },
  { code: 'C', label: $localize`:@@color.colourless:Colourless` },
];
const RARITIES = ['common', 'uncommon', 'rare', 'mythic'] as const;
type Rarity = (typeof RARITIES)[number];
interface Filters {
  q?: string;
  set?: string;
  colors?: string;
  type?: string;
  rarity?: Rarity;
}

/**
 * Catalogue search (US-012, US-013, UC-10). The search lives in the address (?q=&set=&colors=&type=
 * &rarity=&page=), so a search can be shared and the browser's back button works.
 */
@Component({
  selector: 'app-catalogue-page',
  imports: [EmptyState, ErrorState, LoadingState, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    .filters {
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem 1.5rem;
      align-items: flex-end;
    }
    .colors {
      display: flex;
      gap: 0.75rem;
      flex-wrap: wrap;
      border: 0;
      padding: 0;
      margin: 0;
    }
    .card-grid {
      list-style: none;
      padding: 0;
      display: grid;
      gap: 1rem;
      grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
    }
    .card-grid a {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      text-decoration: none;
    }
    .card-grid img {
      width: 100%;
      max-width: 146px;
      height: auto;
      aspect-ratio: 488 / 680;
      object-fit: contain;
    }
    .no-image {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 146px;
      aspect-ratio: 488 / 680;
      border: 1px dashed currentcolor;
    }
    .meta {
      font-size: 0.75rem;
      opacity: 0.85;
    }
    .pager {
      display: flex;
      gap: 1rem;
      align-items: center;
      margin-top: 1rem;
    }
  `,
  template: `
    <h1 i18n="@@page.catalogue.title">Catalogue</h1>

    <form class="filters" (submit)="search($event)" data-testid="search-form" role="search">
      <div class="clr-form-control">
        <label for="q" class="clr-control-label" i18n="@@catalogue.q">Card name</label>
        <input
          id="q"
          name="q"
          class="clr-input"
          type="search"
          maxlength="100"
          [value]="q() ?? ''"
          data-testid="q"
        />
      </div>
      <div class="clr-form-control">
        <label for="set" class="clr-control-label" i18n="@@catalogue.set">Set code</label>
        <input
          id="set"
          name="set"
          class="clr-input"
          maxlength="6"
          size="6"
          [value]="set() ?? ''"
          data-testid="set"
        />
      </div>
      <div class="clr-form-control">
        <label for="type" class="clr-control-label" i18n="@@catalogue.type">Type</label>
        <input
          id="type"
          name="type"
          class="clr-input"
          maxlength="40"
          [value]="type() ?? ''"
          data-testid="type"
        />
      </div>
      <div class="clr-form-control">
        <label for="rarity" class="clr-control-label" i18n="@@catalogue.rarity">Rarity</label>
        <select id="rarity" name="rarity" class="clr-select" data-testid="rarity">
          <option value="" [selected]="!rarity()" i18n="@@catalogue.anyRarity">Any</option>
          @for (r of rarities; track r) {
            <option [value]="r" [selected]="rarity() === r">{{ r }}</option>
          }
        </select>
      </div>
      <fieldset class="colors">
        <legend class="clr-control-label" i18n="@@catalogue.colors">Colours</legend>
        @for (c of colorChoices; track c.code) {
          <label class="clr-control-label">
            <input
              type="checkbox"
              name="colors"
              [value]="c.code"
              [checked]="hasColor(c.code)"
              [attr.data-testid]="'color-' + c.code"
            />
            {{ c.label }}
          </label>
        }
      </fieldset>
      <div>
        <button
          type="submit"
          class="btn btn-primary"
          data-testid="search"
          i18n="@@catalogue.search"
        >
          Search
        </button>
        @if (hasFilters()) {
          <button
            type="button"
            class="btn btn-link"
            data-testid="clear"
            (click)="clear()"
            i18n="@@catalogue.clear"
          >
            Clear
          </button>
        }
      </div>
    </form>

    <section aria-live="polite" class="results">
      @if (loading()) {
        <app-loading-state />
      } @else if (problem(); as message) {
        <app-error-state [message]="message" (retry)="load()" />
      } @else if (result(); as page) {
        @if (page.items.length === 0) {
          <app-empty-state [heading]="noCards" icon="search">
            <ng-container i18n="@@catalogue.noneText">
              Try another spelling, fewer words or other filters.
            </ng-container>
          </app-empty-state>
        } @else {
          <ul class="card-grid" data-testid="results">
            @for (card of page.items; track card.id) {
              <li>
                <a [routerLink]="['/catalogue', card.id]" data-testid="result">
                  @if (card.image_small; as src) {
                    <img [src]="src" [alt]="card.name" width="146" height="204" loading="lazy" />
                  } @else {
                    <span class="no-image" i18n="@@catalogue.noImage">No image</span>
                  }
                  <strong>{{ card.name }}</strong>
                  <span class="meta">{{ card.type_line }}</span>
                  <span class="meta">{{ card.set_name }} ({{ card.set_code.toUpperCase() }})</span>
                </a>
              </li>
            }
          </ul>
          <nav class="pager" aria-label="Pages" i18n-aria-label="@@catalogue.pages">
            <button
              type="button"
              class="btn btn-sm"
              data-testid="prev"
              [disabled]="pageNumber() <= 1"
              (click)="goTo(pageNumber() - 1)"
              i18n="@@catalogue.prev"
            >
              Previous page
            </button>
            <span data-testid="page">{{ pageNumber() }}</span>
            <button
              type="button"
              class="btn btn-sm"
              data-testid="next"
              [disabled]="!page.has_more"
              (click)="goTo(pageNumber() + 1)"
              i18n="@@catalogue.next"
            >
              Next page
            </button>
          </nav>
        }
      } @else {
        <app-empty-state [heading]="startHeading" icon="search">
          <ng-container i18n="@@catalogue.startText">
            Search all Magic: The Gathering cards by name, then narrow them with filters.
          </ng-container>
        </app-empty-state>
      }
    </section>
  `,
})
export class CataloguePage {
  private readonly api = inject(Api);
  private readonly router = inject(Router);

  // Bound from the query string (withComponentInputBinding).
  readonly q = input<string | undefined>();
  readonly set = input<string | undefined>();
  readonly colors = input<string | undefined>();
  readonly type = input<string | undefined>();
  readonly rarity = input<string | undefined>();
  readonly page = input<string | undefined>();

  protected readonly colorChoices = COLORS;
  protected readonly rarities = RARITIES;
  protected readonly noCards = $localize`:@@catalogue.none:No cards found`;
  protected readonly startHeading = $localize`:@@catalogue.start:Find a card`;

  protected readonly loading = signal(false);
  protected readonly result = signal<CardPage | null>(null);
  protected readonly problem = signal<string | null>(null);

  protected readonly pageNumber = computed(() => Math.max(1, Number(this.page()) || 1));
  protected readonly hasFilters = computed(
    () => !!(this.q() || this.set() || this.colors() || this.type() || this.rarity()),
  );

  constructor() {
    effect(() => {
      // Any change of the address triggers a new search.
      this.q();
      this.set();
      this.colors();
      this.type();
      this.rarity();
      this.pageNumber();
      untracked(() => void this.load());
    });
  }

  protected hasColor(code: string): boolean {
    return (this.colors() ?? '').toUpperCase().includes(code);
  }

  protected async load(): Promise<void> {
    if (!this.hasFilters()) {
      this.result.set(null);
      this.problem.set(null);
      return;
    }
    this.loading.set(true);
    this.problem.set(null);
    try {
      const context = new HttpContext().set(HANDLES_OWN_ERRORS, true);
      const rarity = this.rarity() as Rarity | undefined;
      this.result.set(
        await this.api.invoke(
          searchCards,
          {
            q: this.q() || null,
            set: this.set() || null,
            colors: this.colors() || null,
            type: this.type() || null,
            rarity: rarity ?? null,
            page: this.pageNumber(),
          },
          context,
        ),
      );
    } catch (error) {
      this.result.set(null);
      this.problem.set(this.describe(error));
    } finally {
      this.loading.set(false);
    }
  }

  protected search(event: Event): void {
    event.preventDefault();
    const data = new FormData(event.target as HTMLFormElement);
    const text = (name: string): string | undefined => {
      const raw = data.get(name);
      const value = typeof raw === 'string' ? raw.trim() : '';
      return value === '' ? undefined : value;
    };
    const colors = data.getAll('colors').map(String).join('');
    const filters: Filters = {
      q: text('q'),
      set: text('set')?.toLowerCase(),
      colors: colors || undefined,
      type: text('type'),
      rarity: text('rarity') as Rarity | undefined,
    };
    void this.router.navigate(['/catalogue'], { queryParams: { ...filters, page: undefined } });
  }

  protected clear(): void {
    void this.router.navigate(['/catalogue']);
  }

  protected goTo(page: number): void {
    void this.router.navigate(['/catalogue'], {
      queryParams: { page: page > 1 ? page : undefined },
      queryParamsHandling: 'merge',
    });
  }

  private describe(error: unknown): string {
    const status = error instanceof HttpErrorResponse ? error.status : 0;
    switch (status) {
      case 503:
        return $localize`:@@catalogue.unavailable:The catalogue is temporarily unavailable. Please try again in a moment.`;
      case 429:
        return $localize`:@@catalogue.busy:The catalogue is busy right now. Wait a moment and try again.`;
      case 422:
        return $localize`:@@catalogue.invalid:That search is not valid. Check the words and filters.`;
      default:
        return $localize`:@@catalogue.failed:The search could not be completed. Try again.`;
    }
  }
}
