import { Component, inject, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService, Agent } from '../../api.service';

@Component({
  selector: 'app-agents',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './agents.html',
  styleUrl: './agents.css'
})
export class AgentsComponent implements OnInit {
  private api = inject(ApiService);
  systemAgents = signal<Agent[]>([]);
  customAgents = signal<Agent[]>([]);
  loading = signal(true);

  private readonly BASE_AGENTS = ['assistant', 'dev', 'mcp', 'researcher', 'file_reader'];

  ngOnInit() {
    this.loadAgents();
  }

  loadAgents() {
    this.loading.set(true);
    this.api.getAgents().subscribe({
      next: (data) => {
        this.systemAgents.set(data.filter(a => this.BASE_AGENTS.includes(a.name)));
        this.customAgents.set(data.filter(a => !this.BASE_AGENTS.includes(a.name)));
        this.loading.set(false);
      },
      error: () => this.loading.set(false)
    });
  }

  // Editor modal state
  showEditModal = signal(false);
  editingAgentName = signal('');
  agentFiles = signal({
    python_code: '',
    episodic_code: '',
    procedural_code: '',
    prefs_code: '',
    env_code: ''
  });
  
  envVars = signal<{key: string, value: string}[]>([]);

  editAgent(agentName: string) {
    this.editingAgentName.set(agentName);
    this.api.getAgentFiles(agentName).subscribe({
      next: (files) => {
        this.agentFiles.set({
          python_code: files.python_code || '',
          episodic_code: files.episodic_code || '',
          procedural_code: files.procedural_code || '',
          prefs_code: files.prefs_code || '',
          env_code: files.env_code || ''
        });
        this.parseEnvCode(files.env_code || '');
        this.showEditModal.set(true);
      },
      error: (err) => {
        alert('Error al obtener archivos del agente.');
      }
    });
  }

  parseEnvCode(envString: string) {
    const lines = envString.split('\n');
    const vars: {key: string, value: string}[] = [];
    for (const line of lines) {
      if (line.trim().length === 0 || line.startsWith('#')) continue;
      const parts = line.split('=');
      const key = parts[0].trim();
      const value = parts.slice(1).join('=').trim();
      if (key) vars.push({ key, value });
    }
    this.envVars.set(vars);
  }

  serializeEnvCode(): string {
    return this.envVars().map(v => `${v.key}=${v.value}`).join('\n');
  }

  addEnvVar() {
    this.envVars.update(vars => [...vars, { key: '', value: '' }]);
  }

  removeEnvVar(index: number) {
    this.envVars.update(vars => vars.filter((_, i) => i !== index));
  }

  closeEditModal() {
    this.showEditModal.set(false);
    this.editingAgentName.set('');
  }

  saveAgentFiles() {
    const name = this.editingAgentName();
    const data = this.agentFiles();
    data.env_code = this.serializeEnvCode();
    
    this.api.updateAgentFiles(name, data).subscribe({
      next: () => {
        alert('Agente actualizado correctamente. Recarga en caliente aplicada.');
        this.closeEditModal();
        this.loadAgents();
      },
      error: (err) => {
        console.error(err);
        alert('Error guardando archivos del agente.');
      }
    });
  }

  deleteAgent(agentName: string) {
    if (confirm(`¿Estás seguro de que deseas eliminar permanentemente el agente '${agentName}'?`)) {
      this.api.deleteAgent(agentName).subscribe({
        next: (res) => {
          this.loadAgents();
        },
        error: (err) => {
          console.error('Error al borrar el sub-agente', err);
          alert('Error al intentar borrar el sub-agente.');
        }
      });
    }
  }
}
