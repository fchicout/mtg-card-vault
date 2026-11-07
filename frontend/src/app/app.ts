import { CUSTOM_ELEMENTS_SCHEMA, Component, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { ClrNavigationModule } from '@clr/angular';
import { ClarityIcons, libraryIcon, moonIcon, plusIcon, sunIcon } from '@cds/core/icon';
import '@cds/core/icon/register.js';

ClarityIcons.addIcons(libraryIcon, moonIcon, plusIcon, sunIcon);

@Component({
  imports: [RouterOutlet, RouterLink, RouterLinkActive, ClrNavigationModule],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App {
  protected readonly dark = signal(false);

  protected toggleTheme(): void {
    this.dark.update((value) => !value);
    document.body.setAttribute('cds-theme', this.dark() ? 'dark' : 'light');
  }
}
