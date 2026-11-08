import { HttpContext } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  LOCALE_ID,
  computed,
  effect,
  inject,
  input,
  signal,
  untracked,
} from '@angular/core';

import { Api, getVaultSummary, type VaultSummaryDto } from '../../api';
import { HANDLES_OWN_ERRORS } from '../../core/http/error.interceptor';
import { formatMoney } from '../money/money';
import { ErrorState } from '../states/error-state';
import { LoadingState } from '../states/loading-state';

/**
 * What the collection is worth (US-021, FR-PRC-03): cards, entries and the value in USD and EUR.
 * Entries without a price add nothing to a value, so the panel says when it is a lower bound.
 * `version` changes whenever the vault does, which reloads the figures.
 */
@Component({
  selector: 'app-vault-summary',
  imports: [ErrorState, LoadingState],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    .summary {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem 2rem;
      margin: 1rem 0;
      padding: 1rem 1.25rem;
      border: 1px solid var(--clr-global-borders-color, #b3b3b3);
      border-radius: 3px;
    }
    .figure {
      display: flex;
      flex-direction: column;
    }
    .figure .value {
      font-size: 1.4rem;
      font-weight: 600;
    }
    .notes {
      flex-basis: 100%;
      margin: 0;
    }
  `,
  template: `
    <section aria-labelledby="summary-title" data-testid="summary">
      <h2 id="summary-title" class="clr-sr-only" i18n="@@summary.title">Collection value</h2>
      @if (problem(); as message) {
        <app-error-state [message]="message" (retry)="load()" />
      } @else if (data(); as s) {
        <div class="summary">
          <div class="figure">
            <span i18n="@@summary.cards">Cards</span>
            <span class="value" data-testid="summary-cards">{{ s.total_cards }}</span>
          </div>
          <div class="figure">
            <span i18n="@@summary.entries">Entries</span>
            <span class="value" data-testid="summary-entries">{{ s.entries }}</span>
          </div>
          <div class="figure">
            <span i18n="@@summary.valueUsd">Value (USD)</span>
            <span class="value" data-testid="summary-usd">{{ usd() }}</span>
          </div>
          <div class="figure">
            <span i18n="@@summary.valueEur">Value (EUR)</span>
            <span class="value" data-testid="summary-eur">{{ eur() }}</span>
          </div>
          @if (s.entries > 0 && (s.lower_bound_usd || s.lower_bound_eur)) {
            <p class="notes" data-testid="lower-bound" role="note">
              <ng-container i18n="@@summary.lowerBound"
                >These values are a lower bound: entries without a price are not
                counted.</ng-container
              >
              @if (s.lower_bound_usd) {
                <span data-testid="unpriced-usd"> {{ unpricedUsd }}: {{ s.unpriced_usd }}.</span>
              }
              @if (s.lower_bound_eur) {
                <span data-testid="unpriced-eur"> {{ unpricedEur }}: {{ s.unpriced_eur }}.</span>
              }
            </p>
          }
        </div>
      } @else if (loading()) {
        <app-loading-state />
      }
    </section>
  `,
})
export class VaultSummary {
  private readonly api = inject(Api);
  private readonly locale = inject(LOCALE_ID);

  /** Changes when the vault changes; each new value reloads the summary. */
  readonly version = input(0);

  protected readonly data = signal<VaultSummaryDto | null>(null);
  protected readonly loading = signal(false);
  protected readonly problem = signal<string | null>(null);
  protected readonly unpricedUsd = $localize`:@@summary.unpricedUsd:Entries without a USD price`;
  protected readonly unpricedEur = $localize`:@@summary.unpricedEur:Entries without a EUR price`;
  protected readonly usd = computed(() => formatMoney(this.data()?.value_usd, 'USD', this.locale));
  protected readonly eur = computed(() => formatMoney(this.data()?.value_eur, 'EUR', this.locale));

  constructor() {
    effect(() => {
      this.version();
      untracked(() => void this.load());
    });
  }

  protected async load(): Promise<void> {
    this.loading.set(true);
    this.problem.set(null);
    try {
      this.data.set(
        await this.api.invoke(getVaultSummary, {}, new HttpContext().set(HANDLES_OWN_ERRORS, true)),
      );
    } catch {
      this.problem.set(
        $localize`:@@summary.failed:The collection value could not be loaded. Try again.`,
      );
    } finally {
      this.loading.set(false);
    }
  }
}
