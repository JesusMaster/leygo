import { Component, inject, signal, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService, ScheduledTask } from '../../api.service';
import { ToastService } from '@services/toast.service';
import { ConfirmService } from '@services/confirm.service';
import { FriendlyDatePipe } from '../../pipes/friendly-date.pipe';

@Component({
  selector: 'app-tasks',
  standalone: true,
  imports: [CommonModule, FormsModule, FriendlyDatePipe],
  templateUrl: './tasks.html',
  styleUrl: './tasks.css'
})
export class TasksComponent implements OnInit, OnDestroy {
  private api = inject(ApiService);
  private toast = inject(ToastService);
  private confirmService = inject(ConfirmService);
  tasks = signal<ScheduledTask[]>([]);
  loading = signal(true);
  
  // Timer para polling
  private logsInterval: any;

  // Form para nuevo recordatorio
  showAddModal = signal(false);
  newTask = {
    message_or_prompt: '',
    type: 'date',
    value: '',
    is_agent_action: false
  };

  // Ejecución manual
  runningTaskId = signal<string | null>(null);

  // Logs de ejecución
  expandedLogTaskId = signal<string | null>(null);
  taskLogs = signal<any[]>([]);
  logsLoading = signal(false);

  // Estado expandido de resultados (persiste entre recargas)
  expandedResults = new Set<string>();

  getLogResultId(log: any): string {
    return `${log.task_id ?? ''}_${log.timestamp}`;
  }

  isResultExpanded(log: any): boolean {
    return this.expandedResults.has(this.getLogResultId(log));
  }

  toggleResult(log: any) {
    const id = this.getLogResultId(log);
    if (this.expandedResults.has(id)) {
      this.expandedResults.delete(id);
    } else {
      this.expandedResults.add(id);
    }
  }

  ngOnInit() {
    this.loadTasks();
  }

  ngOnDestroy() {
    this.clearLogsInterval();
  }

  private clearLogsInterval() {
    if (this.logsInterval) {
      clearInterval(this.logsInterval);
      this.logsInterval = null;
    }
  }

  loadTasks() {
    this.loading.set(true);
    this.api.getTasks().subscribe({
      next: (data) => {
        this.tasks.set(data);
        this.loading.set(false);
      },
      error: () => this.loading.set(false)
    });
  }

  async deleteTask(id: string) {
    const isConfirmed = await this.confirmService.confirm('¿Estás seguro de que quieres eliminar esta tarea?');
    if (isConfirmed) {
      this.api.deleteTask(id).subscribe({
        next: () => {
          this.toast.show('Tarea eliminada', 'success', '', 5000, 'bottom-right');
          this.loadTasks();
        },
        error: (err) => {
          console.error('Error deleting task:', err);
          this.toast.show('Hubo un error al eliminar la tarea', 'danger', '', 5000, 'bottom-right');
        }
      });
    }
  }

  editingTaskId = signal<string | null>(null);
  editingTaskValue = signal<string>('');

  startEditing(task: ScheduledTask) {
    this.editingTaskId.set(task.id);
    this.editingTaskValue.set(task.args[1] || ''); // args[1] is the message_or_prompt
  }

  cancelEditing() {
    this.editingTaskId.set(null);
    this.editingTaskValue.set('');
  }

  saveTaskEdit(taskId: string) {
    const newVal = this.editingTaskValue();
    if (!newVal.trim()) return;
    
    this.api.updateTask(taskId, newVal).subscribe({
      next: () => {
        this.cancelEditing();
        this.loadTasks();
      }
    });
  }
  runTask(taskId: string) {
    this.runningTaskId.set(taskId);
    this.api.runTask(taskId).subscribe({
      next: () => {
        setTimeout(() => this.runningTaskId.set(null), 3000);
      },
      error: () => this.runningTaskId.set(null)
    });
  }

  async pauseTask(taskId: string) {
    const isConfirmed = await this.confirmService.confirm('¿Pausar esta tarea?');
    if (isConfirmed) {
      this.api.pauseTask(taskId).subscribe({
        next: () => {
          this.toast.show('Tarea pausada', 'success', '', 5000, 'bottom-right');
          this.loadTasks();
        },
        error: (err) => {
          console.error('Error pausing task:', err);
          this.toast.show('Error al pausar la tarea. ' + (err.error?.detail || ''), 'danger', '', 5000, 'bottom-right');
        }
      });
    }
  }

  async resumeTask(taskId: string) {
    const isConfirmed = await this.confirmService.confirm('¿Reanudar esta tarea?');
    if (isConfirmed) {
      this.api.resumeTask(taskId).subscribe({
        next: () => {
          this.toast.show('Tarea reanudada', 'success', '', 5000, 'bottom-right');
          this.loadTasks();
        },
        error: (err) => {
          console.error('Error resuming task:', err);
          this.toast.show('Error al reanudar la tarea. ' + (err.error?.detail || ''), 'danger', '', 5000, 'bottom-right');
        }
      });
    }
  }

  toggleLogs(taskId: string) {
    if (this.expandedLogTaskId() === taskId) {
      this.expandedLogTaskId.set(null);
      this.taskLogs.set([]);
      this.clearLogsInterval();
      return;
    }
    
    this.expandedLogTaskId.set(taskId);
    this.logsLoading.set(true);
    this.fetchLogs(taskId);
    
    // Configurar polling cada 5 segundos si el panel está abierto
    this.clearLogsInterval();
    this.logsInterval = setInterval(() => {
      if (this.expandedLogTaskId() === taskId) {
        this.fetchLogs(taskId, false);
      }
    }, 5000);
  }

  private fetchLogs(taskId: string, showLoading: boolean = true) {
    if (showLoading) this.logsLoading.set(true);
    
    this.api.getTaskLogs(taskId).subscribe({
      next: (logs) => {
        this.taskLogs.set(logs);
        if (showLoading) this.logsLoading.set(false);
        
        // Si no hay logs "running", podríamos detener el polling en el futuro,
        // pero por ahora lo dejamos para capturar nuevas ejecuciones manuales.
      },
      error: () => {
        if (showLoading) {
          this.taskLogs.set([]);
          this.logsLoading.set(false);
        }
      }
    });
  }

  addTask() {
    if (!this.newTask.message_or_prompt || !this.newTask.value) return;

    this.api.createTask(this.newTask).subscribe({
      next: () => {
        this.loadTasks();
        this.closeModal();
      }
    });
  }

  openModal() {
    this.showAddModal.set(true);
  }

  closeModal() {
    this.showAddModal.set(false);
    this.newTask = {
      message_or_prompt: '',
      type: 'date',
      value: '',
      is_agent_action: false
    };
  }
}
