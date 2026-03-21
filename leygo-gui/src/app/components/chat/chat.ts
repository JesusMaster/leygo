import { Component, inject, signal, ElementRef, ViewChild, AfterViewInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../api.service';
import { ChatService, Message } from '../../services/chat.service';
import { MarkdownPipe } from '../../pipes/markdown.pipe';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule, MarkdownPipe],
  templateUrl: './chat.html',
  styleUrl: './chat.css'
})
export class ChatComponent implements AfterViewInit, OnDestroy {
  private api = inject(ApiService);
  private chatService = inject(ChatService);
  
  // Enlazamos directamente el estado local con el global proporcionado por el servicio
  messages = this.chatService.messages;
  
  userInput = signal('');
  isTyping = signal(false);
  selectedFile = signal<{name: string, path: string} | null>(null);
  
  userName = 'Admin';

  constructor() {
    const user = localStorage.getItem('leygo_user');
    if (user) {
      this.userName = user;
    }
  }

  @ViewChild('scrollContainer') private scrollContainer!: ElementRef;
  private observer?: MutationObserver;

  ngAfterViewInit() {
    this.observer = new MutationObserver(() => {
      this.scrollToBottom();
    });
    
    if (this.scrollContainer && this.scrollContainer.nativeElement) {
      this.observer.observe(this.scrollContainer.nativeElement, {
        childList: true,
        subtree: true,
        characterData: true
      });
      // Set initial scroll
      setTimeout(() => this.scrollToBottom(), 100);
    }
  }

  ngOnDestroy() {
    if (this.observer) {
      this.observer.disconnect();
    }
  }

  async sendMessage() {
    let text = this.userInput().trim();
    const file = this.selectedFile();
    
    // Si hay archivo pero no hay texto, dar un texto por defecto
    if (!text && file) {
      text = "Analiza este archivo por favor.";
    }
    
    if (!text && !file) return;

    // Si hay un archivo adjunto, agregar la nota visible para el LLM
    const finalPrompt = file 
      ? `[Archivo adjunto: ${file.path}]\n\n${text}` 
      : text;

    // Agregar mensaje visual sin el path feo para mejor UI al usuario
    this.chatService.addMessage({
      text: file ? `📎 **${file.name}**\n\n${text}` : text,
      sender: 'user',
      timestamp: new Date()
    });

    this.userInput.set('');
    this.selectedFile.set(null);
    this.isTyping.set(true);

    // Llamada a la API con el texto y la ruta del archivo ya incrustados
    this.api.sendMessage(finalPrompt).subscribe({
      next: (res) => {
        this.chatService.addMessage({
          text: res.response,
          sender: 'bot',
          timestamp: new Date(),
          tokens: res.usage ? res.usage.input_tokens + res.usage.output_tokens : undefined,
          cost: res.usage ? res.usage.cost_usd : undefined,
          model: res.usage ? res.usage.model : undefined
        });
        this.isTyping.set(false);
      },
      error: (err) => {
        this.chatService.addMessage({
          text: 'Error al conectar con Leygo. Revisa el backend al puerto 8000.',
          sender: 'bot',
          timestamp: new Date()
        });
        this.isTyping.set(false);
      }
    });
  }

  // File Upload Handlers
  onFileSelected(event: any) {
    const file: File = event.target.files[0];
    if (file) {
      this.isTyping.set(true);
      this.api.uploadFile(file).subscribe({
        next: (res) => {
          this.selectedFile.set({ name: res.filename, path: res.filepath });
          this.isTyping.set(false);
        },
        error: (err) => {
          console.error("Error subiendo archivo", err);
          this.isTyping.set(false);
        }
      });
    }
    // Limpiar input para permitir seleccionar el mismo archivo de nuevo
    event.target.value = '';
  }

  removeFile() {
    this.selectedFile.set(null);
  }

  // Opcionalmente podemos añadir funcionalidad para limpiar
  clearChat() {
    this.chatService.clearChat();
  }

  private scrollToBottom(): void {
    try {
      this.scrollContainer.nativeElement.scrollTop = this.scrollContainer.nativeElement.scrollHeight;
    } catch(err) { }
  }
}
