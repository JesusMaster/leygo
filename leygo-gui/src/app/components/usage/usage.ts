import { Component, inject, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService } from '../../api.service';

interface UsageRecord {
  timestamp: string;
  user_input: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  thread_id: string;
}

@Component({
  selector: 'app-usage',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './usage.html',
  styleUrl: './usage.css'
})
export class UsageComponent implements OnInit {
  private api = inject(ApiService);
  usageHistory = signal<UsageRecord[]>([]);
  loading = signal(true);
  
  // Totales calculados
  totalCost = signal(0);
  totalTokens = signal(0);

  ngOnInit() {
    this.loadUsage();
  }

  loadUsage() {
    this.loading.set(true);
    this.api.getUsageHistory().subscribe({
      next: (data) => {
        // Invertimos para ver el más reciente primero
        const history = [...data].reverse();
        this.usageHistory.set(history);
        
        let costSum = 0;
        let tokenSum = 0;
        history.forEach(r => {
          costSum += (r.cost_usd || 0);
          tokenSum += ((r.input_tokens || 0) + (r.output_tokens || 0));
        });
        
        this.totalCost.set(costSum);
        this.totalTokens.set(tokenSum);
        this.loading.set(false);
      },
      error: () => this.loading.set(false)
    });
  }
}
