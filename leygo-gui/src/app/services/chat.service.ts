import { Injectable, signal, effect } from '@angular/core';

export interface Message {
  text: string;
  sender: 'user' | 'bot';
  timestamp: Date;
  tokens?: number;
  cost?: number;
  model?: string;
  requiresApproval?: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class ChatService {
  private readonly STORAGE_KEY = 'leygo_chat_messages';
  private readonly THREAD_KEY  = 'leygo_chat_thread';

  // ── Persistent state ────────────────────────────────────────────────
  messages  = signal<Message[]>(this.loadMessages());
  threadId  = signal<string>(this.loadThreadId());

  // ── Streaming state (survives component navigation) ──────────────────
  isTyping       = signal(false);
  statusHistory  = signal<string[]>([]);
  streamingText  = signal<string>('');

  private abortController: AbortController | null = null;

  constructor() {
    effect(() => {
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(this.messages()));
    });
    effect(() => {
      localStorage.setItem(this.THREAD_KEY, this.threadId());
    });
  }

  // ── Public API ───────────────────────────────────────────────────────

  addMessage(message: Message) {
    this.messages.update(msgs => [...msgs, message]);
  }

  clearChat() {
    this.messages.set([
      { text: '¡Hola! Soy Leygo. ¿En qué puedo ayudarte hoy?', sender: 'bot', timestamp: new Date() }
    ]);
    this.threadId.set(`gui_session_${Date.now()}`);
  }

  stopStream() {
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
    this.statusHistory.update(h => [...h, '🔴 *Ejecución abortada por el usuario*']);
    setTimeout(() => {
      const remaining = this.streamingText();
      this.addMessage({
        text: remaining || '🔴 Ejecución abortada',
        sender: 'bot',
        timestamp: new Date()
      });
      this.streamingText.set('');
      this.statusHistory.set([]);
      this.isTyping.set(false);
    }, 500);
  }

  async sendMessage(prompt: string, backendUrl: string) {
    if (this.isTyping()) return; // ya hay un stream activo

    this.isTyping.set(true);
    this.statusHistory.set([]);
    this.streamingText.set('');

    this.abortController?.abort();
    this.abortController = new AbortController();

    try {
      const response = await fetch(`${backendUrl}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: prompt, thread_id: this.threadId() }),
        signal: this.abortController.signal
      });

      if (!response.ok || !response.body) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader  = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer    = '';
      let finalUsage: any;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;

          let event: any;
          try { event = JSON.parse(raw); } catch { continue; }

          if (event.type === 'status') {
            this.statusHistory.update(h => [...h.slice(-4), event.content]);

          } else if (event.type === 'token') {
            this.streamingText.update(t => t + event.content);

          } else if (event.type === 'done') {
            finalUsage = event.usage;
            const finalText = event.content || this.streamingText();
            this.addMessage({
              text: finalText,
              sender: 'bot',
              timestamp: new Date(),
              tokens: finalUsage
                ? (finalUsage.input_tokens ?? 0) + (finalUsage.output_tokens ?? 0)
                : undefined,
              cost:  finalUsage?.cost_usd,
              model: finalUsage?.model
            });
            this.streamingText.set('');
            this.statusHistory.set([]);
            this.isTyping.set(false);

          } else if (event.type === 'error') {
            this.addMessage({
              text: event.content || 'Error desconocido',
              sender: 'bot',
              timestamp: new Date()
            });
            this.streamingText.set('');
            this.statusHistory.set([]);
            this.isTyping.set(false);

          } else if (event.type === 'interrupt') {
            const previousText = this.streamingText();
            this.addMessage({
              text: (previousText ? previousText + '\n\n' : '') + 
                    `⚠️ **APROBACIÓN DE SEGURIDAD REQUERIDA**\nEl agente necesita tu autorización para proceder con la siguiente acción:\n\n_${event.content}_`,
              sender: 'bot',
              timestamp: new Date(),
              requiresApproval: true
            });
            this.streamingText.set('');
            this.statusHistory.set([]);
            this.isTyping.set(false);
          }
        }
      }

      // Stream terminó sin evento "done"
      if (this.isTyping()) {
        const remaining = this.streamingText();
        if (remaining) {
          this.addMessage({ text: remaining, sender: 'bot', timestamp: new Date() });
        }
        this.streamingText.set('');
        this.statusHistory.set([]);
        this.isTyping.set(false);
      }

    } catch (err: any) {
      if (err?.name === 'AbortError') return;
      this.addMessage({
        text: 'Error al conectar con Leygo. Revisa el backend.',
        sender: 'bot',
        timestamp: new Date()
      });
      this.streamingText.set('');
      this.statusHistory.set([]);
      this.isTyping.set(false);
    }
  }

  // ── Private helpers ──────────────────────────────────────────────────

  private loadThreadId(): string {
    const stored = localStorage.getItem(this.THREAD_KEY);
    return stored ? stored : `gui_session_${Date.now()}`;
  }

  private loadMessages(): Message[] {
    const stored = localStorage.getItem(this.STORAGE_KEY);
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        return parsed.map((m: any) => ({ ...m, timestamp: new Date(m.timestamp) }));
      } catch (e) {
        console.error('Error parsing chat messages from storage', e);
      }
    }
    return [
      { text: '¡Hola! Soy Leygo. ¿En qué puedo ayudarte hoy?', sender: 'bot', timestamp: new Date() }
    ];
  }
}
