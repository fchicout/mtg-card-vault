import { Component, OnInit, inject, signal } from '@angular/core';
import { ClrAlertModule } from '@clr/angular';
import { ClarityIcons, exclamationCircleIcon } from '@cds/core/icon';
import '@cds/core/icon/register.js';

import { Api, getHello } from './api';

ClarityIcons.addIcons(exclamationCircleIcon);

/**
 * Walking-skeleton page (issue #1): proves the browser -> generated client -> API path.
 * Replaced by the real application shell in issue #9.
 */
@Component({
  imports: [ClrAlertModule],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App implements OnInit {
  private readonly api = inject(Api);

  protected readonly loading = signal(true);
  protected readonly greeting = signal<string | null>(null);
  protected readonly failed = signal(false);

  async ngOnInit(): Promise<void> {
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
