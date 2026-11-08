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

import {
  Api,
  getCard,
  getCardPrintings,
  type CardDetail,
  type PricesDto,
  type PrintingPage,
} from '../api';
import { HANDLES_OWN_ERRORS } from '../core/http/error.interceptor';
import { EmptyState } from '../shared/states/empty-state';
import { ErrorState } from '../shared/states/error-state';
import { LoadingState } from '../shared/states/loading-state';

interface PriceRow {
  label: string;
  value: string;
}

/** Card detail with every printing (US-014, UC-10). The image is shown whole, never cropped. */
@Component({
  selector: 'app-card-detail-page',
  imports: [EmptyState, ErrorState, LoadingState, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    .layout {
      display: flex;
      flex-wrap: wrap;
      gap: 1.5rem;
      align-items: flex-start;
    }
    .art {
      width: min(100%, 336px);
      height: auto;
      aspect-ratio: 488 / 680;
      object-fit: contain;
    }
    .info {
      flex: 1 1 18rem;
      min-width: 0;
    }
    .face + .face {
      margin-top: 1rem;
      border-top: 1px solid currentcolor;
      padding-top: 1rem;
    }
    .oracle {
      white-space: pre-line;
    }
    .printings {
      margin-top: 2rem;
    }
  `,
  template: `
    <p>
      <a routerLink="/catalogue" data-testid="back" i18n="@@detail.back">Back to the catalogue</a>
    </p>
    @if (loading()) {
      <app-loading-state />
    } @else if (problem(); as message) {
      <app-error-state [message]="message" (retry)="load()" />
    } @else if (card(); as c) {
      <h1 data-testid="card-name">{{ c.name }}</h1>
      <div class="layout">
        @if (c.image_normal; as src) {
          <img class="art" [src]="src" [alt]="c.name" width="336" height="468" data-testid="art" />
        }
        <div class="info">
          @if (c.faces.length > 1) {
            @for (face of c.faces; track face.name) {
              <section class="face" data-testid="face">
                <h2>
                  {{ face.name }} <small>{{ face.mana_cost }}</small>
                </h2>
                <p>{{ face.type_line }}</p>
                <p class="oracle">{{ face.oracle_text }}</p>
              </section>
            }
          } @else {
            <p data-testid="mana">{{ c.mana_cost }}</p>
            <p data-testid="type-line">{{ c.type_line }}</p>
            <p class="oracle" data-testid="oracle">{{ c.oracle_text }}</p>
          }
          <dl>
            <dt i18n="@@detail.set">Set</dt>
            <dd data-testid="set">{{ c.set_name }} ({{ c.set_code.toUpperCase() }})</dd>
            <dt i18n="@@detail.number">Collector number</dt>
            <dd data-testid="number">{{ c.collector_number }}</dd>
            <dt i18n="@@detail.rarity">Rarity</dt>
            <dd data-testid="rarity">{{ c.rarity }}</dd>
            <dt i18n="@@detail.finishes">Finishes</dt>
            <dd>{{ c.finishes.join(', ') }}</dd>
          </dl>
          <h2 i18n="@@detail.prices">Prices</h2>
          @if (priceRows().length === 0) {
            <p data-testid="no-prices" i18n="@@detail.noPrices">
              No price is known for this printing.
            </p>
          } @else {
            <table class="table table-compact" data-testid="prices">
              <tbody>
                @for (row of priceRows(); track row.label) {
                  <tr>
                    <th scope="row">{{ row.label }}</th>
                    <td>{{ row.value }}</td>
                  </tr>
                }
              </tbody>
            </table>
          }
          <p>
            <button
              type="button"
              class="btn btn-primary"
              disabled
              data-testid="add"
              aria-describedby="add-hint"
              i18n="@@detail.add"
            >
              Add to vault
            </button>
            <span id="add-hint" class="p5" i18n="@@detail.addHint">
              Adding cards arrives with the vault feature.
            </span>
          </p>
        </div>
      </div>

      <section class="printings" aria-labelledby="printings-title">
        <h2 id="printings-title" i18n="@@detail.printings">Printings</h2>
        @if (printingsProblem(); as message) {
          <app-error-state [message]="message" (retry)="loadPrintings()" />
        } @else if (printings(); as list) {
          @if (list.items.length === 0) {
            <app-empty-state [heading]="noPrintings" icon="search" />
          } @else {
            <table class="table table-compact" data-testid="printings">
              <thead>
                <tr>
                  <th i18n="@@detail.colSet">Set</th>
                  <th i18n="@@detail.colNumber">Number</th>
                  <th i18n="@@detail.colLang">Language</th>
                  <th i18n="@@detail.colFinishes">Finishes</th>
                  <th i18n="@@detail.colRarity">Rarity</th>
                  <th><span class="clr-sr-only" i18n="@@detail.colAction">Select</span></th>
                </tr>
              </thead>
              <tbody>
                @for (p of list.items; track p.id) {
                  <tr data-testid="printing" [attr.aria-current]="p.id === c.id ? 'true' : null">
                    <td>{{ p.set_name }} ({{ p.set_code.toUpperCase() }})</td>
                    <td>{{ p.collector_number }}</td>
                    <td>{{ p.lang }}</td>
                    <td>{{ p.finishes.join(', ') }}</td>
                    <td>{{ p.rarity }}</td>
                    <td>
                      @if (p.id === c.id) {
                        <span i18n="@@detail.current">Shown</span>
                      } @else {
                        <button
                          type="button"
                          class="btn btn-sm btn-link"
                          data-testid="select"
                          (click)="select(p.id)"
                        >
                          <ng-container i18n="@@detail.select">Select</ng-container>
                          <span class="clr-sr-only">
                            {{ p.set_name }} {{ p.collector_number }}</span
                          >
                        </button>
                      }
                    </td>
                  </tr>
                }
              </tbody>
            </table>
            <div class="pager">
              <button
                type="button"
                class="btn btn-sm"
                data-testid="printings-prev"
                [disabled]="printingsPage() <= 1"
                (click)="movePrintings(-1)"
                i18n="@@detail.prev"
              >
                Previous page
              </button>
              <button
                type="button"
                class="btn btn-sm"
                data-testid="printings-next"
                [disabled]="!list.has_more"
                (click)="movePrintings(1)"
                i18n="@@detail.next"
              >
                Next page
              </button>
            </div>
          }
        }
      </section>
    }
  `,
})
export class CardDetailPage {
  private readonly api = inject(Api);
  private readonly router = inject(Router);

  /** The route parameter :id (withComponentInputBinding). */
  readonly id = input.required<string>();

  protected readonly noPrintings = $localize`:@@detail.noPrintings:No printings found`;
  protected readonly loading = signal(false);
  protected readonly card = signal<CardDetail | null>(null);
  protected readonly problem = signal<string | null>(null);
  protected readonly printings = signal<PrintingPage | null>(null);
  protected readonly printingsProblem = signal<string | null>(null);
  protected readonly printingsPage = signal(1);

  protected readonly priceRows = computed<PriceRow[]>(() => this.rows(this.card()?.prices));

  constructor() {
    effect(() => {
      this.id();
      untracked(() => {
        this.printingsPage.set(1);
        void this.load();
      });
    });
  }

  protected async load(): Promise<void> {
    this.loading.set(true);
    this.problem.set(null);
    try {
      this.card.set(await this.api.invoke(getCard, { card_id: this.id() }, this.own()));
    } catch (error) {
      this.card.set(null);
      this.problem.set(this.describe(error));
      return;
    } finally {
      this.loading.set(false);
    }
    await this.loadPrintings();
  }

  protected async loadPrintings(): Promise<void> {
    this.printingsProblem.set(null);
    try {
      this.printings.set(
        await this.api.invoke(
          getCardPrintings,
          { card_id: this.id(), page: this.printingsPage() },
          this.own(),
        ),
      );
    } catch (error) {
      this.printings.set(null);
      this.printingsProblem.set(this.describe(error));
    }
  }

  protected select(printingId: string): void {
    void this.router.navigate(['/catalogue', printingId]);
  }

  protected movePrintings(step: number): void {
    this.printingsPage.update((page) => Math.max(1, page + step));
    void this.loadPrintings();
  }

  private own(): HttpContext {
    return new HttpContext().set(HANDLES_OWN_ERRORS, true);
  }

  private rows(prices: PricesDto | undefined): PriceRow[] {
    if (!prices) {
      return [];
    }
    const labelled: [string, string | null | undefined, string][] = [
      [$localize`:@@price.usd:USD`, prices.usd, '$'],
      [$localize`:@@price.usdFoil:USD foil`, prices.usd_foil, '$'],
      [$localize`:@@price.usdEtched:USD etched`, prices.usd_etched, '$'],
      [$localize`:@@price.eur:EUR`, prices.eur, '€'],
      [$localize`:@@price.eurFoil:EUR foil`, prices.eur_foil, '€'],
      [$localize`:@@price.eurEtched:EUR etched`, prices.eur_etched, '€'],
    ];
    return labelled
      .filter(([, value]) => value !== null && value !== undefined)
      .map(([label, value, symbol]) => ({ label, value: `${symbol}${value}` }));
  }

  private describe(error: unknown): string {
    const status = error instanceof HttpErrorResponse ? error.status : 0;
    switch (status) {
      case 404:
        return $localize`:@@detail.notFound:We could not find this card.`;
      case 503:
        return $localize`:@@detail.unavailable:The catalogue is temporarily unavailable. Please try again in a moment.`;
      case 429:
        return $localize`:@@detail.busy:The catalogue is busy right now. Wait a moment and try again.`;
      default:
        return $localize`:@@detail.failed:The card could not be loaded. Try again.`;
    }
  }
}
