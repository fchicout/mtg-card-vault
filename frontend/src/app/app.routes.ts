import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'vault' },
  {
    path: 'vault',
    loadComponent: () => import('./sample/vault-sample').then((m) => m.VaultSample),
  },
];
