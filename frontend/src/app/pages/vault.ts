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
import { ClrModalModule } from '@clr/angular';

import {
  Api,
  editVaultEntry,
  listVaultEntries,
  removeVaultEntry,
  type VaultItemDto,
  type VaultPage as VaultPageData,
} from '../api';
import { HANDLES_OWN_ERRORS } from '../core/http/error.interceptor';
import { describeFailure } from '../core/http/problem';
import { EmptyState } from '../shared/states/empty-state';
import { ErrorState } from '../shared/states/error-state';
import { LoadingState } from '../shared/states/loading-state';
import { EntryForm, type EntryValues } from '../shared/vault/entry-form';

const SORTS = ['added', 'name', 'set', 'price', 'quantity'] as const;
const PAGE_SIZES = [25, 50, 100, 200] as const;
const RARITIES = ['common', 'uncommon', 'rare', 'mythic'] as const;
const COLORS = ['W', 'U', 'B', 'R', 'G', 'C'] as const;

/**
 * My collection (US-006..US-009, UC-04..UC-06): a server-paged table with search, filters and
 * sorting kept in the address, edit and remove dialogs, and a hint on prices that may be outdated.
 */
@Component({
  selector: 'app-vault-page',
  imports: [ClrModalModule, EmptyState, EntryForm, ErrorState, LoadingState, RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    .filters {
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem 1.5rem;
      align-items: flex-end;
      padding: 1rem 1.25rem;
      margin: 1rem 0 1.5rem;
      border-radius: 3px;
      border: 1px solid var(--clr-global-borders-color, #b3b3b3);
    }
    .colors {
      display: flex;
      gap: 0.75rem;
      flex-wrap: wrap;
      border: 0;
      padding: 0;
      margin: 0;
    }
    table th,
    table td {
      text-align: left;
      vertical-align: middle;
    }
    table img {
      width: 40px;
      height: auto;
      aspect-ratio: 488 / 680;
      object-fit: contain;
    }
    .sort {
      background: none;
      border: 0;
      padding: 0;
      font: inherit;
      font-weight: 600;
      color: inherit;
      cursor: pointer;
    }
    .stale {
      margin-left: 0.25rem;
    }
    .pager {
      display: flex;
      gap: 1rem;
      align-items: center;
      margin-top: 1rem;
      flex-wrap: wrap;
    }
    .notice {
      margin: 0 0 1rem;
    }
  `,
  template: `
    <h1 i18n="@@page.vault.title">Vault</h1>

    @if (notice(); as text) {
      <p class="alert alert-info notice" role="status" data-testid="notice">{{ text }}</p>
    }

    <form class="filters" (submit)="search($event)" data-testid="vault-filters" role="search">
      <div class="clr-form-control">
        <label for="vq" class="clr-control-label" i18n="@@vault.q">Card name</label>
        <input
          id="vq"
          name="q"
          class="clr-input"
          type="search"
          maxlength="100"
          [value]="q() ?? ''"
          data-testid="q"
        />
      </div>
      <div class="clr-form-control">
        <label for="vset" class="clr-control-label" i18n="@@vault.set">Set code</label>
        <input
          id="vset"
          name="set"
          class="clr-input"
          maxlength="6"
          size="6"
          [value]="set() ?? ''"
          data-testid="set"
        />
      </div>
      <div class="clr-form-control">
        <label for="vtype" class="clr-control-label" i18n="@@vault.type">Type</label>
        <input
          id="vtype"
          name="type"
          class="clr-input"
          maxlength="40"
          [value]="type() ?? ''"
          data-testid="type"
        />
      </div>
      <div class="clr-form-control">
        <label for="vrarity" class="clr-control-label" i18n="@@vault.rarity">Rarity</label>
        <select id="vrarity" name="rarity" class="clr-select" data-testid="rarity">
          <option value="" [selected]="!rarity()" i18n="@@vault.anyRarity">Any</option>
          @for (r of rarities; track r) {
            <option [value]="r" [selected]="rarity() === r">{{ r }}</option>
          }
        </select>
      </div>
      <fieldset class="colors">
        <legend class="clr-control-label" i18n="@@vault.colors">Colours</legend>
        @for (c of colorCodes; track c) {
          <label class="clr-control-label">
            <input
              type="checkbox"
              name="colors"
              [value]="c"
              [checked]="hasColor(c)"
              [attr.data-testid]="'color-' + c"
            />
            {{ c }}
          </label>
        }
      </fieldset>
      <div class="clr-form-control">
        <label for="vsize" class="clr-control-label" i18n="@@vault.pageSize">Per page</label>
        <select id="vsize" name="page_size" class="clr-select" data-testid="page-size">
          @for (n of pageSizes; track n) {
            <option [value]="n" [selected]="n === pageSize()">{{ n }}</option>
          }
        </select>
      </div>
      <div>
        <button type="submit" class="btn btn-primary" data-testid="search" i18n="@@vault.search">
          Search
        </button>
        @if (hasFilters()) {
          <button
            type="button"
            class="btn btn-link"
            data-testid="clear"
            (click)="clear()"
            i18n="@@vault.clear"
          >
            Clear
          </button>
        }
      </div>
    </form>

    <section aria-live="polite">
      @if (loading()) {
        <app-loading-state />
      } @else if (problem(); as message) {
        <app-error-state [message]="message" (retry)="load()" />
      } @else if (result(); as list) {
        @if (list.total === 0 && !hasFilters()) {
          <app-empty-state [heading]="emptyHeading" icon="library">
            <ng-container i18n="@@vault.emptyText">Cards you add will appear here.</ng-container>
            <div actions>
              <a
                class="btn btn-primary"
                routerLink="/scan"
                data-testid="empty-scan"
                i18n="@@vault.scan"
                >Scan a card</a
              >
              <a
                class="btn btn-outline"
                routerLink="/catalogue"
                data-testid="empty-catalogue"
                i18n="@@vault.browse"
                >Search the catalogue</a
              >
            </div>
          </app-empty-state>
        } @else if (list.items.length === 0) {
          <app-empty-state [heading]="noMatches" icon="search">
            <ng-container i18n="@@vault.noMatchText"
              >Try other words or clear the filters.</ng-container
            >
          </app-empty-state>
        } @else {
          <p data-testid="total">
            <ng-container i18n="@@vault.total">Entries:</ng-container> {{ list.total }}
          </p>
          <table class="table table-compact" data-testid="entries">
            <thead>
              <tr>
                <th><span class="clr-sr-only" i18n="@@vault.colImage">Image</span></th>
                <th [attr.aria-sort]="ariaSort('name')">
                  <button
                    type="button"
                    class="sort"
                    data-testid="sort-name"
                    (click)="sortBy('name')"
                    i18n="@@vault.colName"
                  >
                    Name
                  </button>
                </th>
                <th [attr.aria-sort]="ariaSort('set')">
                  <button
                    type="button"
                    class="sort"
                    data-testid="sort-set"
                    (click)="sortBy('set')"
                    i18n="@@vault.colSet"
                  >
                    Set
                  </button>
                </th>
                <th i18n="@@vault.colNumber">Number</th>
                <th i18n="@@vault.colFinish">Finish</th>
                <th i18n="@@vault.colCondition">Condition</th>
                <th [attr.aria-sort]="ariaSort('quantity')">
                  <button
                    type="button"
                    class="sort"
                    data-testid="sort-quantity"
                    (click)="sortBy('quantity')"
                    i18n="@@vault.colQuantity"
                  >
                    Quantity
                  </button>
                </th>
                <th [attr.aria-sort]="ariaSort('price')">
                  <button
                    type="button"
                    class="sort"
                    data-testid="sort-price"
                    (click)="sortBy('price')"
                    i18n="@@vault.colPrice"
                  >
                    Unit price
                  </button>
                </th>
                <th><span class="clr-sr-only" i18n="@@vault.colActions">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              @for (item of list.items; track item.id) {
                <tr data-testid="entry">
                  <td>
                    @if (item.card.image_small; as src) {
                      <img
                        [src]="src"
                        [alt]="item.card.name"
                        width="40"
                        height="56"
                        loading="lazy"
                      />
                    }
                  </td>
                  <td>
                    <a [routerLink]="['/catalogue', item.card.id]" data-testid="entry-name">{{
                      item.card.name
                    }}</a>
                  </td>
                  <td>{{ item.card.set_name }} ({{ item.card.set_code.toUpperCase() }})</td>
                  <td>{{ item.card.collector_number }}</td>
                  <td>{{ item.finish }}</td>
                  <td>{{ item.condition }}</td>
                  <td data-testid="entry-quantity">{{ item.quantity }}</td>
                  <td>
                    @if (item.unit_price; as price) {
                      <span data-testid="entry-price">\${{ price }}</span>
                    } @else {
                      <span data-testid="entry-price" i18n="@@vault.noPrice">unknown</span>
                    }
                    @if (item.prices_stale) {
                      <span
                        class="label label-warning stale"
                        data-testid="stale"
                        i18n="@@vault.stale"
                        >outdated</span
                      >
                    }
                  </td>
                  <td>
                    <button
                      type="button"
                      class="btn btn-sm btn-link"
                      data-testid="edit"
                      (click)="startEdit(item)"
                    >
                      <ng-container i18n="@@vault.edit">Edit</ng-container>
                      <span class="clr-sr-only"> {{ item.card.name }}</span>
                    </button>
                    <button
                      type="button"
                      class="btn btn-sm btn-link"
                      data-testid="remove"
                      (click)="startRemove(item)"
                    >
                      <ng-container i18n="@@vault.remove">Remove</ng-container>
                      <span class="clr-sr-only"> {{ item.card.name }}</span>
                    </button>
                  </td>
                </tr>
              }
            </tbody>
          </table>
          <nav class="pager" aria-label="Pages" i18n-aria-label="@@vault.pages">
            <button
              type="button"
              class="btn btn-sm"
              data-testid="prev"
              [disabled]="pageNumber() <= 1"
              (click)="goTo(pageNumber() - 1)"
              i18n="@@vault.prev"
            >
              Previous page
            </button>
            <span data-testid="page">{{ pageNumber() }} / {{ pageCount() }}</span>
            <button
              type="button"
              class="btn btn-sm"
              data-testid="next"
              [disabled]="pageNumber() >= pageCount()"
              (click)="goTo(pageNumber() + 1)"
              i18n="@@vault.next"
            >
              Next page
            </button>
          </nav>
        }
      }
    </section>

    <clr-modal
      [clrModalOpen]="editing() !== null"
      (clrModalOpenChange)="closeDialogs()"
      [clrModalClosable]="true"
      data-testid="edit-dialog"
    >
      <h3 class="modal-title" i18n="@@vault.editTitle">Edit entry</h3>
      <div class="modal-body">
        @if (editing(); as item) {
          <p>{{ item.card.name }}</p>
          <app-entry-form
            [finishes]="item.available_finishes"
            [quantity]="item.quantity"
            [condition]="item.condition"
            [finish]="item.finish"
            [errors]="formErrors()"
            [busy]="busy()"
            [submitLabel]="saveLabel"
            (submitted)="saveEdit($event)"
            (cancelled)="closeDialogs()"
          />
        }
      </div>
    </clr-modal>

    <clr-modal
      [clrModalOpen]="removing() !== null"
      (clrModalOpenChange)="closeDialogs()"
      [clrModalClosable]="true"
      data-testid="remove-dialog"
    >
      <h3 class="modal-title" i18n="@@vault.removeTitle">Remove entry</h3>
      <div class="modal-body">
        @if (removing(); as item) {
          <p data-testid="remove-question">
            <ng-container i18n="@@vault.removeAsk">Remove</ng-container>
            {{ item.quantity }} × {{ item.card.name }} ({{ item.condition }}, {{ item.finish }})?
          </p>
        }
      </div>
      <div class="modal-footer">
        <button
          type="button"
          class="btn btn-outline"
          data-testid="remove-cancel"
          (click)="closeDialogs()"
          i18n="@@entry.cancel"
        >
          Cancel
        </button>
        <button
          type="button"
          class="btn btn-danger"
          data-testid="remove-confirm"
          [disabled]="busy()"
          (click)="confirmRemove()"
          i18n="@@vault.removeConfirm"
        >
          Remove
        </button>
      </div>
    </clr-modal>
  `,
})
export class VaultPage {
  private readonly api = inject(Api);
  private readonly router = inject(Router);

  // Bound from the query string (withComponentInputBinding).
  readonly q = input<string | undefined>();
  readonly set = input<string | undefined>();
  readonly colors = input<string | undefined>();
  readonly type = input<string | undefined>();
  readonly rarity = input<string | undefined>();
  readonly sort = input<string | undefined>();
  readonly dir = input<string | undefined>();
  readonly page = input<string | undefined>();
  readonly page_size = input<string | undefined>();

  protected readonly rarities = RARITIES;
  protected readonly colorCodes = COLORS;
  protected readonly pageSizes = PAGE_SIZES;
  protected readonly emptyHeading = $localize`:@@page.vault.empty:Your vault is empty`;
  protected readonly noMatches = $localize`:@@vault.noMatches:No entries match`;
  protected readonly saveLabel = $localize`:@@vault.save:Save`;

  protected readonly loading = signal(false);
  protected readonly result = signal<VaultPageData | null>(null);
  protected readonly problem = signal<string | null>(null);
  protected readonly notice = signal<string | null>(null);
  protected readonly editing = signal<VaultItemDto | null>(null);
  protected readonly removing = signal<VaultItemDto | null>(null);
  protected readonly formErrors = signal<Record<string, string>>({});
  protected readonly busy = signal(false);

  protected readonly pageNumber = computed(() => Math.max(1, Number(this.page()) || 1));
  protected readonly pageSize = computed(() => {
    const requested = Number(this.page_size());
    return (PAGE_SIZES as readonly number[]).includes(requested) ? requested : 50;
  });
  protected readonly activeSort = computed(() =>
    (SORTS as readonly string[]).includes(this.sort() ?? '') ? (this.sort() as string) : 'added',
  );
  protected readonly descending = computed(() => {
    const dir = this.dir();
    return dir ? dir === 'desc' : ['added', 'price', 'quantity'].includes(this.activeSort());
  });
  protected readonly pageCount = computed(() => {
    const total = this.result()?.total ?? 0;
    return Math.max(1, Math.ceil(total / this.pageSize()));
  });
  protected readonly hasFilters = computed(
    () => !!(this.q() || this.set() || this.colors() || this.type() || this.rarity()),
  );

  constructor() {
    effect(() => {
      // Any change of the address loads the page again.
      this.q();
      this.set();
      this.colors();
      this.type();
      this.rarity();
      this.sort();
      this.dir();
      this.pageNumber();
      this.pageSize();
      untracked(() => void this.load());
    });
  }

  protected hasColor(code: string): boolean {
    return (this.colors() ?? '').toUpperCase().includes(code);
  }

  protected ariaSort(column: string): 'ascending' | 'descending' | null {
    if (this.activeSort() !== column) {
      return null;
    }
    return this.descending() ? 'descending' : 'ascending';
  }

  protected async load(): Promise<void> {
    this.loading.set(true);
    this.problem.set(null);
    try {
      this.result.set(
        await this.api.invoke(
          listVaultEntries,
          {
            page: this.pageNumber(),
            page_size: this.pageSize(),
            q: this.q() || null,
            set: this.set() || null,
            colors: this.colors() || null,
            rarity: this.rarity() || null,
            type: this.type() || null,
            sort: this.activeSort(),
            dir: this.dir() || null,
          },
          this.own(),
        ),
      );
    } catch (error) {
      this.result.set(null);
      this.problem.set(this.describe(error));
    } finally {
      this.loading.set(false);
    }
  }

  // ------------------------------------------------------------------ the address
  protected search(event: Event): void {
    event.preventDefault();
    const data = new FormData(event.target as HTMLFormElement);
    const text = (name: string): string | undefined => {
      const raw = data.get(name);
      const value = typeof raw === 'string' ? raw.trim() : '';
      return value === '' ? undefined : value;
    };
    const size = Number(text('page_size'));
    void this.router.navigate(['/vault'], {
      queryParams: {
        q: text('q'),
        set: text('set')?.toLowerCase(),
        type: text('type'),
        rarity: text('rarity'),
        colors: data.getAll('colors').map(String).join('') || undefined,
        page_size: size && size !== 50 ? size : undefined,
        sort: this.sort(),
        dir: this.dir(),
        page: undefined,
      },
    });
  }

  protected clear(): void {
    void this.router.navigate(['/vault']);
  }

  protected goTo(page: number): void {
    void this.router.navigate(['/vault'], {
      queryParams: { page: page > 1 ? page : undefined },
      queryParamsHandling: 'merge',
    });
  }

  protected sortBy(column: string): void {
    const nextDescending = this.activeSort() === column ? !this.descending() : false;
    void this.router.navigate(['/vault'], {
      queryParams: { sort: column, dir: nextDescending ? 'desc' : 'asc', page: undefined },
      queryParamsHandling: 'merge',
    });
  }

  // ------------------------------------------------------------------ edit and remove
  protected startEdit(item: VaultItemDto): void {
    this.formErrors.set({});
    this.editing.set(item);
  }

  protected startRemove(item: VaultItemDto): void {
    this.removing.set(item);
  }

  protected closeDialogs(): void {
    this.editing.set(null);
    this.removing.set(null);
    this.formErrors.set({});
  }

  protected async saveEdit(values: EntryValues): Promise<void> {
    const item = this.editing();
    if (!item) {
      return;
    }
    this.busy.set(true);
    try {
      const saved = await this.api.invoke(
        editVaultEntry,
        { entry_id: item.id, body: values },
        this.own(),
      );
      this.closeDialogs();
      this.notice.set(
        saved.id === item.id
          ? $localize`:@@vault.saved:Saved.`
          : $localize`:@@vault.merged:Merged with an existing entry: you now own ${saved.quantity}:quantity: of this card in ${saved.condition}:condition:, ${saved.finish}:finish:.`,
      );
      await this.load();
    } catch (error) {
      this.formErrors.set(this.fieldMessages(error));
      if (error instanceof HttpErrorResponse && error.status === 404) {
        this.closeDialogs();
        this.notice.set(
          $localize`:@@vault.gone:That entry no longer exists. The list was refreshed.`,
        );
        await this.load();
      }
    } finally {
      this.busy.set(false);
    }
  }

  protected async confirmRemove(): Promise<void> {
    const item = this.removing();
    if (!item) {
      return;
    }
    this.busy.set(true);
    try {
      await this.api.invoke(removeVaultEntry, { entry_id: item.id }, this.own());
      this.notice.set($localize`:@@vault.removed:The entry was removed.`);
    } catch (error) {
      this.notice.set(
        error instanceof HttpErrorResponse && error.status === 404
          ? $localize`:@@vault.alreadyGone:That entry was not found (it may already be removed). The list was refreshed.`
          : this.describe(error),
      );
    } finally {
      this.busy.set(false);
      this.closeDialogs();
      await this.load();
    }
  }

  // ------------------------------------------------------------------ helpers
  private own(): HttpContext {
    return new HttpContext().set(HANDLES_OWN_ERRORS, true);
  }

  private fieldMessages(error: unknown): Record<string, string> {
    if (!(error instanceof HttpErrorResponse)) {
      return { _: this.describe(error) };
    }
    const failure = describeFailure(error);
    const byField: Record<string, string> = {};
    for (const problem of failure.fields) {
      byField[problem.field] = problem.message;
    }
    return Object.keys(byField).length > 0 ? byField : { _: failure.message };
  }

  private describe(error: unknown): string {
    const status = error instanceof HttpErrorResponse ? error.status : 0;
    return status === 422
      ? $localize`:@@vault.invalid:That request is not valid. Check the filters.`
      : $localize`:@@vault.failed:Your vault could not be loaded. Try again.`;
  }
}
