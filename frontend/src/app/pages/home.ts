import { ChangeDetectionStrategy, Component } from '@angular/core';

/** Start page: a welcome card. Sign-in and the vault summary arrive with the identity milestone. */
@Component({
  selector: 'app-home-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h1 i18n="@@page.home.title">Welcome to MTG Card Vault</h1>
    <div class="card">
      <div class="card-block">
        <p class="card-text" data-testid="welcome" i18n="@@page.home.welcome">
          Your private, priced inventory of Magic: The Gathering cards.
        </p>
      </div>
    </div>
  `,
})
export class HomePage {}
