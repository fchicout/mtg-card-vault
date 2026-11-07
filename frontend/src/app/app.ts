import { CUSTOM_ELEMENTS_SCHEMA, ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { ClrMainContainerModule, ClrNavigationModule } from '@clr/angular';
import {
  ClarityIcons,
  cameraIcon,
  exclamationCircleIcon,
  libraryIcon,
  moonIcon,
  searchIcon,
  sunIcon,
  userIcon,
} from '@cds/core/icon';
import '@cds/core/icon/register.js';

import { Notifications } from './core/notifications/notifications';
import { ThemeService } from './core/theme/theme.service';

ClarityIcons.addIcons(
  cameraIcon,
  exclamationCircleIcon,
  libraryIcon,
  moonIcon,
  searchIcon,
  sunIcon,
  userIcon,
);

/** Application shell (issue #9): Clarity header, vertical navigation, content, footer. */
@Component({
  imports: [
    ClrMainContainerModule,
    ClrNavigationModule,
    Notifications,
    RouterLink,
    RouterLinkActive,
    RouterOutlet,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  changeDetection: ChangeDetectionStrategy.OnPush,
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App {
  protected readonly theme = inject(ThemeService);
}
