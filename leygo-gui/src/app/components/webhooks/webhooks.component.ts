import { Component, inject, signal, OnInit, Pipe, PipeTransform } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { ToastService } from '@services/toast.service';
import { ConfirmService } from '@services/confirm.service';
import { ApiService } from '../../api.service';
import { MarkdownPipe } from '../../pipes/markdown.pipe';
import { FriendlyDatePipe } from '../../pipes/friendly-date.pipe';

interface Webhook {
  id: string;
  titulo: string;
  descripcion: string;
  modelo: string;
  paused: boolean;
  fecha_creacion: string;
}

export interface WebhookLog {
  webhook_id: string;
  timestamp: string;
  payload: string;
  response: string;
  error?: string;
  _expandedPayload?: boolean;
  _expandedResponse?: boolean;
}

interface ModelOption {
  value: string;
  label: string;
  provider: 'google' | 'anthropic' | 'openai' | 'ollama' | 'default';
}

@Pipe({
  name: 'filterProvider',
  standalone: true
})
export class FilterProviderPipe implements PipeTransform {
  transform(items: ModelOption[], provider: string): ModelOption[] {
    if (!items) return [];
    return items.filter(it => it.provider === provider);
  }
}

@Component({
  selector: 'app-webhooks',
  standalone: true,
  imports: [CommonModule, FormsModule, FilterProviderPipe, MarkdownPipe, FriendlyDatePipe],
  templateUrl: './webhooks.component.html',
  styleUrls: ['./webhooks.component.css']
})
export class WebhooksComponent implements OnInit {
  api = inject(ApiService);
  private toast = inject(ToastService);
  private confirmService = inject(ConfirmService);

  webhooks = signal<Webhook[]>([]);
  loading = signal<boolean>(true);

  // Logs state
  logs = signal<WebhookLog[]>([]);
  logsLoading = signal<boolean>(false);
  logsInterval: any;
  logsPanelOpen = signal<boolean>(false);
  selectedWebhookId = signal<string | null>(null);

  // Modal form state
  showModal = signal<boolean>(false);
  editMode = signal<boolean>(false);
  currentId = signal<string | null>(null);
  
  formData = signal({
    titulo: '',
    descripcion: '',
    modelo: ''
  });

  availableModels = signal<ModelOption[]>([
    { value: 'gemini-2.0-flash', label: 'Default System', provider: 'default' }
  ]);
  modelsLoading = signal<boolean>(false);

  ngOnInit() {
    this.loadWebhooks();
    this.loadAllModels();
    this.loadAllLogs();
    
    // Auto-refresh logs every 10 seconds
    this.logsInterval = setInterval(() => {
      this.loadAllLogs(true);
    }, 10000);
  }

  ngOnDestroy() {
    if (this.logsInterval) {
      clearInterval(this.logsInterval);
    }
  }

  loadAllLogs(silent = false) {
    if (!this.logsPanelOpen()) return; // Solo carga si el panel está abierto
    
    if (!silent) this.logsLoading.set(true);
    
    const ob$ = this.selectedWebhookId() 
      ? this.api.getWebhookLogs(this.selectedWebhookId()!)
      : this.api.getAllWebhookLogs();

    ob$.subscribe({
      next: (data) => {
        this.logs.set(data || []);
        this.logsLoading.set(false);
      },
      error: (e) => {
        console.error('Error cargando logs:', e);
        this.logsLoading.set(false);
      }
    });
  }

  openLogs(webhookId?: string) {
    this.selectedWebhookId.set(webhookId || null);
    this.logsPanelOpen.set(true);
    this.loadAllLogs();
  }

  closeLogs() {
    this.logsPanelOpen.set(false);
    this.selectedWebhookId.set(null);
  }

  getWebhookTitle(id: string): string {
    const wh = this.webhooks().find(w => w.id === id);
    return wh ? wh.titulo : 'Webhook Eliminado ' + id.substring(0, 4);
  }

  loadWebhooks() {
    this.loading.set(true);
    this.api.getWebhooks().subscribe({
      next: (data) => {
        this.webhooks.set(data || []);
        this.loading.set(false);
      },
      error: (e) => {
        console.error('Error cargando webhooks:', e);
        this.loading.set(false);
      }
    });
  }

  loadAllModels() {
    this.modelsLoading.set(true);
    forkJoin({
      gemini: this.api.getGeminiModels().pipe(catchError(() => of({ models: [] }))),
      anthropic: this.api.getAnthropicModels().pipe(catchError(() => of({ models: [] }))),
      openai: this.api.getOpenaiModels().pipe(catchError(() => of({ models: [] }))),
      ollama: this.api.getOllamaTags().pipe(catchError(() => of({ models: [] }))),
    }).subscribe(({ gemini, anthropic, openai, ollama }) => {
      const all: ModelOption[] = [];

      for (const item of (gemini?.models ?? [])) {
        const m: any = item;
        const name = typeof m === 'string' ? m : m.name;
        const label = typeof m === 'string' ? m : (m.displayName || m.name);
        all.push({ value: name, label, provider: 'google' });
      }
      for (const item of (anthropic?.models ?? [])) {
        const m: any = item;
        const name = typeof m === 'string' ? m : m.name;
        const label = typeof m === 'string' ? m : (m.displayName || m.name);
        all.push({ value: name, label, provider: 'anthropic' });
      }
      for (const item of (openai?.models ?? [])) {
        const m: any = item;
        const name = typeof m === 'string' ? m : m.name;
        const label = typeof m === 'string' ? m : (m.displayName || m.name);
        all.push({ value: name, label, provider: 'openai' });
      }
      for (const item of (ollama?.models ?? [])) {
        const m: any = item;
        const name = typeof m === 'string' ? m : m.name;
        all.push({ value: name, label: name, provider: 'ollama' });
      }

      this.availableModels.set([
        { value: 'gemini-2.0-flash', label: 'Default System (Gemini Flash)', provider: 'default' },
        ...all
      ]);
      this.modelsLoading.set(false);
    });
  }

  openCreateModal() {
    this.editMode.set(false);
    this.currentId.set(null);
    this.formData.set({
      titulo: '',
      descripcion: '',
      modelo: 'gemini-2.0-flash'
    });
    this.showModal.set(true);
  }

  openEditModal(webhook: Webhook) {
    this.editMode.set(true);
    this.currentId.set(webhook.id);
    this.formData.set({
      titulo: webhook.titulo,
      descripcion: webhook.descripcion,
      modelo: webhook.modelo || 'gemini-2.0-flash'
    });
    this.showModal.set(true);
  }

  closeModal() {
    this.showModal.set(false);
  }

  saveWebhook() {
    const data = this.formData();
    if (!data.titulo || !data.descripcion || !data.modelo) {
      this.toast.show("Por favor completa todos los campos (título, descripción y modelo).", 'warning', '', 5000, 'bottom-right');
      return;
    }

    if (this.editMode() && this.currentId()) {
      // Edit
      this.api.updateWebhook(this.currentId()!, data).subscribe({
        next: () => {
          this.loadWebhooks();
          this.closeModal();
        },
        error: (e) => {
          this.toast.show('Error actualizando webhook', 'danger', '', 5000, 'bottom-right');
          console.error(e);
        }
      });
    } else {
      // Create
      this.api.createWebhook(data).subscribe({
        next: () => {
          this.loadWebhooks();
          this.closeModal();
        },
        error: (e) => {
          this.toast.show('Error creando webhook', 'danger', '', 5000, 'bottom-right');
          console.error(e);
        }
      });
    }
  }

  togglePauseState(webhook: Webhook) {
    this.api.updateWebhook(webhook.id, { paused: !webhook.paused }).subscribe({
      next: () => this.loadWebhooks(),
      error: (e) => console.error("Error cambiando estado:", e)
    });
  }

  async deleteWebhook(webhook: Webhook) {
    const isConfirmed = await this.confirmService.confirm(`¿Estás seguro de eliminar el webhook '${webhook.titulo}'? Esta acción no se puede deshacer y la URL dejará de funcionar inmediatamente.`);
    if (isConfirmed) {
      this.api.deleteWebhook(webhook.id).subscribe({
        next: () => {
          this.toast.show('Webhook eliminado', 'success', '', 5000, 'bottom-right');
          this.loadWebhooks();
        },
        error: (e) => {
          this.toast.show('Error eliminando webhook', 'danger', '', 5000, 'bottom-right');
          console.error("Error eliminando webhook:", e);
        }
      });
    }
  }

  copyToClipboard(id: string) {
    const host = window.location.host;
    const protocol = window.location.protocol;
    // Format to point to the backend 8000/8443 port typically. Assume backend runs where the API base is.
    // However, user stated target as `https://jesus.leygo.cl:8443/webhook/{uuid}`
    // Since API base URL is usually handled config, we can assemble a full path.
    // If the backend runs on port 8443 currently vs 80, we should guess based on `this.api.baseUrl`.
    const apiBase = this.api["baseUrl"];
    let webhookUrl = '';
    // if api is http://localhost:8000/api
    if (apiBase.endsWith('/api')) {
      webhookUrl = apiBase + `/webhook/${id}`;
    } else {
      webhookUrl = `${protocol}//${host}/api/webhook/${id}`;
    }

    navigator.clipboard.writeText(webhookUrl).then(() => {
      this.toast.show('URL del Webhook copiada al portapapeles', 'success', '', 5000, 'bottom-right');
    });
  }

  getModelLabel(modelId: string): string {
    const m = this.availableModels().find(x => x.value === modelId);
    return m ? `${m.label} (${m.provider})` : modelId;
  }
}
