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

  private readonly BASE_AGENTS = ['assistant', 'dev', 'mcp', 'researcher'];

  ngOnInit() {
    this.api.getAgents().subscribe({
      next: (data) => {
        this.systemAgents.set(data.filter(a => this.BASE_AGENTS.includes(a.name)));
        this.customAgents.set(data.filter(a => !this.BASE_AGENTS.includes(a.name)));
        this.loading.set(false);
      },
      error: () => this.loading.set(false)
    });
  }
}
