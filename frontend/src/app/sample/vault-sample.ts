import { CUSTOM_ELEMENTS_SCHEMA, Component, inject, signal, viewChild } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import {
  ClrAlertModule,
  ClrDatagridModule,
  ClrForm,
  ClrFormsModule,
  ClrInputModule,
  ClrNumberInputModule,
  ClrModalModule,
  ClrRadioModule,
  ClrSelectModule,
} from '@clr/angular';

interface Row {
  name: string;
  set: string;
  quantity: number;
  condition: string;
  finish: string;
}

const SETS = ['LEA', 'M21', 'MH3', 'ONE', 'BLB'];
const CONDITIONS = ['NM', 'LP', 'MP', 'HP', 'DMG'];

/** Throwaway spike (issue #3): proves datagrid + modal + form + alert + icons under Clarity. */
@Component({
  selector: 'app-vault-sample',
  imports: [
    ReactiveFormsModule,
    ClrAlertModule,
    ClrDatagridModule,
    ClrFormsModule,
    ClrInputModule,
    ClrNumberInputModule,
    ClrModalModule,
    ClrRadioModule,
    ClrSelectModule,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './vault-sample.html',
})
export class VaultSample {
  protected readonly conditions = CONDITIONS;
  protected readonly rows = signal<Row[]>(
    Array.from({ length: 37 }, (_, i) => ({
      name: `Sample card ${i + 1}`,
      set: SETS[i % SETS.length],
      quantity: (i % 4) + 1,
      condition: CONDITIONS[i % CONDITIONS.length],
      finish: i % 3 === 0 ? 'foil' : 'nonfoil',
    })),
  );
  protected readonly open = signal(false);
  protected readonly added = signal<string | null>(null);

  private readonly fb = inject(FormBuilder);
  private readonly clrForm = viewChild.required(ClrForm);

  protected readonly form = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(80)]],
    quantity: [1, [Validators.required, Validators.min(1), Validators.max(9999)]],
    condition: ['NM', Validators.required],
    finish: ['nonfoil', Validators.required],
  });

  protected submit(): void {
    if (this.form.invalid) {
      // Clarity shows control errors from status events: its own helper triggers them.
      this.clrForm().markAsTouched();
      return;
    }
    const value = this.form.getRawValue();
    this.rows.update((rows) => [{ ...value, set: 'LEA' }, ...rows]);
    this.added.set(value.name);
    this.open.set(false);
    this.form.reset({ name: '', quantity: 1, condition: 'NM', finish: 'nonfoil' });
  }
}
