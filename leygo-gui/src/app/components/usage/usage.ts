import { Component, inject, signal, computed, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../api.service';
import { ToastService } from '@services/toast.service';
import { FriendlyDatePipe } from '../../pipes/friendly-date.pipe';

interface UsageRecord {
  timestamp: string;
  user_input: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  thread_id: string;
}

interface OperationGroup {
  id: string;               // thread_id + timestamp inicio
  timestamp: string;        // timestamp del primer registro
  label: string;            // texto del user_input principal (sin prefijo)
  thread_id: string;
  records: UsageRecord[];
  total_cost: number;
  total_input_tokens: number;
  total_output_tokens: number;
  models: string[];         // modelos únicos usados
  expanded: boolean;
}

@Component({
  selector: 'app-usage',
  standalone: true,
  imports: [CommonModule, FormsModule, FriendlyDatePipe],
  templateUrl: './usage.html',
  styleUrl: './usage.css'
})
export class UsageComponent implements OnInit {
  private api = inject(ApiService);
  private toast = inject(ToastService);

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

  // Vista agrupada o detalle
  groupedView = signal(true);

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

  // Registros filtrados (sin agrupar)
  filteredHistory = computed(() => {
    let records = this.allHistory();
    const hasActiveFilter = this.filterModel() || this.filterDateFrom() || this.filterDateTo();

    if (this.filterModel()) {
      records = records.filter(r => r.model === this.filterModel());
    }
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

    if (hasActiveFilter) return records.slice(0, this.displayLimit());
    const todayRecords = this.getLastDayRecords(records);
    if (todayRecords.length > 0) return todayRecords.slice(0, this.displayLimit());
    return records.slice(0, this.displayLimit());
  });

  // Registros agrupados por operación (thread_id + ventana 30s)
  groupedOperations = computed(() => {
    const records = this.filteredHistory();
    // La lista ya viene ordenada de más reciente a más antigua
    // Agrupamos de atrás hacia adelante para que el orden sea natural
    const chronological = [...records].reverse();
    const groups: OperationGroup[] = [];

    for (const record of chronological) {
      const recTime = new Date(record.timestamp).getTime();
      const lastGroup = groups[groups.length - 1];

      // Pertenece al grupo si mismo thread_id y diff < 30s desde el ultimo registro del grupo
      if (
        lastGroup &&
        lastGroup.thread_id === record.thread_id &&
        Math.abs(recTime - new Date(lastGroup.records[lastGroup.records.length - 1].timestamp).getTime()) <= 30000
      ) {
        lastGroup.records.push(record);
        lastGroup.total_cost += record.cost_usd || 0;
        lastGroup.total_input_tokens += record.input_tokens || 0;
        lastGroup.total_output_tokens += record.output_tokens || 0;
        if (record.model && !lastGroup.models.includes(record.model)) {
          lastGroup.models.push(record.model);
        }
      } else {
        // Nuevo grupo
        const label = this.extractLabel(record.user_input);
        groups.push({
          id: `${record.thread_id}_${record.timestamp}`,
          timestamp: record.timestamp,
          label,
          thread_id: record.thread_id,
          records: [record],
          total_cost: record.cost_usd || 0,
          total_input_tokens: record.input_tokens || 0,
          total_output_tokens: record.output_tokens || 0,
          models: record.model ? [record.model] : [],
          expanded: false,
        });
      }
    }

    // Invertir para que el más reciente quede primero
    return groups.reverse();
  });

  // Totales de la vista filtrada
  filteredCost = computed(() => this.filteredHistory().reduce((s, r) => s + (r.cost_usd || 0), 0));
  filteredTokens = computed(() => this.filteredHistory().reduce((s, r) => s + (r.input_tokens || 0) + (r.output_tokens || 0), 0));

  canLoadMore = computed(() => {
    const hasActiveFilter = this.filterModel() || this.filterDateFrom() || this.filterDateTo();
    if (hasActiveFilter) {
      let records = this.allHistory();
      if (this.filterModel()) records = records.filter(r => r.model === this.filterModel());
      if (this.filterDateFrom()) {
        const from = new Date(this.filterDateFrom()); from.setHours(0, 0, 0, 0);
        records = records.filter(r => { try { return new Date(r.timestamp) >= from; } catch { return true; } });
      }
      if (this.filterDateTo()) {
        const to = new Date(this.filterDateTo()); to.setHours(23, 59, 59, 999);
        records = records.filter(r => { try { return new Date(r.timestamp) <= to; } catch { return true; } });
      }
      return records.length > this.displayLimit();
    }
    const todayRecords = this.getLastDayRecords(this.allHistory());
    if (todayRecords.length > 0) return todayRecords.length > this.displayLimit();
    return this.allHistory().length > this.displayLimit();
  });

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
        this.toast.show('Error al guardar el presupuesto', 'danger', '', 5000, 'bottom-right');
      }
    });
  }

  loadUsage() {
    this.loading.set(true);
    this.api.getUsageHistory().subscribe({
      next: (data) => {
        const history = [...data].reverse();
        this.allHistory.set(history);

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

  toggleGroup(group: OperationGroup) {
    group.expanded = !group.expanded;
  }

  toggleViewMode() {
    this.groupedView.update(v => !v);
  }

  /** Extrae el prefijo de agente del user_input (ej: "[assistant]" → "assistant") */
  getAgentPrefix(input: string): string {
    if (!input) return '—';
    const match = input.match(/^\[(supervisor|assistant|dev|researcher|mcp|autocoder)\]/i);
    return match ? match[1] : 'sistema';
  }

  loadMore() { this.displayLimit.update(v => v + 50); }

  clearFilters() {
    this.filterModel.set('');
    this.filterDateFrom.set('');
    this.filterDateTo.set('');
    this.displayLimit.set(20);
  }

  onFilterChange() { this.displayLimit.set(20); }

  /** Extrae el texto limpio de un user_input (quita prefijo [supervisor]/[assistant]) */
  private extractLabel(input: string): string {
    if (!input) return 'Operación';
    return input.replace(/^\[(supervisor|assistant|dev|researcher|mcp)\]\s*/i, '').trim();
  }

  private getLastDayRecords(records: UsageRecord[]): UsageRecord[] {
    if (records.length === 0) return [];
    try {
      const latestDate = new Date(records[0].timestamp);
      const dayStart = new Date(latestDate);
      dayStart.setHours(0, 0, 0, 0);
      const dayEnd = new Date(latestDate);
      dayEnd.setHours(23, 59, 59, 999);
      return records.filter(r => {
        try { const d = new Date(r.timestamp); return d >= dayStart && d <= dayEnd; }
        catch { return false; }
      });
    } catch { return []; }
  }
}
