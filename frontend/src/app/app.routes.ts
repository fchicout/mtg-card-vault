import type { Routes } from '@angular/router';

import { authGuard } from './core/auth/auth.guard';

/** Feature routes are lazy: each page is its own chunk and only loads when visited. */
export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    title: $localize`:@@route.home:MTG Card Vault`,
    loadComponent: () => import('./pages/home').then((m) => m.HomePage),
  },
  {
    path: 'vault',
    canActivate: [authGuard],
    title: $localize`:@@route.vault:Vault - MTG Card Vault`,
    loadComponent: () => import('./pages/vault').then((m) => m.VaultPage),
  },
  {
    path: 'catalogue',
    canActivate: [authGuard],
    title: $localize`:@@route.catalogue:Catalogue - MTG Card Vault`,
    loadComponent: () => import('./pages/catalogue').then((m) => m.CataloguePage),
  },
  {
    path: 'catalogue/:id',
    canActivate: [authGuard],
    title: $localize`:@@route.card:Card - MTG Card Vault`,
    loadComponent: () => import('./pages/card-detail').then((m) => m.CardDetailPage),
  },
  {
    path: 'scan',
    canActivate: [authGuard],
    title: $localize`:@@route.scan:Scan - MTG Card Vault`,
    loadComponent: () => import('./pages/scan').then((m) => m.ScanPage),
  },
  {
    path: 'account',
    canActivate: [authGuard],
    title: $localize`:@@route.account:Account - MTG Card Vault`,
    loadComponent: () => import('./pages/account').then((m) => m.AccountPage),
  },
  {
    path: 'signin-required',
    title: $localize`:@@route.signin:Sign in required - MTG Card Vault`,
    loadComponent: () => import('./pages/signin-required').then((m) => m.SigninRequiredPage),
  },
  {
    path: 'callback',
    title: $localize`:@@route.callback:Signing in - MTG Card Vault`,
    loadComponent: () => import('./pages/callback').then((m) => m.CallbackPage),
  },
  {
    path: '**',
    title: $localize`:@@route.notfound:Page not found - MTG Card Vault`,
    loadComponent: () => import('./pages/not-found').then((m) => m.NotFoundPage),
  },
];
