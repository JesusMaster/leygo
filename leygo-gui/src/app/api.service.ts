import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Agent {
  name: string;
  description: string;
  model: string;
  tools: { name: string; description: string }[];
}

export interface ScheduledTask {
  id: string;
  name: string;
  func_name?: string;
  args: any[];
  type: 'date' | 'interval' | 'cron' | 'cron_expr';
  interval_minutes?: number;
  cron_hour?: string;
  cron_minute?: string;
  cron_day?: string;
  cron_month?: string;
  cron_day_of_week?: string;
  next_run_time_iso?: string;
}

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  private http = inject(HttpClient);
  private host = window.location.hostname;
  private baseUrl = `${window.location.protocol}//${this.host}:8443/api`;

  getAgents(): Observable<Agent[]> {
    return this.http.get<Agent[]>(`${this.baseUrl}/agents`);
  }

  deleteAgent(name: string): Observable<any> {
    return this.http.delete(`${this.baseUrl}/agents/${name}`);
  }

  getAgentFiles(name: string): Observable<{python_code: string, episodic_code: string, procedural_code: string, prefs_code: string, env_code: string}> {
    return this.http.get<{python_code: string, episodic_code: string, procedural_code: string, prefs_code: string, env_code: string}>(`${this.baseUrl}/agents/${name}`);
  }

  updateAgentFiles(name: string, data: {python_code?: string, episodic_code?: string, procedural_code?: string, prefs_code?: string, env_code?: string}): Observable<any> {
    return this.http.put(`${this.baseUrl}/agents/${name}`, data);
  }

  getConfig(): Observable<any> {
    return this.http.get(`${this.baseUrl}/config`);
  }

  updateConfig(key: string, value: string): Observable<any> {
    return this.http.post(`${this.baseUrl}/config`, { key, value });
  }

  sendMessage(message: string, threadId: string = 'gui_session'): Observable<{ response: string, usage?: any }> {
    return this.http.post<{ response: string, usage?: any }>(`${this.baseUrl}/chat`, { message, thread_id: threadId });
  }

  uploadFile(file: File): Observable<{ status: string, filepath: string, filename: string }> {
    const formData = new FormData();
    formData.append('file', file);
    return this.http.post<{ status: string, filepath: string, filename: string }>(`${this.baseUrl}/upload`, formData);
  }

  getUsageHistory(): Observable<any[]> {
    return this.http.get<any[]>(`${this.baseUrl}/usage`);
  }

  getAuthStatus(): Observable<any> {
    return this.http.get(`${this.baseUrl}/auth/google/status`);
  }

  getTasks(): Observable<ScheduledTask[]> {
    return this.http.get<ScheduledTask[]>(`${this.baseUrl}/tasks`);
  }

  createTask(task: { message_or_prompt: string, type: string, value: string, is_agent_action?: boolean }): Observable<any> {
    return this.http.post(`${this.baseUrl}/tasks`, task);
  }

  deleteTask(taskId: string): Observable<any> {
    return this.http.delete(`${this.baseUrl}/tasks/${taskId}`);
  }

  updateTask(taskId: string, message_or_prompt: string): Observable<any> {
    return this.http.put(`${this.baseUrl}/tasks/${taskId}`, { message_or_prompt });
  }

  exchangeGoogleCode(code: string): Observable<any> {
    return this.http.post(`${this.baseUrl}/auth/google/exchange`, { code });
  }

  revokeGoogleWorkspace(): Observable<any> {
    return this.http.delete(`${this.baseUrl}/auth/google/revoke`);
  }

  reloadTelegram(): Observable<any> {
    return this.http.post(`${this.baseUrl}/config/telegram/reload`, {});
  }

  getTelegramStatus(): Observable<any> {
    return this.http.get(`${this.baseUrl}/config/telegram/status`);
  }
}
