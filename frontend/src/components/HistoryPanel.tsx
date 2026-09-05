import { useTranslation } from 'react-i18next';
import { useSearchHistory } from '../hooks/useSearchRun';
import type { SearchRunStatus } from '../types/api';

interface Props {
  onSelectRun: (runId: string) => void;
  activeRunId: string | null;
}

const STATUS_COLORS: Record<SearchRunStatus, string> = {
  pending: '#f59e0b',
  running: '#3b82f6',
  done: '#16a34a',
  failed: '#dc2626',
};

export function HistoryPanel({ onSelectRun, activeRunId }: Props) {
  const { t } = useTranslation();
  const { data: history, isLoading } = useSearchHistory();

  if (isLoading) return <p style={{ fontSize: 12, color: '#666', padding: '8px 0' }}>{t('loading')}</p>;
  if (!history?.length) return null;

  return (
    <div style={{ marginTop: 16 }}>
      <h4 style={{ margin: '0 0 8px', fontSize: 13, color: '#374151' }}>{t('history')}</h4>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0, maxHeight: 300, overflowY: 'auto' }}>
        {history.map(run => (
          <li
            key={run.id}
            onClick={() => onSelectRun(run.id)}
            style={{
              padding: '6px 8px',
              marginBottom: 4,
              cursor: 'pointer',
              borderRadius: 4,
              background: run.id === activeRunId ? '#dbeafe' : '#f9fafb',
              border: '1px solid #e5e7eb',
            }}
          >
            <div style={{ fontSize: 12, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {run.user_query.slice(0, 50)}{run.user_query.length > 50 ? '…' : ''}
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 2 }}>
              <span style={{ fontSize: 11, color: '#6b7280' }}>
                {new Date(run.created_at).toLocaleDateString()}
              </span>
              <span style={{ fontSize: 11, color: STATUS_COLORS[run.status], fontWeight: 600 }}>
                {t(`status_${run.status}`, run.status)}
              </span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
