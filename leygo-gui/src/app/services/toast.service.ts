import { Injectable } from '@angular/core';
import { Observable, Subject } from 'rxjs';

export type ToastPosition = 'top-right' | 'top-left' | 'bottom-right' | 'bottom-left' | 'top-center' | 'bottom-center';

export interface ToastMessage {
  type: 'success' | 'info' | 'warning' | 'danger';
  title?: string;
  message: string;
  delay?: number;
  position?: ToastPosition;
}

@Injectable({
  providedIn: 'root'
})
export class ToastService {
  private readonly toastSubject = new Subject<ToastMessage>();
  public toastState: Observable<ToastMessage> = this.toastSubject.asObservable();

  show(message: string, type: 'success' | 'info' | 'warning' | 'danger' = 'info', title?: string, delay: number = 5000, position: ToastPosition = 'top-right') {
    this.toastSubject.next({ type, title, message, delay, position });
  }
}
