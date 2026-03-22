import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface McpServer {
  name: string;
  command: string;
  transport: string;
  args: string[];
  env: { [key: string]: string };
}

@Injectable({
  providedIn: 'root'
})
export class McpService {
  private apiUrl = `${window.location.protocol}//${window.location.hostname}:8443/api/mcp`;

  constructor(private http: HttpClient) { }

  getServers(): Observable<McpServer[]> {
    return this.http.get<McpServer[]>(this.apiUrl);
  }

  createServer(server: McpServer): Observable<{status: string, message: string}> {
    return this.http.post<any>(this.apiUrl, server);
  }

  updateServer(originalName: string, server: McpServer): Observable<{status: string, message: string}> {
    return this.http.put<any>(`${this.apiUrl}/${originalName}`, server);
  }

  deleteServer(name: string): Observable<{status: string, message: string}> {
    return this.http.delete<any>(`${this.apiUrl}/${name}`);
  }
}
