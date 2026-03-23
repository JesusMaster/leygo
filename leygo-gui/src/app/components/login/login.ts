import { Component, ChangeDetectorRef, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { SetupService } from '../../services/setup.service';
import { ApiService } from '../../api.service';

declare var google: any;

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './login.html',
  styleUrls: ['./login.css']
})
export class LoginComponent implements OnInit {
  username = '';
  password = '';
  errorMessage = '';
  loading = false;

  private googleClientId = '';

  constructor(
    private setupService: SetupService,
    private api: ApiService,
    private router: Router,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit() {
    // Obtener el Client ID de Google del backend
    this.api.getAuthStatus().subscribe({
      next: (status: any) => {
        if (status.clientId) {
          this.googleClientId = status.clientId;
        }
      }
    });
  }

  loginWithGoogle() {
    if (!this.googleClientId) {
      this.errorMessage = 'Google SSO no está configurado. Configura GOOGLE_CLIENT_ID en las Variables de Entorno.';
      this.cdr.detectChanges();
      return;
    }

    this.loading = true;
    this.errorMessage = '';
    this.cdr.detectChanges();

    // Cargar el script de Google Identity Services si no está cargado
    if (typeof google === 'undefined' || !google.accounts) {
      const script = document.createElement('script');
      script.src = 'https://accounts.google.com/gsi/client';
      script.async = true;
      script.defer = true;
      script.onload = () => this.initGoogleSSO();
      script.onerror = () => {
        this.loading = false;
        this.errorMessage = 'No se pudo cargar el servicio de Google.';
        this.cdr.detectChanges();
      };
      document.head.appendChild(script);
    } else {
      this.initGoogleSSO();
    }
  }

  private initGoogleSSO() {
    try {
      google.accounts.id.initialize({
        client_id: this.googleClientId,
        callback: (response: any) => this.handleGoogleCredential(response)
      });
      // Trigger one-tap o popup
      google.accounts.id.prompt((notification: any) => {
        if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
          // Si One Tap no se muestra, forzar popup manual
          this.loading = false;
          this.errorMessage = 'Google no pudo mostrar el diálogo de inicio de sesión. Intenta de nuevo.';
          this.cdr.detectChanges();
        }
      });
    } catch (e) {
      this.loading = false;
      this.errorMessage = 'Error al inicializar Google SSO.';
      this.cdr.detectChanges();
    }
  }

  private handleGoogleCredential(response: any) {
    if (!response.credential) {
      this.loading = false;
      this.errorMessage = 'No se recibió credencial de Google.';
      this.cdr.detectChanges();
      return;
    }

    // Enviar el ID token al backend para validación
    this.setupService.googleLogin(response.credential).subscribe({
      next: (res) => {
        this.loading = false;
        localStorage.setItem('leygo_token', res.token);
        localStorage.setItem('leygo_user', res.username);
        this.cdr.detectChanges();
        this.router.navigate(['/chat']);
      },
      error: (err) => {
        this.loading = false;
        this.errorMessage = 'Acceso Denegado. ' + (err.error?.detail || err.message);
        this.cdr.detectChanges();
      }
    });
  }

  doLogin() {
    this.errorMessage = '';
    
    if (!this.username || !this.password) {
      this.errorMessage = 'Please provide both username and password.';
      this.cdr.detectChanges();
      return;
    }

    this.loading = true;
    this.cdr.detectChanges();

    this.setupService.login(this.username, this.password).subscribe({
      next: (res) => {
        this.loading = false;
        localStorage.setItem('leygo_token', res.token);
        localStorage.setItem('leygo_user', res.username);
        this.cdr.detectChanges();
        this.router.navigate(['/chat']);
      },
      error: (err) => {
        this.loading = false;
        this.errorMessage = 'Acceso Denegado. ' + (err.error?.detail || err.message);
        this.cdr.detectChanges();
      }
    });
  }
}
