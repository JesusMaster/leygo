import { Routes } from '@angular/router';
import { ChatComponent } from './components/chat/chat';
import { AgentsComponent } from './components/agents/agents';
import { ConfigComponent } from './components/config/config';

export const routes: Routes = [
  { path: '', redirectTo: 'chat', pathMatch: 'full' },
  { path: 'chat', component: ChatComponent },
  { path: 'agents', component: AgentsComponent },
  { path: 'config', component: ConfigComponent }
];
