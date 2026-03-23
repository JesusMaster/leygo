import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface SetupStatus {
  setup_completed: boolean;
  admin_created: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class SetupService {
  private apiUrl = `${window.location.protocol}//${window.location.hostname}:8443/api/setup`;

  constructor(private http: HttpClient) { }

  getStatus(): Observable<SetupStatus> {
    return this.http.get<SetupStatus>(`${this.apiUrl}/status`);
  }

  validateKey(key: string): Observable<{valid: boolean, message: string}> {
    return this.http.post<{valid: boolean, message: string}>(`${this.apiUrl}/validate-key`, { key });
  }

  createAdmin(key: string, username: string, password: string): Observable<{status: string, message: string}> {
    return this.http.post<any>(`${this.apiUrl}/admin`, { key, username, password });
  }

  saveConfigs(configs: {[key: string]: string}): Observable<{status: string}> {
    return this.http.post<any>(`${this.apiUrl}/config-batch`, { configs });
  }

  getGoogleAuthUrl(clientId: string, clientSecret: string, redirectUri: string): Observable<{status: string, url: string}> {
    return this.http.post<any>(`${this.apiUrl}/google-auth-url`, { client_id: clientId, client_secret: clientSecret, redirect_uri: redirectUri });
  }

  savePreferences(userName: string, preferredName: string, agentName: string, agentPersonality: string): Observable<{status: string}> {
    return this.http.post<any>(`${this.apiUrl}/preferences`, { user_name: userName, preferred_name: preferredName, agent_name: agentName, agent_personality: agentPersonality });
  }

  login(username: string, password: string): Observable<{status: string, token: string, username: string, role: string}> {
    return this.http.post<any>(`${this.apiUrl}/login`, { username, password });
  }

  googleLogin(credential: string): Observable<{status: string, token: string, username: string, role: string}> {
    return this.http.post<any>(`${this.apiUrl}/google-login`, { credential });
  }

  logout() {
    localStorage.removeItem('leygo_token');
    localStorage.removeItem('leygo_user');
  }

  isLoggedIn(): boolean {
    // Si el token existe, se considera logueado. (Para máxima estrictez se podría decodificar el JWT y ver expiración)
    return !!localStorage.getItem('leygo_token');
  }
}

