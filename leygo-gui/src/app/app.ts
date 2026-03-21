import { Component } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive, Router } from '@angular/router';
import { SetupService } from './services/setup.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App {
  title = 'Leygo';
  userName = 'Admin';
  userInitials = 'AD';

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
  }

  logout() {
    this.setupService.logout();
    this.router.navigate(['/login']);
  }
}
