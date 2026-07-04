import React, { useState } from 'react';
import { LibraryBig, Upload } from 'lucide-react';
import { DocumentUpload } from './DocumentUpload';
import { DocumentList } from './DocumentList';
import { FadeIn } from '../ui/motion';
import { cn } from '../../lib/utils';

const TABS = [
  { key: 'list', label: 'Library', icon: LibraryBig },
  { key: 'upload', label: 'Upload', icon: Upload },
] as const;

export const DocumentHub: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'list' | 'upload'>('list');

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <FadeIn>
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Document Hub</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Ingest, manage, and inspect your industrial document library.
            </p>
          </div>
          <div className="inline-flex items-center gap-1 rounded-lg border border-border bg-card/60 p-1">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={cn(
                  'inline-flex items-center gap-2 rounded-md px-3.5 py-1.5 text-sm font-medium transition-all',
                  activeTab === tab.key
                    ? 'bg-primary text-primary-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                <tab.icon className="h-4 w-4" />
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </FadeIn>

      <FadeIn delay={0.05} key={activeTab}>
        {activeTab === 'list' ? <DocumentList /> : <DocumentUpload />}
      </FadeIn>
    </div>
  );
};
