import { Component, inject, signal, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../api.service';

declare var google: any;

@Component({
  selector: 'app-config',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './config.html',
  styleUrl: './config.css'
})
export class ConfigComponent implements OnInit {
  private api = inject(ApiService);
  private cdr = inject(ChangeDetectorRef);
  
  config = signal<any>({});
  authStatus = signal<any>({ authenticated: false });
  loading = signal(true);
  
  newKey = '';
  newValue = '';

  ollamaUrlInput = '';
  ollamaModels = signal<string[]>([]);
  geminiModels = signal<{name: string, displayName: string}[]>([]);
  anthropicModels = signal<{name: string, displayName: string}[]>([]);
  anthropicKeyInput = '';

  ngOnInit() {
    this.loadData();
    this.api.getOllamaTags().subscribe(res => {
      if (res.models && res.models.length > 0) {
        this.ollamaModels.set(res.models);
      }
    });
    this.api.getGeminiModels().subscribe(res => {
      if (res.models && res.models.length > 0) {
        this.geminiModels.set(res.models);
      }
    });
    this.api.getAnthropicModels().subscribe(res => {
      if (res.models && res.models.length > 0) {
        this.anthropicModels.set(res.models);
      }
    });
  }

  loadData() {
    this.api.getConfig().subscribe(data => {
      this.config.set(data);
      if (data['OLLAMA_BASE_URL']) {
        this.ollamaUrlInput = data['OLLAMA_BASE_URL'];
      } else {
        this.ollamaUrlInput = 'http://host.docker.internal:11434';
      }
      if (data['ANTHROPIC_API_KEY']) {
        this.anthropicKeyInput = data['ANTHROPIC_API_KEY'];
      }
    });

    this.api.getAuthStatus().subscribe(status => {
      let restored = false;
      if (typeof localStorage !== 'undefined') {
        const storedAuth = localStorage.getItem('google_auth_session');
        if (storedAuth) {
          try {
            const authData = JSON.parse(storedAuth);
            this.authStatus.set({
              ...status,
              authenticated: true,
              user: authData.user,
              message: 'Sesión restaurada localmente.',
              workspaceConnected: status.workspaceConnected // Always take the freshed backend info for this
            });
            restored = true;
          } catch(e) { }
        }
      }
      
      if (!restored) {
        this.authStatus.set(status);
      }
      
      // Siempre inyectar el script de Google si tenemos clientId
      // Es necesario para que "google.accounts.oauth2" funcione en el click azul
      if (status.clientId) {
        setTimeout(() => this.initGoogleAuth(status.clientId), 100);
      }
    });
    this.loading.set(false);
  }

  initGoogleAuth(clientId: string) {
    if (typeof document !== 'undefined') {
      const script = document.createElement('script');
      script.src = 'https://accounts.google.com/gsi/client';
      script.async = true;
      script.defer = true;
      script.onload = () => {
        if (typeof google !== 'undefined') {
          google.accounts.id.initialize({
            client_id: clientId,
            callback: (response: any) => this.handleCredentialResponse(response)
          });
          
          const buttonDiv = document.getElementById("google-buttonDiv");
          if (buttonDiv) {
            google.accounts.id.renderButton(buttonDiv, {
              theme: "outline", 
              size: "large", 
              type: "standard", 
              text: "continue_with",
              shape: "rectangular"
            });
          }
        }
      };
      document.head.appendChild(script);
    }
  }

  authorizeWorkspace() {
    const clientId = this.authStatus().clientId;
    if (!clientId) {
      alert("No se encontró el Client ID de Google");
      return;
    }
    
    // Scopes match the backend configuration to generate token.pickle
    const client = google.accounts.oauth2.initCodeClient({
      client_id: clientId,
      scope: 'https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/spreadsheets https://www.googleapis.com/auth/chat.spaces.readonly https://www.googleapis.com/auth/chat.messages.readonly https://www.googleapis.com/auth/chat.messages',
      ux_mode: 'popup',
      callback: (response: any) => {
        if (response.error !== undefined) {
          console.error("Error en autorización OAuth", response);
          return;
        }
        
        // Send the authorization code to backend API
        this.api.exchangeGoogleCode(response.code).subscribe({
          next: (res) => {
            alert("¡Permisos otorgados exitosamente! Workspace conectado.");
            const currentStatus = this.authStatus();
            this.authStatus.set({ ...currentStatus, workspaceConnected: true });
          },
          error: (err) => {
            console.error(err);
            alert("Hubo un error al conectar el Workspace en el backend.");
          }
        });
      },
    });
    
    client.requestCode();
  }

  handleCredentialResponse(response: any) {
    try {
      const base64Url = response.credential.split('.')[1];
      const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
      const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
          return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
      }).join(''));
      
      const payload = JSON.parse(jsonPayload);
      const currentStatus = this.authStatus();
      const authData = { 
        ...currentStatus,
        authenticated: true, 
        user: payload,
        message: 'Conectado de forma segura.' 
      };
      
      this.authStatus.set(authData);
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem('google_auth_session', JSON.stringify({
          authenticated: true,
          user: payload
        }));
      }
      alert(`¡Sesión iniciada con éxito! Bienvenido, ${payload.name}`);
    } catch (e) {
      console.error("Error al procesar el JWT de Google:", e);
      alert("Hubo un error al iniciar sesión.");
    }
  }

  logoutGoogle() {
    if (typeof localStorage !== 'undefined') {
      localStorage.removeItem('google_auth_session');
    }
    
    // Revoke Google Workspace Backend Token
    this.api.revokeGoogleWorkspace().subscribe({
      next: () => {
        this.api.getAuthStatus().subscribe(status => {
          this.authStatus.set(status);
          if (status.clientId) {
            setTimeout(() => this.initGoogleAuth(status.clientId), 100);
          }
        });
      },
      error: (err) => {
        console.error("Error revocando el token:", err);
        // Force state reset anyway
        this.authStatus.set({ authenticated: false, workspaceConnected: false });
      }
    });
  }

  telegramLoading = false;
  telegramMsg = '';
  telegramMsgError = false;
  telegramConnected = false;

  checkTelegramStatus() {
    this.api.getTelegramStatus().subscribe({
      next: (res) => {
        this.telegramConnected = res.connected;
        this.cdr.detectChanges();
      }
    });
  }

  reloadTelegramBot() {
    this.telegramLoading = true;
    this.telegramMsg = '';
    this.telegramMsgError = false;
    this.cdr.detectChanges();
    
    this.api.reloadTelegram().subscribe({
      next: (res) => {
        this.telegramLoading = false;
        this.telegramMsg = res.message;
        this.telegramConnected = true;
        this.cdr.detectChanges();
        setTimeout(() => { this.telegramMsg = ''; this.cdr.detectChanges(); }, 5000);
      },
      error: (err) => {
        this.telegramLoading = false;
        this.telegramMsgError = true;
        this.telegramConnected = false;
        this.telegramMsg = err.error?.detail || err.message;
        this.cdr.detectChanges();
      }
    });
  }

  updateVar(key: string, value: string) {
    if (!value) return;
    this.api.updateConfig(key, value).subscribe((res: any) => {
      if (res.reinit) {
        alert(`✅ Variable ${key} actualizada. El agente se re-inicializó automáticamente con los nuevos valores.`);
      } else {
        alert(`Variable ${key} actualizada exitosamente.`);
      }
      this.loadData();
    });
  }

  addNewVar() {
    if (!this.newKey || !this.newValue) return;
    this.updateVar(this.newKey, this.newValue);
    this.newKey = '';
    this.newValue = '';
  }

  saveOllamaUrl() {
    if (!this.ollamaUrlInput) return;
    this.updateVar('OLLAMA_BASE_URL', this.ollamaUrlInput);
  }

  saveAnthropicKey() {
    if (!this.anthropicKeyInput) return;
    this.updateVar('ANTHROPIC_API_KEY', this.anthropicKeyInput);
    // Recargar modelos después de guardar la key
    setTimeout(() => {
      this.api.getAnthropicModels().subscribe(res => {
        if (res.models && res.models.length > 0) {
          this.anthropicModels.set(res.models);
        }
      });
    }, 1000);
  }

  isKnownModel(value: string): boolean {
    if (!value) return true;
    // Check Ollama models
    if (value.startsWith('ollama/')) return true;
    // Check dynamically loaded Gemini models
    if (this.geminiModels().some(m => m.name === value)) return true;
    // Check dynamically loaded Anthropic models
    if (this.anthropicModels().some(m => m.name === value)) return true;
    // Fallback static list
    const staticModels = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-2.5-pro'];
    return staticModels.includes(value);
  }

  getEnvKeys() {
    return Object.keys(this.config());
  }

  getEnvGroups() {
    const config = this.config();
    const groups = [];
    const keys = Object.keys(config);

    const googleKeys = keys.filter(k => k.startsWith('GOOGLE_'));
    if (googleKeys.length > 0) {
      groups.push({ title: 'Autenticación: Google Workspace', icon: 'ph-google-logo', keys: googleKeys });
    }

    const telegramKeys = keys.filter(k => k.startsWith('TELEGRAM_') || k === 'WEBHOOK_URL');
    if (telegramKeys.length > 0) {
      groups.push({ title: 'Integración: Bot de Telegram', icon: 'ph-telegram-logo', keys: telegramKeys });
    }

    const modelKeys = keys.filter(k => k.startsWith('MODEL_'));
    if (modelKeys.length > 0) {
      groups.push({ title: 'Configuración LLM por Agente', icon: 'ph-brain', keys: modelKeys });
    }

    const otherKeys = keys.filter(k => 
      !k.startsWith('GOOGLE_') && 
      !k.startsWith('TELEGRAM_') && 
      k !== 'WEBHOOK_URL' && 
      !k.startsWith('MODEL_')
    );
    if (otherKeys.length > 0) {
      groups.push({ title: 'Ajustes Globales del Sistema', icon: 'ph-gear-six', keys: otherKeys });
    }

    return groups;
  }
}
