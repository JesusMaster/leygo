import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Agent {
  name: string;
  description: string;
  model: string;
  tools: { name: string; description: string }[];
}

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  private http = inject(HttpClient);
  private baseUrl = 'http://localhost:8000/api';

  getAgents(): Observable<Agent[]> {
    return this.http.get<Agent[]>(`${this.baseUrl}/agents`);
  }

  getConfig(): Observable<any> {
    return this.http.get(`${this.baseUrl}/config`);
  }

  updateConfig(key: string, value: string): Observable<any> {
    return this.http.post(`${this.baseUrl}/config`, { key, value });
  }

  sendMessage(message: string, threadId: string = 'gui_session'): Observable<{ response: string }> {
    return this.http.post<{ response: string }>(`${this.baseUrl}/chat`, { message, thread_id: threadId });
  }

  getAuthStatus(): Observable<any> {
    return this.http.get(`${this.baseUrl}/auth/google/status`);
  }
}
