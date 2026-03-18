import { Routes } from '@angular/router';
import { ChatComponent } from './components/chat/chat';
import { AgentsComponent } from './components/agents/agents';
import { ConfigComponent } from './components/config/config';
import { TasksComponent } from './components/tasks/tasks';
import { UsageComponent } from './components/usage/usage';

export const routes: Routes = [
  { path: '', redirectTo: 'chat', pathMatch: 'full' },
  { path: 'chat', component: ChatComponent },
  { path: 'agents', component: AgentsComponent },
  { path: 'tasks', component: TasksComponent },
  { path: 'config', component: ConfigComponent },
  { path: 'usage', component: UsageComponent }
];
