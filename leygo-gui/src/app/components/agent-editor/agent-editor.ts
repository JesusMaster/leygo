import { Component, inject, signal, OnInit, computed, HostListener, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService, AgentFileNode } from '../../api.service';
import { ActivatedRoute, Router } from '@angular/router';
import { MonacoEditorModule } from 'ngx-monaco-editor-v2';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

export interface ModelOption {
  value: string;
  label: string;
  provider: 'google' | 'anthropic' | 'openai' | 'ollama';
}

const PROVIDER_ICONS: Record<string, string> = {
  google: '✦',
  anthropic: '◆',
  openai: '⬡',
  ollama: '⬟',
};

@Component({
  selector: 'app-agent-editor',
  standalone: true,
  imports: [CommonModule, FormsModule, MonacoEditorModule],
  templateUrl: './agent-editor.html',
  styleUrl: './agent-editor.css'
})
export class AgentEditorComponent implements OnInit {
  private el = inject(ElementRef);

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent) {
    if (!this.el.nativeElement.contains(event.target)) {
      this.modelSelectorOpen.set(false);
    }
  }
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  agentName = signal<string>('');
  files = signal<AgentFileNode[]>([]);
  deletedFiles = signal<string[]>([]);

  loading = signal(true);
  saving = signal(false);

  selectedFile = signal<AgentFileNode | null>(null);
  editorOptions = signal({ theme: 'vs-dark', language: 'python', automaticLayout: true });

  // Model selector state
  availableModels = signal<ModelOption[]>([]);
  selectedModel = signal<string>('');
  modelSelectorOpen = signal(false);
  savingModel = signal(false);
  modelsLoading = signal(false);

  // Grouped models for display
  groupedModels = computed(() => {
    const groups: Record<string, ModelOption[]> = {};
    for (const m of this.availableModels()) {
      if (!groups[m.provider]) groups[m.provider] = [];
      groups[m.provider].push(m);
    }
    return groups;
  });

  providerGroups = computed(() => Object.keys(this.groupedModels()));

  selectedModelLabel = computed(() => {
    const m = this.availableModels().find(x => x.value === this.selectedModel());
    return m?.label ?? this.selectedModel() ?? 'Seleccionar modelo';
  });

  selectedModelProvider = computed(() => {
    return this.availableModels().find(x => x.value === this.selectedModel())?.provider ?? 'google';
  });

  providerIcon(provider: string): string {
    return PROVIDER_ICONS[provider] ?? '●';
  }

  providerLabel(provider: string): string {
    const labels: Record<string, string> = {
      google: 'Google Gemini',
      anthropic: 'Anthropic Claude',
      openai: 'OpenAI GPT',
      ollama: 'Ollama (Local)',
    };
    return labels[provider] ?? provider;
  }

  ngOnInit() {
    this.route.paramMap.subscribe(params => {
      const name = params.get('agentName');
      if (name) {
        this.agentName.set(name);
        this.loadTree();
        this.loadAllModels();
      }
    });
  }

  loadTree() {
    this.loading.set(true);
    this.api.getAgentTree(this.agentName()).subscribe({
      next: (data) => {
        this.files.set(data);
        this.deletedFiles.set([]);
        if (data.length > 0) {
          const mainFile = data.find(f => f.path.endsWith('_agent.py')) || data[0];
          this.selectFile(mainFile);
          this.readModelFromEnv(data);
        }
        this.loading.set(false);
      },
      error: () => this.loading.set(false)
    });
  }

  /** Read MODEL or MODEL_OVERRIDE from agent's .env file */
  readModelFromEnv(files: AgentFileNode[]) {
    const envFile = files.find(f => f.path === '.env');
    if (!envFile) return;
    const lines = envFile.content.split('\n');
    let model = '';
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('MODEL_OVERRIDE=')) {
        model = trimmed.split('=').slice(1).join('=').trim();
        break;
      } else if (trimmed.startsWith('MODEL=') && !model) {
        model = trimmed.split('=').slice(1).join('=').trim();
      }
    }
    if (model) this.selectedModel.set(model);
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

      for (const m of (gemini?.models ?? [])) {
        const name = typeof m === 'string' ? m : m.name;
        const label = typeof m === 'string' ? m : (m.displayName || m.name);
        all.push({ value: name, label, provider: 'google' });
      }
      for (const m of (anthropic?.models ?? [])) {
        const name = typeof m === 'string' ? m : m.name;
        const label = typeof m === 'string' ? m : (m.displayName || m.name);
        all.push({ value: name, label, provider: 'anthropic' });
      }
      for (const m of (openai?.models ?? [])) {
        const name = typeof m === 'string' ? m : m.name;
        const label = typeof m === 'string' ? m : (m.displayName || m.name);
        all.push({ value: name, label, provider: 'openai' });
      }
      for (const m of (ollama?.models ?? [])) {
        const rawName = typeof m === 'string' ? m : (m as any).name;
        const value = rawName.startsWith('ollama/') ? rawName : `ollama/${rawName}`;
        all.push({ value, label: rawName, provider: 'ollama' });
      }

      this.availableModels.set(all);
      this.modelsLoading.set(false);
    });
  }

  selectModel(modelValue: string) {
    if (modelValue === this.selectedModel()) {
      this.modelSelectorOpen.set(false);
      return;
    }
    this.selectedModel.set(modelValue);
    this.modelSelectorOpen.set(false);
    this.saveModelToEnv(modelValue);
  }

  /** Replace MODEL= in agent .env (and remove MODEL_OVERRIDE) to avoid conflicts */
  saveModelToEnv(modelValue: string) {
    this.savingModel.set(true);
    const envFilePath = '.env';

    let envFile = this.files().find(f => f.path === envFilePath);
    let isNew = false;

    if (!envFile) {
      envFile = { path: envFilePath, content: '' };
      isNew = true;
    }

    // 1. Remove MODEL_OVERRIDE lines (keep .env clean/no duplicates)
    // 2. Replace existing MODEL= or append it
    let lines = envFile.content.split('\n')
      .filter(l => !l.trim().startsWith('MODEL_OVERRIDE='));

    const modelIdx = lines.findIndex(l => l.trim().startsWith('MODEL='));
    const newLine = `MODEL=${modelValue}`;

    if (modelIdx >= 0) {
      lines[modelIdx] = newLine;
    } else {
      if (lines.length > 0 && lines[lines.length - 1].trim() !== '') {
        lines.push('');
      }
      lines.push(newLine);
    }

    const updatedContent = lines.join('\n');

    if (isNew) {
      const newEnvFile: AgentFileNode = { path: envFilePath, content: updatedContent };
      this.files.update(f => [...f, newEnvFile]);
    } else {
      this.files.update(f => f.map(x => x.path === envFilePath ? { ...x, content: updatedContent } : x));
    }

    // Persist to backend immediately
    this.api.updateAgentTree(this.agentName(), {
      files: this.files(),
      deleted_paths: this.deletedFiles()
    }).subscribe({
      next: () => this.savingModel.set(false),
      error: () => {
        this.savingModel.set(false);
        alert('Error guardando el modelo en .env');
      }
    });
  }

  toggleModelSelector() {
    this.modelSelectorOpen.update(v => !v);
  }

  closeModelSelector() {
    this.modelSelectorOpen.set(false);
  }

  selectFile(file: AgentFileNode) {
    this.selectedFile.set(file);
    let lang = 'plaintext';
    if (file.path.endsWith('.py')) lang = 'python';
    else if (file.path.endsWith('.md')) lang = 'markdown';
    else if (file.path.endsWith('.json')) lang = 'json';
    else if (file.path.endsWith('.env')) lang = 'ini';

    this.editorOptions.set({
      theme: 'vs-dark',
      language: lang,
      automaticLayout: true
    });
  }

  createNewFile() {
    const filename = prompt('Ingresa la ruta relativa del nuevo archivo (ej: memoria/nuevo_conocimiento.md):');
    if (!filename) return;

    if (this.files().find(f => f.path === filename)) {
      alert('Ese archivo ya existe.');
      return;
    }

    const newFile: AgentFileNode = { path: filename, content: '' };
    this.files.update(f => [...f, newFile]);
    this.selectFile(newFile);
  }

  deleteFile(file: AgentFileNode) {
    if (file.path.endsWith('_agent.py')) {
      alert('No puedes eliminar el archivo controlador principal del agente.');
      return;
    }
    if (confirm(`¿Eliminar ${file.path}?`)) {
      this.files.update(f => f.filter(x => x.path !== file.path));
      this.deletedFiles.update(d => [...d, file.path]);
      if (this.selectedFile()?.path === file.path) {
        this.selectedFile.set(this.files()[0] || null);
      }
    }
  }

  saveAll() {
    this.saving.set(true);
    this.api.updateAgentTree(this.agentName(), {
      files: this.files(),
      deleted_paths: this.deletedFiles()
    }).subscribe({
      next: () => {
        this.saving.set(false);
        alert('Archivos guardados con éxito.');
        this.loadTree();
      },
      error: (e) => {
        this.saving.set(false);
        alert('Error guardando archivos: ' + e.message);
      }
    });
  }

  goBack() {
    this.router.navigate(['/agents']);
  }
}
