import { Component, inject, signal, ElementRef, ViewChild, AfterViewChecked } from '@angular/core';
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
export class ChatComponent implements AfterViewChecked {
  private api = inject(ApiService);
  private chatService = inject(ChatService);
  
  // Enlazamos directamente el estado local con el global proporcionado por el servicio
  messages = this.chatService.messages;
  
  userInput = signal('');
  isTyping = signal(false);

  @ViewChild('scrollContainer') private scrollContainer!: ElementRef;

  ngAfterViewChecked() {
    this.scrollToBottom();
  }

  async sendMessage() {
    const text = this.userInput().trim();
    if (!text) return;

    // Agregar mensaje del usuario al store global
    this.chatService.addMessage({
      text,
      sender: 'user',
      timestamp: new Date()
    });

    this.userInput.set('');
    this.isTyping.set(true);

    // Llamada a la API
    this.api.sendMessage(text).subscribe({
      next: (res) => {
        this.chatService.addMessage({
          text: res.response,
          sender: 'bot',
          timestamp: new Date()
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
