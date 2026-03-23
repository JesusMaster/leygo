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
    md_code: '',
    env_code: ''
  });

  editAgent(agentName: string) {
    this.editingAgentName.set(agentName);
    this.api.getAgentFiles(agentName).subscribe({
      next: (files) => {
        this.agentFiles.set(files);
        this.showEditModal.set(true);
      },
      error: (err) => {
        alert('Error al obtener archivos del agente.');
      }
    });
  }

  closeEditModal() {
    this.showEditModal.set(false);
    this.editingAgentName.set('');
  }

  saveAgentFiles() {
    const name = this.editingAgentName();
    const data = this.agentFiles();
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
