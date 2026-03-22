import { inject } from '@angular/core';
import { Router, CanActivateFn } from '@angular/router';
import { SetupService } from '../services/setup.service';

export const authGuard: CanActivateFn = (route, state) => {
  const setupService = inject(SetupService);
  const router = inject(Router);

  if (setupService.isLoggedIn()) {
    return true;
  }

  // Si no está logueado, patada a la pantalla de login
  return router.createUrlTree(['/login']);
};
