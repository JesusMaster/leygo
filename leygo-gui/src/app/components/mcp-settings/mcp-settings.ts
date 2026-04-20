import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { McpService, McpServer } from '../../services/mcp.service';
import { ToastService } from '@services/toast.service';
import { ConfirmService } from '@services/confirm.service';

@Component({
  selector: 'app-mcp-settings',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './mcp-settings.html',
  styleUrls: ['./mcp-settings.css']
})
export class McpSettingsComponent implements OnInit {
  servers: McpServer[] = [];
  loading = false;
  errorMsg = '';
  successMsg = '';

  // Modal / Edición state
  showModal = false;
  isEditing = false;
  originalName = '';

  currentServer: any = this.getEmptyServer();

  constructor(
    private mcpService: McpService, 
    private cdr: ChangeDetectorRef,
    private toast: ToastService,
    private confirmService: ConfirmService
  ) {}

  ngOnInit() {
    this.loadServers();
  }

  loadServers() {
    this.loading = true;
    this.mcpService.getServers().subscribe({
      next: (data) => {
        this.servers = data;
        this.loading = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        this.errorMsg = 'Error al cargar conexiones: ' + (err.error?.detail || err.message);
        this.loading = false;
        this.cdr.detectChanges();
      }
    });
  }

  getEmptyServer() {
    return {
      name: '',
      command: 'npx',
      transport: 'stdio',
      args: ['-y'],
      envPairs: [{key: '', value: ''}] // Usamos envPairs visuales para manejar diccionarios nativamente en la GUI
    };
  }

  openNew() {
    this.isEditing = false;
    this.currentServer = this.getEmptyServer();
    this.showModal = true;
    this.errorMsg = '';
    this.successMsg = '';
  }

  openEdit(server: McpServer) {
    this.isEditing = true;
    this.originalName = server.name;
    
    // Transformar el mapeo simple de {KEY: VALUE} a iterador [{key: K, value: V}]
    const envPairs = server.env ? Object.keys(server.env).map(k => ({key: k, value: server.env[k]})) : [];
    if(envPairs.length === 0) envPairs.push({key: '', value: ''});
    
    this.currentServer = {
      name: server.name,
      command: server.command,
      transport: server.transport,
      args: [...server.args],
      envPairs: envPairs
    };
    
    this.showModal = true;
    this.errorMsg = '';
    this.successMsg = '';
  }

  closeModal() {
    this.showModal = false;
  }

  async deleteServer(name: string) {
    const isConfirmed = await this.confirmService.confirm(`¿Seguro que deseas eliminar la conexión a ${name}?`);
    if(!isConfirmed) return;
    
    this.loading = true;
    this.mcpService.deleteServer(name).subscribe({
      next: () => {
        this.successMsg = 'Conexión eliminada con éxito.';
        this.toast.show('Conexión eliminada.', 'success', '', 5000, 'bottom-right');
        this.loadServers();
      },
      error: (err) => {
        this.errorMsg = 'No se pudo eliminar: ' + (err.error?.detail || err.message);
        this.toast.show(this.errorMsg, 'danger', '', 5000, 'bottom-right');
        this.loading = false;
        this.cdr.detectChanges();
      }
    });
  }

  saveServer() {
    if(!this.currentServer.name) {
      this.errorMsg = "El nombre es obligatorio.";
      return;
    }
    
    this.errorMsg = '';
    this.loading = true;

    // Aplanar envPairs a dict
    const envDict: {[key: string]: string} = {};
    for(const ev of this.currentServer.envPairs) {
      if(ev.key.trim()) {
        envDict[ev.key.trim()] = ev.value;
      }
    }

    const payload: McpServer = {
      name: this.currentServer.name,
      command: this.currentServer.command,
      transport: this.currentServer.transport,
      args: this.currentServer.args.filter((a:string) => a.trim() !== ''),
      env: envDict
    };

    if(this.isEditing) {
      this.mcpService.updateServer(this.originalName, payload).subscribe({
         next: () => {
           this.successMsg = 'Actualizado correctamente.';
           this.closeModal();
           this.loadServers();
         },
         error: (err) => {
           this.errorMsg = err.error?.detail || err.message;
           this.loading = false;
           this.cdr.detectChanges();
         }
      });
    } else {
      this.mcpService.createServer(payload).subscribe({
         next: () => {
           this.successMsg = 'Creado correctamente.';
           this.closeModal();
           this.loadServers();
         },
         error: (err) => {
           this.errorMsg = err.error?.detail || err.message;
           this.loading = false;
           this.cdr.detectChanges();
         }
      });
    }
  }

  // Utilidades del Form dinámico
  addArg() {
    this.currentServer.args.push('');
  }
  removeArg(idx: number) {
    this.currentServer.args.splice(idx, 1);
  }
  addEnv() {
    this.currentServer.envPairs.push({key: '', value: ''});
  }
  removeEnv(idx: number) {
    this.currentServer.envPairs.splice(idx, 1);
  }
  
  trackByIndex(index: number, obj: any): any {
    return index;
  }
}
