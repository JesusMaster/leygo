import { Injectable, signal, effect } from '@angular/core';

export interface Message {
  text: string;
  sender: 'user' | 'bot';
  timestamp: Date;
}

@Injectable({
  providedIn: 'root'
})
export class ChatService {
  private readonly STORAGE_KEY = 'leygo_chat_messages';
  
  // Estado global de los mensajes usando Signals
  messages = signal<Message[]>(this.loadMessages());

  constructor() {
    // Almacenar automáticamente en localStorage cuando cambian los mensajes
    effect(() => {
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(this.messages()));
    });
  }

  // Cargar mensajes desde localStorage o usar el predeterminado
  private loadMessages(): Message[] {
    const stored = localStorage.getItem(this.STORAGE_KEY);
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        // Convertir strings de fecha a objetos Date
        return parsed.map((m: any) => ({
          ...m,
          timestamp: new Date(m.timestamp)
        }));
      } catch (e) {
        console.error('Error parsing chat messages from storage', e);
      }
    }
    return [
      { text: '¡Hola! Soy Leygo. ¿En qué puedo ayudarte hoy?', sender: 'bot', timestamp: new Date() }
    ];
  }

  addMessage(message: Message) {
    this.messages.update(msgs => [...msgs, message]);
  }

  clearChat() {
    this.messages.set([
      { text: '¡Hola! Soy Leygo. ¿En qué puedo ayudarte hoy?', sender: 'bot', timestamp: new Date() }
    ]);
  }
}
