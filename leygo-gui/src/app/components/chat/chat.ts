import { Component, inject, signal, ElementRef, ViewChild, AfterViewInit, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../api.service';
import { ChatService } from '../../services/chat.service';
import { MarkdownPipe } from '../../pipes/markdown.pipe';
import { FriendlyDatePipe } from '../../pipes/friendly-date.pipe';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule, MarkdownPipe, FriendlyDatePipe],
  templateUrl: './chat.html',
  styleUrl: './chat.css'
})
export class ChatComponent implements AfterViewInit, OnDestroy, OnInit {
  private api         = inject(ApiService);
  private chatService = inject(ChatService);

  // ── Read from persistent service signals (survive navigation) ───────
  messages       = this.chatService.messages;
  isTyping       = this.chatService.isTyping;
  statusHistory  = this.chatService.statusHistory;
  streamingText  = this.chatService.streamingText;

  // ── Local component state ────────────────────────────────────────────
  userInput    = signal('');
  selectedFile = signal<{name: string, path: string} | null>(null);
  supervisorModel = signal('gemini');
  userName = 'Admin';

  @ViewChild('messageInput')    messageInput!: ElementRef<HTMLTextAreaElement>;
  @ViewChild('scrollContainer') private scrollContainer!: ElementRef;
  private observer?: MutationObserver;

  constructor() {
    const user = localStorage.getItem('leygo_user');
    if (user) this.userName = user;
  }

  ngOnInit() {
    this.api.getConfig().subscribe({
      next: (config: any) => {
        const model = config['MODEL_SUPERVISOR'] || config['MODEL'] || 'gemini-2.5-flash';
        this.supervisorModel.set(model.replace('models/', ''));
      },
      error: () => {}
    });
  }

  ngAfterViewInit() {
    this.observer = new MutationObserver(() => this.scrollToBottom());
    if (this.scrollContainer?.nativeElement) {
      this.observer.observe(this.scrollContainer.nativeElement, {
        childList: true, subtree: true, characterData: true
      });
      setTimeout(() => this.scrollToBottom(), 100);
    }
  }

  ngOnDestroy() {
    // Solo desconectamos el observer de scroll — el stream sigue en el servicio
    this.observer?.disconnect();
  }

  private get backendUrl(): string {
    return `${window.location.protocol}//${window.location.hostname}:8443`;
  }

  // ── Actions delegated to ChatService ────────────────────────────────

  stopMessage() {
    this.chatService.stopStream();
  }

  async sendMessage() {
    let text = this.userInput().trim();
    const file = this.selectedFile();

    if (!text && file) text = 'Analiza este archivo por favor.';
    if (!text && !file) return;

    const finalPrompt = file
      ? `[Archivo adjunto: ${file.path}]\n\n${text}`
      : text;

    // Agregar mensaje del usuario al historial
    this.chatService.addMessage({
      text: file ? `📎 **${file.name}**\n\n${text}` : text,
      sender: 'user',
      timestamp: new Date()
    });

    this.userInput.set('');
    this.selectedFile.set(null);

    if (this.messageInput) {
      this.messageInput.nativeElement.style.height = 'auto';
    }

    // El stream vive en el servicio → sobrevive la navegación
    this.chatService.sendMessage(finalPrompt, this.backendUrl);
  }

  // ── File handling ────────────────────────────────────────────────────

  onFileSelected(event: any) {
    const file: File = event.target.files[0];
    if (file) {
      this.api.uploadFile(file).subscribe({
        next: (res) => this.selectedFile.set({ name: res.filename, path: res.filepath }),
        error: () => {}
      });
    }
    event.target.value = '';
  }

  removeFile() { this.selectedFile.set(null); }

  clearChat() { this.chatService.clearChat(); }

  // ── Input UX ─────────────────────────────────────────────────────────

  onInput(event: Event) {
    this.adjustHeight(event.target as HTMLTextAreaElement);
  }

  onKeyDown(event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.sendMessage();
    }
  }

  private adjustHeight(target: HTMLTextAreaElement) {
    target.style.height = 'auto';
    const maxHeight = 12 * 24;
    const newHeight = Math.min(target.scrollHeight, maxHeight);
    target.style.height = `${newHeight}px`;
    target.style.overflowY = target.scrollHeight > maxHeight ? 'auto' : 'hidden';
  }

  private scrollToBottom(): void {
    try {
      this.scrollContainer.nativeElement.scrollTop =
        this.scrollContainer.nativeElement.scrollHeight;
    } catch { }
  }
}
