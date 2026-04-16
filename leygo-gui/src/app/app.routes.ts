import { Routes } from '@angular/router';
import { ChatComponent } from './components/chat/chat';
import { AgentsComponent } from './components/agents/agents';
import { AgentEditorComponent } from './components/agent-editor/agent-editor';
import { ConfigComponent } from './components/config/config';
import { TasksComponent } from './components/tasks/tasks';
import { UsageComponent } from './components/usage/usage';
import { SetupComponent } from './components/setup/setup';
import { LoginComponent } from './components/login/login';
import { McpSettingsComponent } from './components/mcp-settings/mcp-settings';
import { WebhooksComponent } from './components/webhooks/webhooks.component';
import { setupGuard } from './guards/setup.guard';
import { authGuard } from './guards/auth.guard';

export const routes: Routes = [
  { path: 'login', component: LoginComponent },
  { path: 'setup', component: SetupComponent },
  { path: '', redirectTo: 'chat', pathMatch: 'full' },
  { path: 'chat', component: ChatComponent, canActivate: [setupGuard, authGuard] },
  { path: 'agents', component: AgentsComponent, canActivate: [setupGuard, authGuard] },
  { path: 'editor/:agentName', component: AgentEditorComponent, canActivate: [setupGuard, authGuard] },
  { path: 'tasks', component: TasksComponent, canActivate: [setupGuard, authGuard] },
  { path: 'webhooks', component: WebhooksComponent, canActivate: [setupGuard, authGuard] },
  { path: 'config', component: ConfigComponent, canActivate: [setupGuard, authGuard] },
  { path: 'mcp-settings', component: McpSettingsComponent, canActivate: [setupGuard, authGuard] },
  { path: 'usage', component: UsageComponent, canActivate: [setupGuard, authGuard] }
];
