import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';

import { Api, getHello } from '../api';
import { ErrorState } from '../shared/states/error-state';
import { LoadingState } from '../shared/states/loading-state';

/**
 * Start page. It still shows the skeleton greeting (issue #1) because that proves the browser ->
 * generated client -> API path; it goes away with the temporary /hello route in issue #15.
 * A failure is explained by the global alert (with support details); this view only offers a retry.
 */
@Component({
  selector: 'app-home-page',
  imports: [ErrorState, LoadingState],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h1 i18n="@@page.home.title">Welcome to MTG Card Vault</h1>
    @if (loading()) {
      <app-loading-state />
    } @else if (failed()) {
      <app-error-state [message]="unreachable" (retry)="load()" />
    } @else {
      <div class="card">
        <div class="card-block">
          <p class="card-text" data-testid="greeting">{{ greeting() }}</p>
        </div>
      </div>
    }
  `,
})
export class HomePage implements OnInit {
  private readonly api = inject(Api);

  protected readonly unreachable = $localize`:@@page.home.unreachable:The greeting could not be loaded.`;
  protected readonly loading = signal(true);
  protected readonly greeting = signal<string | null>(null);
  protected readonly failed = signal(false);

  ngOnInit(): void {
    void this.load();
  }

  protected async load(): Promise<void> {
    this.loading.set(true);
    this.failed.set(false);
    try {
      const response = await this.api.invoke(getHello);
      this.greeting.set(response.message);
    } catch {
      this.failed.set(true);
    } finally {
      this.loading.set(false);
    }
  }
}
