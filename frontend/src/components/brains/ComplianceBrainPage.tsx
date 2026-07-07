import React from 'react';
import { ShieldAlert, ShieldCheck } from 'lucide-react';
import { BrainChat, BrainChatResponse } from './BrainChat';
import { Card } from '../ui/card';
import { Badge } from '../ui/badge';

interface ComplianceGap {
  regulation_clause: string;
  procedure_gap: string;
  severity: string;
}

interface GapReport {
  regulation_query: string;
  procedure_query: string;
  gaps: ComplianceGap[];
  has_critical_gaps: boolean;
  generated_at: string;
}

const sevVariant = (s: string): 'destructive' | 'warning' | 'secondary' => {
  const v = s.toLowerCase();
  if (v.includes('critical') || v.includes('high')) return 'destructive';
  if (v.includes('medium') || v.includes('moderate')) return 'warning';
  return 'secondary';
};

const ComplianceContext: React.FC<{ last: BrainChatResponse | null }> = ({
  last,
}) => {
  if (!last) return null;
  const report = last.gap_report as GapReport | null;

  if (!report) {
    return (
      <Card className="p-4">
        <div className="flex items-center gap-2 text-sm text-success">
          <ShieldCheck className="h-4 w-4" /> No structured gap report generated.
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          Ask a regulation-vs-procedure question (e.g. an OSHA clause against an
          SOP) to generate a compliance gap report.
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          <ShieldAlert className="h-3.5 w-3.5 text-primary" /> Compliance Gap Report
          <Badge
            variant={report.has_critical_gaps ? 'destructive' : 'success'}
            className="ml-auto"
          >
            {report.has_critical_gaps ? 'Critical gaps' : 'Compliant'}
          </Badge>
        </div>
        <div className="space-y-1.5 text-[11px] text-muted-foreground">
          <p>
            <span className="text-foreground/80">Regulation:</span>{' '}
            {report.regulation_query}
          </p>
          <p>
            <span className="text-foreground/80">Procedure:</span>{' '}
            {report.procedure_query}
          </p>
        </div>
      </Card>

      <Card className="p-4">
        <div className="mb-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          Detected Gaps
          <span className="ml-2 font-normal normal-case text-foreground">
            {report.gaps.length}
          </span>
        </div>
        {report.gaps.length === 0 ? (
          <p className="flex items-center gap-2 text-sm text-success">
            <ShieldCheck className="h-4 w-4" /> No gaps — procedure satisfies the
            regulation.
          </p>
        ) : (
          <ul className="space-y-2">
            {report.gaps.map((g, i) => (
              <li
                key={i}
                className="rounded-lg border border-border bg-secondary/40 p-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-primary">
                    {g.regulation_clause}
                  </span>
                  <Badge variant={sevVariant(g.severity)}>{g.severity}</Badge>
                </div>
                <p className="mt-1 text-sm text-foreground/90">{g.procedure_gap}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
};

export const ComplianceBrainPage: React.FC = () => (
  <BrainChat
    title="Compliance Brain"
    icon={ShieldAlert}
    description="Automated safety manager. Checks procedures and maintenance logs against OSHA/EPA regulations and surfaces compliance gaps."
    endpoint="/api/v1/brain/compliance/chat"
    suggestions={[
      'Does our lockout-tagout SOP meet OSHA 1910.147?',
      'Are there compliance gaps in the pump maintenance procedure?',
      'What safety checks are required before valve inspection?',
    ]}
    renderContext={(last) => <ComplianceContext last={last} />}
  />
);
