import { Component } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive, Router } from '@angular/router';
import { SetupService } from './services/setup.service';
import { ToastComponent } from './shared/components/toast/toast';
import { ConfirmDialogComponent } from './shared/components/confirm-dialog/confirm-dialog';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, ToastComponent, ConfirmDialogComponent],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App {
  title = 'Leygo';
  userName = 'Admin';
  userInitials = 'AD';
  isDarkMode = false;

  constructor(private setupService: SetupService, private router: Router) {
    const user = localStorage.getItem('leygo_user');
    if (user) {
      this.userName = user;
      const parts = user.split(' ');
      if (parts.length > 1) {
        this.userInitials = (parts[0][0] + parts[1][0]).toUpperCase();
      } else {
        this.userInitials = user.substring(0, 2).toUpperCase();
      }
    }

    const savedTheme = localStorage.getItem('leygo_theme');
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
      this.isDarkMode = true;
      document.body.classList.add('dark-theme');
    } else {
      this.isDarkMode = false;
      document.body.classList.remove('dark-theme');
    }
  }

  toggleTheme() {
    this.isDarkMode = !this.isDarkMode;
    if (this.isDarkMode) {
      document.body.classList.add('dark-theme');
      localStorage.setItem('leygo_theme', 'dark');
    } else {
      document.body.classList.remove('dark-theme');
      localStorage.setItem('leygo_theme', 'light');
    }
  }

  logout() {
    this.setupService.logout();
    this.router.navigate(['/login']);
  }
}
