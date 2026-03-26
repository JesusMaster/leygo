import { Component, inject, signal, ElementRef, ViewChild, AfterViewInit, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../api.service';
import { ChatService } from '../../services/chat.service';
import { MarkdownPipe } from '../../pipes/markdown.pipe';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule, MarkdownPipe],
  templateUrl: './chat.html',
  styleUrl: './chat.css'
})
export class ChatComponent implements AfterViewInit, OnDestroy, OnInit {
  private api = inject(ApiService);
  private chatService = inject(ChatService);

  messages = this.chatService.messages;

  userInput = signal('');
  isTyping = signal(false);
  selectedFile = signal<{name: string, path: string} | null>(null);

  // Estado en tiempo real
  statusHistory = signal<string[]>([]);
  // Texto de respuesta que se va construyendo token a token
  streamingText = signal<string>('');

  private abortController: AbortController | null = null;
  @ViewChild('messageInput') messageInput!: ElementRef<HTMLTextAreaElement>;

  supervisorModel = signal('gemini'); // Se rellena en ngOnInit

  userName = 'Admin';

  constructor() {
    const user = localStorage.getItem('leygo_user');
    if (user) this.userName = user;
  }

  ngOnInit() {
    this.api.getConfig().subscribe({
      next: (config: any) => {
        const model = config['MODEL_SUPERVISOR'] || config['MODEL'] || 'gemini-2.5-flash';
        // Mostrar versión corta y legible del modelo
        this.supervisorModel.set(model.replace('models/', ''));
      },
      error: () => {} // silencioso si falla
    });
  }

  @ViewChild('scrollContainer') private scrollContainer!: ElementRef;
  private observer?: MutationObserver;

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
    this.observer?.disconnect();
    this.abortController?.abort();
  }

  /** URL base del backend, auto-detectada */
  private get backendUrl(): string {
    return `${window.location.protocol}//${window.location.hostname}:8443`;
  }

  stopMessage() {
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
    this.isTyping.set(false);
    this.statusHistory.set([...this.statusHistory(), "🔴 *Ejecución abortada por el usuario*"]);
    setTimeout(() => {
      this.chatService.addMessage({
        text: this.streamingText() || "🔴 Ejecución abortada",
        sender: 'bot',
        timestamp: new Date()
      });
      this.streamingText.set('');
      this.statusHistory.set([]);
    }, 500);
  }

  async sendMessage() {
    let text = this.userInput().trim();
    const file = this.selectedFile();

    if (!text && file) text = 'Analiza este archivo por favor.';
    if (!text && !file) return;

    const finalPrompt = file
      ? `[Archivo adjunto: ${file.path}]\n\n${text}`
      : text;

    // Agregar mensaje del usuario
    this.chatService.addMessage({
      text: file ? `📎 **${file.name}**\n\n${text}` : text,
      sender: 'user',
      timestamp: new Date()
    });

    this.userInput.set('');
    this.selectedFile.set(null);
    this.isTyping.set(true);
    this.statusHistory.set([]);
    this.streamingText.set('');
    
    // Reset textarea height
    if (this.messageInput) {
      this.messageInput.nativeElement.style.height = 'auto';
    }

    // Cancelar cualquier stream anterior
    this.abortController?.abort();
    this.abortController = new AbortController();

    try {
      const response = await fetch(`${this.backendUrl}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: finalPrompt, thread_id: 'gui_session' }),
        signal: this.abortController.signal
      });

      if (!response.ok || !response.body) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let finalUsage: any = undefined;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? ''; // última línea puede estar incompleta

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;

          let event: any;
          try { event = JSON.parse(raw); } catch { continue; }

          if (event.type === 'status') {
            // Paso de estado — mostrar en la burbuja thinking
            this.statusHistory.update(h => [...h.slice(-4), event.content]);

          } else if (event.type === 'token') {
            // Token de respuesta — acumular en streamingText
            this.streamingText.update(t => t + event.content);

          } else if (event.type === 'done') {
            // Respuesta completa — agregar como mensaje del bot
            finalUsage = event.usage;
            const finalText = event.content || this.streamingText();
            this.chatService.addMessage({
              text: finalText,
              sender: 'bot',
              timestamp: new Date(),
              tokens: finalUsage
                ? (finalUsage.input_tokens ?? 0) + (finalUsage.output_tokens ?? 0)
                : undefined,
              cost: finalUsage?.cost_usd,
              model: finalUsage?.model
            });
            this.streamingText.set('');
            this.statusHistory.set([]);
            this.isTyping.set(false);

          } else if (event.type === 'error') {
            this.chatService.addMessage({
              text: event.content || 'Error desconocido',
              sender: 'bot',
              timestamp: new Date()
            });
            this.streamingText.set('');
            this.statusHistory.set([]);
            this.isTyping.set(false);
          }
        }
      }

      // Por si acaso el stream terminó sin evento "done"
      if (this.isTyping()) {
        const remaining = this.streamingText();
        if (remaining) {
          this.chatService.addMessage({
            text: remaining,
            sender: 'bot',
            timestamp: new Date()
          });
        }
        this.streamingText.set('');
        this.statusHistory.set([]);
        this.isTyping.set(false);
      }

    } catch (err: any) {
      if (err?.name === 'AbortError') return; // cancelado intencionalmente
      this.chatService.addMessage({
        text: 'Error al conectar con Leygo. Revisa el backend.',
        sender: 'bot',
        timestamp: new Date()
      });
      this.streamingText.set('');
      this.statusHistory.set([]);
      this.isTyping.set(false);
    }
  }

  onFileSelected(event: any) {
    const file: File = event.target.files[0];
    if (file) {
      this.isTyping.set(true);
      this.api.uploadFile(file).subscribe({
        next: (res) => {
          this.selectedFile.set({ name: res.filename, path: res.filepath });
          this.isTyping.set(false);
        },
        error: () => this.isTyping.set(false)
      });
    }
    event.target.value = '';
  }

  removeFile() { this.selectedFile.set(null); }

  clearChat() { this.chatService.clearChat(); }

  onInput(event: Event) {
    const target = event.target as HTMLTextAreaElement;
    this.adjustHeight(target);
  }

  onKeyDown(event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.sendMessage();
    }
  }

  private adjustHeight(target: HTMLTextAreaElement) {
    target.style.height = 'auto';
    // Max 12 lines. Line height is approx 24px (1.5 * 16px). 
    // We can also let the CSS max-height handle it, but setting it here is safer.
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
