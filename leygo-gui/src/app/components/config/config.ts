import { Component, inject, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../api.service';

@Component({
  selector: 'app-config',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './config.html',
  styleUrl: './config.css'
})
export class ConfigComponent implements OnInit {
  private api = inject(ApiService);
  
  config = signal<any>({});
  authStatus = signal<any>({ authenticated: false });
  loading = signal(true);
  
  newKey = signal('');
  newValue = signal('');

  ngOnInit() {
    this.loadData();
  }

  loadData() {
    this.api.getConfig().subscribe(data => this.config.set(data));
    this.api.getAuthStatus().subscribe(status => this.authStatus.set(status));
    this.loading.set(false);
  }

  updateVar(key: string, value: string) {
    if (!value) return;
    this.api.updateConfig(key, value).subscribe(() => {
      alert(`Variable ${key} actualizada exitosamente.`);
      this.loadData();
    });
  }

  addNewVar() {
    if (!this.newKey() || !this.newValue()) return;
    this.updateVar(this.newKey(), this.newValue());
    this.newKey.set('');
    this.newValue.set('');
  }

  getEnvKeys() {
    return Object.keys(this.config());
  }

  loginWithGoogle() {
    alert('Redirigiendo a Google SSO (Simulado)...');
  }
}
