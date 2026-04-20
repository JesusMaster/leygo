import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ConfirmService, ConfirmState } from '@services/confirm.service';

@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './confirm-dialog.html',
  styleUrls: ['./confirm-dialog.scss']
})
export class ConfirmDialogComponent implements OnInit {
  showModal = false;
  title = '';
  message = '';
  private currentResolver?: (value: boolean) => void;

  private readonly confirmService = inject(ConfirmService);

  ngOnInit() {
    this.confirmService.confirmState$.subscribe((state: ConfirmState) => {
      this.showModal = state.show;
      this.title = state.title;
      this.message = state.message;
      this.currentResolver = state.resolve;
    });
  }

  onClose() {
    this.confirmService.close(false, this.currentResolver);
  }

  onConfirm() {
    this.confirmService.close(true, this.currentResolver);
  }
}
