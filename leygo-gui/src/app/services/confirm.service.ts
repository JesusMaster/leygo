import { Injectable } from '@angular/core';
import { Subject } from 'rxjs';

export interface ConfirmState {
  show: boolean;
  title: string;
  message: string;
  resolve?: (value: boolean) => void;
}

@Injectable({
  providedIn: 'root'
})
export class ConfirmService {
  private confirmSubject = new Subject<ConfirmState>();
  confirmState$ = this.confirmSubject.asObservable();

  confirm(message: string, title = 'Confirmar'): Promise<boolean> {
    return new Promise((resolve) => {
      this.confirmSubject.next({
        show: true,
        title,
        message,
        resolve
      });
    });
  }

  close(result: boolean, resolve?: (value: boolean) => void) {
    this.confirmSubject.next({
      show: false,
      title: '',
      message: ''
    });
    if (resolve) {
      resolve(result);
    }
  }
}
