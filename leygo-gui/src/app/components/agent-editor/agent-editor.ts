import { Component, inject, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService, AgentFileNode } from '../../api.service';
import { ActivatedRoute, Router } from '@angular/router';
import { MonacoEditorModule } from 'ngx-monaco-editor-v2';

@Component({
  selector: 'app-agent-editor',
  standalone: true,
  imports: [CommonModule, FormsModule, MonacoEditorModule],
  templateUrl: './agent-editor.html',
  styleUrl: './agent-editor.css'
})
export class AgentEditorComponent implements OnInit {
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  agentName = signal<string>('');
  files = signal<AgentFileNode[]>([]);
  deletedFiles = signal<string[]>([]);
  
  loading = signal(true);
  saving = signal(false);

  selectedFile = signal<AgentFileNode | null>(null);
  editorOptions = signal({theme: 'vs-dark', language: 'python', automaticLayout: true});

  ngOnInit() {
    this.route.paramMap.subscribe(params => {
      const name = params.get('agentName');
      if (name) {
        this.agentName.set(name);
        this.loadTree();
      }
    });
  }

  loadTree() {
    this.loading.set(true);
    this.api.getAgentTree(this.agentName()).subscribe({
      next: (data) => {
        this.files.set(data);
        this.deletedFiles.set([]);
        if (data.length > 0) {
          // pre-select main file if possible
          const mainFile = data.find(f => f.path.endsWith('_agent.py')) || data[0];
          this.selectFile(mainFile);
        }
        this.loading.set(false);
      },
      error: () => this.loading.set(false)
    });
  }

  selectFile(file: AgentFileNode) {
    this.selectedFile.set(file);
    let lang = 'plaintext';
    if (file.path.endsWith('.py')) lang = 'python';
    else if (file.path.endsWith('.md')) lang = 'markdown';
    else if (file.path.endsWith('.json')) lang = 'json';
    else if (file.path.endsWith('.env')) lang = 'ini';
    
    this.editorOptions.set({
      theme: 'vs-dark',
      language: lang,
      automaticLayout: true
    });
  }

  createNewFile() {
    const filename = prompt('Ingresa la ruta relativa del nuevo archivo (ej: memoria/nuevo_conocimiento.md):');
    if (!filename) return;
    
    // Check if exists
    if (this.files().find(f => f.path === filename)) {
      alert('Ese archivo ya existe.');
      return;
    }

    const newFile: AgentFileNode = { path: filename, content: '' };
    this.files.update(f => [...f, newFile]);
    this.selectFile(newFile);
  }

  deleteFile(file: AgentFileNode) {
    if (file.path.endsWith('_agent.py')) {
      alert('No puedes eliminar el archivo controlador principal del agente.');
      return;
    }
    if (confirm(`¿Eliminar ${file.path}?`)) {
      this.files.update(f => f.filter(x => x.path !== file.path));
      this.deletedFiles.update(d => [...d, file.path]);
      if (this.selectedFile()?.path === file.path) {
        this.selectedFile.set(this.files()[0] || null);
      }
    }
  }

  saveAll() {
    this.saving.set(true);
    this.api.updateAgentTree(this.agentName(), {
      files: this.files(),
      deleted_paths: this.deletedFiles()
    }).subscribe({
      next: () => {
        this.saving.set(false);
        alert('Archivos guardados con éxito.');
        this.loadTree();
      },
      error: (e) => {
        this.saving.set(false);
        alert('Error guardando archivos: ' + e.message);
      }
    });
  }

  goBack() {
    this.router.navigate(['/agents']);
  }
}
