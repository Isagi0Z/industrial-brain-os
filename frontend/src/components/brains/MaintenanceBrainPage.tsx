import React from 'react';
import { Wrench, ClipboardList, AlertTriangle } from 'lucide-react';
import { BrainChat, BrainChatResponse } from './BrainChat';
import { Card } from '../ui/card';
import { Badge } from '../ui/badge';

interface WorkOrder {
  wo_id: string;
  asset_tag: string;
  description: string;
  status: string;
  priority: string;
  scheduled_date: string | null;
  completed_date: string | null;
}

interface FailureRecord {
  failure_code: string;
  description: string;
  severity: string | null;
  typical_cause: string | null;
}

const priorityVariant = (p: string): 'destructive' | 'warning' | 'secondary' => {
  const v = p.toLowerCase();
  if (v.includes('critical') || v.includes('high')) return 'destructive';
  if (v.includes('medium')) return 'warning';
  return 'secondary';
};

const MaintenanceContext: React.FC<{ last: BrainChatResponse | null }> = ({
  last,
}) => {
  if (!last) return null;
  const assetTag = last.asset_tag as string | null;
  const workOrders = (last.work_orders as WorkOrder[]) || [];
  const failures = (last.failure_history as FailureRecord[]) || [];

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="mb-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          Asset
        </div>
        {assetTag ? (
          <Badge variant="default" className="font-mono">
            {assetTag}
          </Badge>
        ) : (
          <p className="text-xs text-muted-foreground">
            No asset tag detected in the query.
          </p>
        )}
      </Card>

      <Card className="p-4">
        <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          <ClipboardList className="h-3.5 w-3.5 text-primary" /> Open Work Orders
          {workOrders.length > 0 && (
            <span className="ml-auto font-normal normal-case text-foreground">
              {workOrders.length}
            </span>
          )}
        </div>
        {workOrders.length === 0 ? (
          <p className="text-xs text-muted-foreground">No open work orders.</p>
        ) : (
          <ul className="space-y-2">
            {workOrders.map((wo) => (
              <li
                key={wo.wo_id}
                className="rounded-lg border border-border bg-secondary/40 p-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs text-primary">{wo.wo_id}</span>
                  <Badge variant={priorityVariant(wo.priority)}>{wo.priority}</Badge>
                </div>
                <p className="mt-1 text-sm text-foreground/90">{wo.description}</p>
                <div className="mt-1.5 flex items-center gap-2 text-[11px] text-muted-foreground">
                  <span className="capitalize">{wo.status}</span>
                  {wo.scheduled_date && <span>· due {wo.scheduled_date.slice(0, 10)}</span>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="p-4">
        <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          <AlertTriangle className="h-3.5 w-3.5 text-primary" /> Failure History
          {failures.length > 0 && (
            <span className="ml-auto font-normal normal-case text-foreground">
              {failures.length}
            </span>
          )}
        </div>
        {failures.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No failure records for this asset.
          </p>
        ) : (
          <ul className="space-y-2">
            {failures.map((f) => (
              <li
                key={f.failure_code}
                className="rounded-lg border border-border bg-secondary/40 p-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs text-primary">
                    {f.failure_code}
                  </span>
                  {f.severity && <Badge variant="warning">{f.severity}</Badge>}
                </div>
                <p className="mt-1 text-sm text-foreground/90">{f.description}</p>
                {f.typical_cause && (
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    Typical cause: {f.typical_cause}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
};

export const MaintenanceBrainPage: React.FC = () => (
  <BrainChat
    title="Maintenance Brain"
    icon={Wrench}
    description="Operational maintenance supervisor connected to the CMMS. Diagnoses failures, surfaces open work orders, and queries equipment specs."
    endpoint="/api/v1/brain/maintenance/chat"
    suggestions={[
      'What open work orders exist for pump P-102A?',
      'What are the common failure modes for centrifugal pumps?',
      'How do I isolate pump P-102A for maintenance?',
    ]}
    renderContext={(last) => <MaintenanceContext last={last} />}
  />
);
