import { inject } from '@angular/core';
import { Router, CanActivateFn } from '@angular/router';
import { SetupService } from '../services/setup.service';
import { map, catchError } from 'rxjs/operators';
import { of } from 'rxjs';

export const setupGuard: CanActivateFn = (route, state) => {
  const setupService = inject(SetupService);
  const router = inject(Router);

  // Excepciones: Si ya estás tratando de ir al setup o login, te dejo pasar
  if (state.url === '/setup' || state.url === '/login') {
    return true;
  }

  return setupService.getStatus().pipe(
    map(status => {
      // Si el backend dice que el setup NO está completado, bota al usuario al setup
      if (!status.setup_completed) {
        return router.createUrlTree(['/setup']);
      }
      return true; // Si está completado, adelante
    }),
    catchError((err) => {
      console.warn('Backend is unreachable or error in setup status fetch', err);
      // Forzamos al setup en caso de error para no dejarlos huérfanos sin backend
      return of(router.createUrlTree(['/setup']));
    })
  );
};
