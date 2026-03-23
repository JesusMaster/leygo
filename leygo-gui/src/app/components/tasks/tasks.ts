import { Component, inject, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService, ScheduledTask } from '../../api.service';

@Component({
  selector: 'app-tasks',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './tasks.html',
  styleUrl: './tasks.css'
})
export class TasksComponent implements OnInit {
  private api = inject(ApiService);
  tasks = signal<ScheduledTask[]>([]);
  loading = signal(true);

  // Form para nuevo recordatorio
  showAddModal = signal(false);
  newTask = {
    message_or_prompt: '',
    type: 'date',
    value: '',
    is_agent_action: false
  };

  ngOnInit() {
    this.loadTasks();
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

  deleteTask(id: string) {
    if (confirm('¿Estás seguro de que quieres eliminar esta tarea?')) {
      this.api.deleteTask(id).subscribe({
        next: () => this.loadTasks()
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
