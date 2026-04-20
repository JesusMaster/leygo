import { Component, inject, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ToastService, ToastMessage } from '@services/toast.service';

@Component({
  selector: 'app-toast',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './toast.html',
  styleUrls: ['./toast.scss']
})
export class ToastComponent implements OnInit {
  toastGroups: { [position: string]: ToastMessage[] } = {};

  private readonly toastService = inject(ToastService);
  private readonly cdr = inject(ChangeDetectorRef);

  ngOnInit() {
    this.toastService.toastState.subscribe((toast) => {
      const position = toast.position ?? 'top-right';
      if (!this.toastGroups[position]) {
        this.toastGroups[position] = [];
      }
      this.toastGroups[position].push(toast);
      this.cdr.detectChanges();
      
      setTimeout(() => {
        this.removeToast(toast);
      }, toast.delay ?? 5000);
    });
  }

  removeToast(toast: ToastMessage) {
    const position = toast.position ?? 'top-right';
    if (this.toastGroups[position]) {
      this.toastGroups[position] = this.toastGroups[position].filter(t => t !== toast);
      this.cdr.detectChanges();
    }
  }

  objectKeys(obj: object) {
    return Object.keys(obj);
  }

  getIconClass(type: string): string {
    switch (type) {
      case 'success':
        return 'fas fa-check-circle';
      case 'info':
        return 'fas fa-info-circle';
      case 'warning':
        return 'fas fa-exclamation-triangle';
      case 'danger':
        return 'fas fa-exclamation-circle';
      default:
        return 'fas fa-info-circle';
    }
  }

  getToastClass(type: string): string {
    switch (type) {
      case 'success':
        return 'bg-green-500';
      case 'info':
        return 'bg-blue-500';
      case 'warning':
        return 'bg-yellow-500';
      case 'danger':
        return 'bg-red-500';
      default:
        return 'bg-blue-500';
    }
  }
}
