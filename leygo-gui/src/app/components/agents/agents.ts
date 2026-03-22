import { Component, inject, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService, Agent } from '../../api.service';

@Component({
  selector: 'app-agents',
  standalone: true,
  imports: [CommonModule],
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
