import { Component, OnInit, ChangeDetectorRef, HostListener } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { SetupService, SetupStatus } from '../../services/setup.service';

@Component({
  selector: 'app-setup',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './setup.html',
  styleUrls: ['./setup.css']
})
export class SetupComponent implements OnInit {
  currentStep = 1;
  totalSteps = 5;
  loading = false;
  errorMessage = '';
  backendBaseUrl = `${window.location.protocol}//${window.location.hostname}:2083`;

  // --- MODELOS DE DATOS ---
  // Paso 1
  activationKey = '';
  adminEmail = '';
  adminPass = '';
  userName = ''; // Movido aquí

  // Paso 2
  agentName = 'Leygo';
  preferredName = '';
  agentPersonality = 'Eres un asistente altamente capacitado. Tu objetivo es ser directo, útil y claro, apoyando a tu creador en sus tareas diarias con una orientación excepcional, creatividad y resolución implacable de problemas.';

  // Paso 3
  timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  tzDropdownOpen = false;
  tzSearchQuery = '';
  llmProvider = 'Google';
  googleApiKey = '';
  openaiApiKey = '';
  anthropicApiKey = '';

  // Paso 4
  googleClientId = '';
  googleClientSecret = '';
  googleAuthRequested = false;

  // Paso 5
  telegramToken = '';
  telegramChatId = '';
  webhookUrl = '';

  constructor(
    private setupService: SetupService, 
    private router: Router,
    private cdr: ChangeDetectorRef
  ) {}

  @HostListener('document:click')
  onDocumentClick() {
    if (this.tzDropdownOpen) {
      this.tzDropdownOpen = false;
      this.cdr.detectChanges();
    }
  }

  private ALL_TIMEZONES: string[] = [
    // Africa
  'Africa/Abidjan','Africa/Accra','Africa/Addis_Ababa','Africa/Algiers','Africa/Cairo',
  'Africa/Casablanca','Africa/Johannesburg','Africa/Lagos','Africa/Nairobi','Africa/Tunis',

  // America
  'America/Anchorage','America/Bogota','America/Buenos_Aires','America/Caracas',
  'America/Chicago','America/Denver','America/Guayaquil','America/Havana',
  'America/Lima','America/Los_Angeles','America/Mexico_City','America/Montevideo',
  'America/New_York','America/Phoenix','America/Puerto_Rico','America/Santiago',
  'America/Sao_Paulo','America/Toronto','America/Vancouver',

  // Polar
  'Antarctica/McMurdo','Arctic/Longyearbyen',

  // Asia
  'Asia/Almaty','Asia/Amman','Asia/Baghdad','Asia/Baku','Asia/Bangkok',
  'Asia/Beirut','Asia/Colombo','Asia/Dhaka','Asia/Dubai','Asia/Ho_Chi_Minh',
  'Asia/Hong_Kong','Asia/Jakarta','Asia/Jerusalem','Asia/Kabul','Asia/Karachi',
  'Asia/Kathmandu','Asia/Kolkata','Asia/Kuala_Lumpur','Asia/Kuwait','Asia/Macau',
  'Asia/Manila','Asia/Muscat','Asia/Nicosia','Asia/Qatar','Asia/Yangon',
  'Asia/Riyadh','Asia/Seoul','Asia/Shanghai','Asia/Singapore','Asia/Taipei',
  'Asia/Tashkent','Asia/Tehran','Asia/Tokyo','Asia/Ulaanbaatar','Asia/Yekaterinburg',

  // Atlantic
  'Atlantic/Azores','Atlantic/Canary','Atlantic/Cape_Verde','Atlantic/Reykjavik',

  // Australia
  'Australia/Adelaide','Australia/Brisbane','Australia/Darwin','Australia/Hobart',
  'Australia/Melbourne','Australia/Perth','Australia/Sydney',

  // Europe
  'Europe/Amsterdam','Europe/Athens','Europe/Belgrade','Europe/Berlin',
  'Europe/Brussels','Europe/Bucharest','Europe/Budapest','Europe/Copenhagen',
  'Europe/Dublin','Europe/Helsinki','Europe/Istanbul','Europe/Kyiv',
  'Europe/Lisbon','Europe/London','Europe/Luxembourg','Europe/Madrid',
  'Europe/Moscow','Europe/Oslo','Europe/Paris','Europe/Prague','Europe/Rome',
  'Europe/Sofia','Europe/Stockholm','Europe/Vienna','Europe/Warsaw','Europe/Zurich',

  // Indian Ocean
  'Indian/Maldives','Indian/Mauritius',

  // Pacific
  'Pacific/Auckland','Pacific/Fiji','Pacific/Guam','Pacific/Honolulu',
  'Pacific/Midway','Pacific/Noumea','Pacific/Pago_Pago','Pacific/Port_Moresby',
  'Pacific/Tongatapu',

  // Universal
  'UTC'
  ];

  filteredTimezones(): string[] {
    const q = this.tzSearchQuery.toLowerCase();
    return this.ALL_TIMEZONES.filter(tz => tz.toLowerCase().includes(q));
  }

  toggleTzDropdown() {
    this.tzDropdownOpen = !this.tzDropdownOpen;
    if (this.tzDropdownOpen) this.tzSearchQuery = '';
    this.cdr.detectChanges();
  }

  selectTimezone(tz: string) {
    this.timezone = tz;
    this.tzDropdownOpen = false;
    this.tzSearchQuery = '';
    this.cdr.detectChanges();
  }

  ngOnInit() {
    this.webhookUrl = `${window.location.protocol}//${window.location.hostname}:2083`;
    
    this.setupService.getStatus().subscribe(status => {
      if(status.admin_created && !status.setup_completed) {
        this.currentStep = 2;
      } else if (status.setup_completed) {
        this.router.navigate(['/']);
      }
      this.cdr.detectChanges();
    });
  }

  nextStep() {
    this.errorMessage = '';
    
    if (this.currentStep === 1) {
      if (!this.activationKey || !this.adminEmail || !this.adminPass || !this.userName) {
        this.errorMessage = 'Completa la llave, nombre, correo y contraseña para continuar.';
        this.cdr.detectChanges();
        return;
      }
      this.loading = true;
      this.cdr.detectChanges();

      // Mandamos adminEmail como el "username" nativo del backend
      this.setupService.createAdmin(this.activationKey, this.adminEmail, this.adminPass).subscribe({
        next: () => {
          this.loading = false;
          // Sugerir el primer nombre de forma automática
          if (!this.preferredName && this.userName) {
             this.preferredName = this.userName.trim().split(' ')[0];
          }
          this.currentStep++;
          this.cdr.detectChanges();
        },
        error: (err) => {
          this.loading = false;
          this.errorMessage = 'Error de activación: ' + (err.error?.detail || err.message);
          this.cdr.detectChanges();
        }
      });
      return;
    }

    if (this.currentStep === 2) {
      if (!this.agentName || !this.agentPersonality) {
        this.errorMessage = 'El nombre de tu agente y su personalidad son obligatorios.';
        this.cdr.detectChanges();
        return;
      }
      this.currentStep++;
      this.cdr.detectChanges();
      return;
    }

    if (this.currentStep === 3) {
      if (this.llmProvider === 'Google' && !this.googleApiKey) {
        this.errorMessage = 'Si seleccionas Google, debes ingresar su API Key.'; 
        this.cdr.detectChanges();
        return;
      }
      this.currentStep++;
      this.cdr.detectChanges();
      return;
    }

    if (this.currentStep === 4) {
       this.currentStep++;
       this.cdr.detectChanges();
       return;
    }
  }

  connectGoogle() {
    this.errorMessage = '';
    
    // Aquí obligamos a coincidir con el puerto Backend donde está escuchando FastAPI ciegamente
    const redirectUri = `${window.location.protocol}//${window.location.hostname}:2083/api/setup/google-callback`;

    this.loading = true;
    this.cdr.detectChanges();
    
    this.setupService.getGoogleAuthUrl(this.googleClientId, this.googleClientSecret, redirectUri).subscribe({
      next: (res: any) => {
        this.loading = false;
        this.googleAuthRequested = true;
        this.cdr.detectChanges();
        // Abrimos el popup
        window.open(res.url, 'GoogleAuth', 'width=600,height=700');
      },
      error: (err: any) => {
        this.loading = false;
        this.errorMessage = "Fallo obteniendo la URL en servidor: " + (err.error?.detail || err.message);
        this.cdr.detectChanges();
      }
    });
  }

  prevStep() {
    if (this.currentStep > 1) {
      this.currentStep--;
      this.errorMessage = '';
      this.cdr.detectChanges();
    }
  }

  finishSetup() {
    this.loading = true;
    this.errorMessage = '';
    this.cdr.detectChanges();
    
    const configs: any = {
      TZ: this.timezone,
      MODEL_PROVIDER: this.llmProvider
    };
    if (this.googleApiKey) configs.GOOGLE_API_KEY = this.googleApiKey;
    if (this.openaiApiKey) configs.OPENAI_API_KEY = this.openaiApiKey;
    if (this.anthropicApiKey) configs.ANTHROPIC_API_KEY = this.anthropicApiKey;
    
    if (this.googleClientId) configs.GOOGLE_CLIENT_ID = this.googleClientId;
    if (this.googleClientSecret) configs.GOOGLE_CLIENT_SECRET = this.googleClientSecret;
    
    if (this.telegramToken) configs.TELEGRAM_TOKEN = this.telegramToken;
    if (this.telegramChatId) configs.TELEGRAM_CHAT_ID = this.telegramChatId;
    if (this.webhookUrl) configs.WEBHOOK_URL = this.webhookUrl;

    this.setupService.saveConfigs(configs).subscribe({
      next: () => {
        this.setupService.savePreferences(this.userName, this.preferredName, this.agentName, this.agentPersonality).subscribe({
          next: () => {
            this.loading = false;
            this.cdr.detectChanges();
            window.location.href = '/chat';
          },
          error: (err) => {
             this.loading = false;
             this.errorMessage = 'Se guardó configuración pero falló la memoria: ' + (err.error?.detail || err.message);
             this.cdr.detectChanges();
          }
        });
      },
      error: (err) => {
         this.loading = false;
         this.errorMessage = 'No se pudo aplicar al .env: ' + (err.error?.detail || err.message);
         this.cdr.detectChanges();
      }
    });
  }

  skipWorkspace() {
    this.googleClientId = '';
    this.googleClientSecret = '';
    this.currentStep++;
    this.cdr.detectChanges();
  }

  skipTelegram() {
     this.telegramToken = '';
     this.telegramChatId = '';
     this.finishSetup();
  }
}


