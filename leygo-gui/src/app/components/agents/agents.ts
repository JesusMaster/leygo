import { Component, inject, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ApiService, Agent } from '../../api.service';
import { ToastService } from '@services/toast.service';
import { ConfirmService } from '@services/confirm.service';

@Component({
  selector: 'app-agents',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './agents.html',
  styleUrl: './agents.css'
})
export class AgentsComponent implements OnInit {
  private api = inject(ApiService);
  private router = inject(Router);
  private toast = inject(ToastService);
  private confirmService = inject(ConfirmService);
  
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

  editAgent(agentName: string) {
    this.router.navigate(['/editor', agentName]);
  }

  async deleteAgent(agentName: string) {
    const isConfirmed = await this.confirmService.confirm(`¿Estás seguro de que deseas eliminar permanentemente el agente '${agentName}'?`);
    if (isConfirmed) {
      this.api.deleteAgent(agentName).subscribe({
        next: (res) => {
          this.toast.show('Agente eliminado.', 'success', '', 5000, 'bottom-right');
          this.loadAgents();
        },
        error: (err) => this.toast.show('Error eliminando agente.', 'danger', '', 5000, 'bottom-right')
      });
    }
  }
}
