import { ChangeDetectionStrategy, Component, computed, input, output, signal } from '@angular/core';

import type { Condition, Finish } from '../../api';

export const CONDITIONS: readonly { code: Condition; label: string }[] = [
  { code: 'NM', label: $localize`:@@condition.nm:Near mint (NM)` },
  { code: 'LP', label: $localize`:@@condition.lp:Lightly played (LP)` },
  { code: 'MP', label: $localize`:@@condition.mp:Moderately played (MP)` },
  { code: 'HP', label: $localize`:@@condition.hp:Heavily played (HP)` },
  { code: 'DMG', label: $localize`:@@condition.dmg:Damaged (DMG)` },
];

export interface EntryValues {
  quantity: number;
  condition: Condition;
  finish: Finish;
}

/**
 * Quantity, condition and finish of a vault entry (US-005, US-007). The finish choices are only the
 * ones the printing exists in. Server-side field problems are shown next to their field.
 */
@Component({
  selector: 'app-entry-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    form {
      display: grid;
      gap: 1rem;
    }
    .error {
      color: var(--clr-forms-invalid-color, #c92100);
      margin: 0;
    }
    .actions {
      display: flex;
      gap: 0.5rem;
      justify-content: flex-end;
    }
  `,
  template: `
    <form (submit)="submit($event)" novalidate data-testid="entry-form">
      <div class="clr-form-control">
        <label for="entry-quantity" class="clr-control-label" i18n="@@entry.quantity"
          >Quantity</label
        >
        <input
          id="entry-quantity"
          name="quantity"
          class="clr-input"
          type="number"
          min="1"
          max="9999"
          step="1"
          required
          [value]="quantity()"
          data-testid="quantity"
          [attr.aria-invalid]="shown()['quantity'] ? 'true' : null"
          [attr.aria-describedby]="shown()['quantity'] ? 'quantity-error' : null"
        />
        @if (shown()['quantity']; as message) {
          <p class="error" id="quantity-error" data-testid="quantity-error">{{ message }}</p>
        }
      </div>
      <div class="clr-form-control">
        <label for="entry-condition" class="clr-control-label" i18n="@@entry.condition"
          >Condition</label
        >
        <select id="entry-condition" name="condition" class="clr-select" data-testid="condition">
          @for (c of conditions; track c.code) {
            <option [value]="c.code" [selected]="c.code === condition()">{{ c.label }}</option>
          }
        </select>
        @if (shown()['condition']; as message) {
          <p class="error" data-testid="condition-error">{{ message }}</p>
        }
      </div>
      <div class="clr-form-control">
        <label for="entry-finish" class="clr-control-label" i18n="@@entry.finish">Finish</label>
        <select
          id="entry-finish"
          name="finish"
          class="clr-select"
          data-testid="finish"
          [attr.aria-invalid]="shown()['finish'] ? 'true' : null"
        >
          @for (f of finishes(); track f) {
            <option [value]="f" [selected]="f === finish()">{{ f }}</option>
          }
        </select>
        @if (shown()['finish']; as message) {
          <p class="error" data-testid="finish-error">{{ message }}</p>
        }
      </div>
      @if (shown()['_']; as message) {
        <p class="error" role="alert" data-testid="form-error">{{ message }}</p>
      }
      <div class="actions">
        <button
          type="button"
          class="btn btn-outline"
          data-testid="cancel"
          (click)="cancelled.emit()"
          i18n="@@entry.cancel"
        >
          Cancel
        </button>
        <button type="submit" class="btn btn-primary" data-testid="submit" [disabled]="busy()">
          {{ submitLabel() }}
        </button>
      </div>
    </form>
  `,
})
export class EntryForm {
  readonly finishes = input.required<readonly string[]>();
  readonly submitLabel = input.required<string>();
  readonly quantity = input(1);
  readonly condition = input<Condition>('NM');
  readonly finish = input<string | undefined>();
  readonly errors = input<Record<string, string>>({});
  readonly busy = input(false);

  readonly submitted = output<EntryValues>();
  readonly cancelled = output<void>();

  protected readonly conditions = CONDITIONS;

  protected submit(event: Event): void {
    event.preventDefault();
    const data = new FormData(event.target as HTMLFormElement);
    const quantity = Number(data.get('quantity'));
    const finish = data.get('finish');
    const condition = data.get('condition');
    if (typeof finish !== 'string' || typeof condition !== 'string') {
      return;
    }
    // Nothing is sent for an unusable quantity: the field shows its hint instead.
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > 9999) {
      this.local.set({
        quantity: $localize`:@@entry.quantityHint:Use a whole number from 1 to 9999.`,
      });
      return;
    }
    this.local.set({});
    this.submitted.emit({ quantity, condition: condition as Condition, finish: finish as Finish });
  }

  private readonly local = signal<Record<string, string>>({});
  protected readonly shown = computed(() => ({ ...this.local(), ...this.errors() }));
}
