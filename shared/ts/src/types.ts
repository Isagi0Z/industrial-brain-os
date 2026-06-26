export interface BoundingBox {
  x: number;
  y: number;
  w: number;
  h: number;
  page: number;
}

export interface ServiceStatus {
  name: string;
  status: 'healthy' | 'unhealthy' | 'degraded';
  version: string;
  details?: Record<string, any>;
}

export interface ErrorResponse {
  code: string;
  message: string;
  details?: Record<string, any>;
  correlation_id?: string;
}

export interface UserPrincipal {
  userId: string;
  username: string;
  roles: string[];
  workspaces: string[];
}

export interface DashboardStats {
  documentCount: number;
  entityCount: number;
  relationCount: number;
  activeSensors: number;
  recentIncidents: number;
}
