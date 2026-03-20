import { Component, inject, signal, computed, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
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
  imports: [CommonModule, FormsModule],
  templateUrl: './usage.html',
  styleUrl: './usage.css'
})
export class UsageComponent implements OnInit {
  private api = inject(ApiService);
  
  // Data cruda (toda la historia invertida, más reciente primero)
  allHistory = signal<UsageRecord[]>([]);
  loading = signal(true);
  
  // Totales calculados para el mes (sin filtros)
  totalCost = signal(0);
  totalTokens = signal(0);
  
  // Presupuesto mensual
  monthlyBudget = signal(3.0);
  isEditingBudget = signal(false);
  editBudgetValue = signal<number>(3.0);
  budgetLoading = signal(false);
  
  // Filtros
  filterModel = signal('');
  filterDateFrom = signal('');
  filterDateTo = signal('');
  
  // Control de paginación / límite visual
  displayLimit = signal(20);
  
  // Lista de modelos únicos para el selector
  availableModels = computed(() => {
    const models = new Set<string>();
    this.allHistory().forEach(r => {
      if (r.model) models.add(r.model);
    });
    return Array.from(models).sort();
  });
  
  // Registros filtrados con lógica de "último día o últimos 20"
  filteredHistory = computed(() => {
    let records = this.allHistory();
    const hasActiveFilter = this.filterModel() || this.filterDateFrom() || this.filterDateTo();
    
    // Aplicar filtro por modelo
    if (this.filterModel()) {
      records = records.filter(r => r.model === this.filterModel());
    }
    
    // Aplicar filtro por fecha "desde"
    if (this.filterDateFrom()) {
      const from = new Date(this.filterDateFrom());
      from.setHours(0, 0, 0, 0);
      records = records.filter(r => {
        try { return new Date(r.timestamp) >= from; }
        catch { return true; }
      });
    }
    
    // Aplicar filtro por fecha "hasta"
    if (this.filterDateTo()) {
      const to = new Date(this.filterDateTo());
      to.setHours(23, 59, 59, 999);
      records = records.filter(r => {
        try { return new Date(r.timestamp) <= to; }
        catch { return true; }
      });
    }
    
    // Si hay filtros activos, devolver todo lo filtrado (con limit)
    if (hasActiveFilter) {
      return records.slice(0, this.displayLimit());
    }
    
    // Sin filtros: mostrar registros del último día
    const todayRecords = this.getLastDayRecords(records);
    if (todayRecords.length > 0) {
      return todayRecords.slice(0, this.displayLimit());
    }
    
    // Si no hay registros del último día, últimos 20
    return records.slice(0, this.displayLimit());
  });
  
  // Totales de la vista filtrada
  filteredCost = computed(() => {
    return this.filteredHistory().reduce((sum, r) => sum + (r.cost_usd || 0), 0);
  });
  
  filteredTokens = computed(() => {
    return this.filteredHistory().reduce((sum, r) => sum + (r.input_tokens || 0) + (r.output_tokens || 0), 0);
  });
  
  // ¿Se puede cargar más?
  canLoadMore = computed(() => {
    const hasActiveFilter = this.filterModel() || this.filterDateFrom() || this.filterDateTo();
    if (hasActiveFilter) {
      // Contar cuántos registros matchean después de filtros
      let records = this.allHistory();
      if (this.filterModel()) records = records.filter(r => r.model === this.filterModel());
      if (this.filterDateFrom()) {
        const from = new Date(this.filterDateFrom());
        from.setHours(0, 0, 0, 0);
        records = records.filter(r => { try { return new Date(r.timestamp) >= from; } catch { return true; } });
      }
      if (this.filterDateTo()) {
        const to = new Date(this.filterDateTo());
        to.setHours(23, 59, 59, 999);
        records = records.filter(r => { try { return new Date(r.timestamp) <= to; } catch { return true; } });
      }
      return records.length > this.displayLimit();
    }
    const todayRecords = this.getLastDayRecords(this.allHistory());
    if (todayRecords.length > 0) return todayRecords.length > this.displayLimit();
    return this.allHistory().length > this.displayLimit();
  });
  
  // Etiqueta del filtro actual
  activeFilterLabel = computed(() => {
    const hasActiveFilter = this.filterModel() || this.filterDateFrom() || this.filterDateTo();
    if (hasActiveFilter) return 'Resultados filtrados';
    const todayRecords = this.getLastDayRecords(this.allHistory());
    if (todayRecords.length > 0) return 'Registros del último día';
    return `Últimos ${Math.min(this.displayLimit(), this.allHistory().length)} registros`;
  });

  ngOnInit() {
    this.loadConfig();
    this.loadUsage();
  }
  
  loadConfig() {
    this.api.getConfig().subscribe(config => {
      const budgetStr = config['MONTHLY_BUDGET_USD'];
      if (budgetStr !== undefined && budgetStr !== null && budgetStr !== '') {
        const val = parseFloat(budgetStr);
        if (!isNaN(val)) {
          this.monthlyBudget.set(val);
          this.editBudgetValue.set(val);
        }
      }
    });
  }
  
  toggleEditBudget() {
    this.isEditingBudget.set(!this.isEditingBudget());
    this.editBudgetValue.set(this.monthlyBudget());
  }

  saveBudget() {
    if (this.editBudgetValue() < 0) return;
    this.budgetLoading.set(true);
    this.api.updateConfig('MONTHLY_BUDGET_USD', this.editBudgetValue().toString()).subscribe({
      next: () => {
        this.monthlyBudget.set(this.editBudgetValue());
        this.isEditingBudget.set(false);
        this.budgetLoading.set(false);
      },
      error: () => {
        this.budgetLoading.set(false);
        alert('Error al guardar el presupuesto');
      }
    });
  }

  loadUsage() {
    this.loading.set(true);
    this.api.getUsageHistory().subscribe({
      next: (data) => {
        const history = [...data].reverse();
        this.allHistory.set(history);
        
        // Totales globales del mes actual (independiente de filtros)
        let costSum = 0;
        let tokenSum = 0;
        const now = new Date();
        history.forEach(r => {
          try {
            const rowDate = new Date(r.timestamp);
            if (rowDate.getMonth() === now.getMonth() && rowDate.getFullYear() === now.getFullYear()) {
              costSum += (r.cost_usd || 0);
              tokenSum += ((r.input_tokens || 0) + (r.output_tokens || 0));
            }
          } catch(e) {}
        });
        
        this.totalCost.set(costSum);
        this.totalTokens.set(tokenSum);
        this.loading.set(false);
      },
      error: () => this.loading.set(false)
    });
  }
  
  loadMore() {
    this.displayLimit.update(v => v + 50);
  }
  
  clearFilters() {
    this.filterModel.set('');
    this.filterDateFrom.set('');
    this.filterDateTo.set('');
    this.displayLimit.set(20);
  }
  
  onFilterChange() {
    this.displayLimit.set(20);
  }
  
  private getLastDayRecords(records: UsageRecord[]): UsageRecord[] {
    if (records.length === 0) return [];
    
    // El primer registro es el más reciente (ya está invertido)
    try {
      const latestDate = new Date(records[0].timestamp);
      const dayStart = new Date(latestDate);
      dayStart.setHours(0, 0, 0, 0);
      const dayEnd = new Date(latestDate);
      dayEnd.setHours(23, 59, 59, 999);
      
      return records.filter(r => {
        try {
          const d = new Date(r.timestamp);
          return d >= dayStart && d <= dayEnd;
        } catch { return false; }
      });
    } catch { return []; }
  }
}
