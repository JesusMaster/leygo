import { Component, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { SetupService } from '../../services/setup.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './login.html',
  styleUrls: ['./login.css']
})
export class LoginComponent {
  username = '';
  password = '';
  errorMessage = '';
  loading = false;

  constructor(
    private setupService: SetupService,
    private router: Router,
    private cdr: ChangeDetectorRef
  ) {}

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
        // Guardamos el Session Token para el AuthGuard
        localStorage.setItem('leygo_token', res.token);
        localStorage.setItem('leygo_user', res.username);
        this.cdr.detectChanges();
        // Dirigimos al centro de chat
        this.router.navigate(['/chat']);
      },
      error: (err) => {
        this.loading = false;
        // Explicación nativa de Argon2 si se falla o acierta
        this.errorMessage = 'Acceso Denegado. ' + (err.error?.detail || err.message);
        this.cdr.detectChanges();
      }
    });
  }
}
