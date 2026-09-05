import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import i18n from '../i18n';
import { useStartSearch, useSearchHistory, useSearchRun } from '../hooks/useSearchRun';

interface Props {
  onRunStarted: (runId: string) => void;
  tolerance: number;
  onToleranceChange: (v: number) => void;
  compareToRunId: string | undefined;
  onCompareToRunIdChange: (v: string | undefined) => void;
  activeRunId: string | null;
}

export function SearchForm({ onRunStarted, tolerance, onToleranceChange, compareToRunId, onCompareToRunIdChange, activeRunId }: Props) {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const startSearch = useStartSearch();
  const history = useSearchHistory();
  const activeRun = useSearchRun(activeRunId);

  const isPolling = activeRun.data && (activeRun.data.status === 'pending' || activeRun.data.status === 'running');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    const result = await startSearch.mutateAsync({
      query,
      tolerance,
      compare_to_run_id: compareToRunId,
      language: i18n.language.startsWith('ru') ? 'ru' : 'en',
    });
    onRunStarted(result.run_id);
  }

  return (
    <form onSubmit={handleSubmit} style={{ padding: '12px 0' }}>
      <div style={{ marginBottom: 10 }}>
        <textarea
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder={t('search_placeholder')}
          rows={4}
          style={{ width: '100%', boxSizing: 'border-box', padding: 8, border: '1px solid #ccc', borderRadius: 4, resize: 'vertical', fontSize: 13 }}
        />
      </div>

      <div style={{ marginBottom: 10 }}>
        <label style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
          <span>{t('tolerance')}</span>
          <span>{tolerance} km</span>
        </label>
        <input
          type="range"
          min={0}
          max={100}
          step={5}
          value={tolerance}
          onChange={e => onToleranceChange(Number(e.target.value))}
          style={{ width: '100%' }}
        />
      </div>

      <div style={{ marginBottom: 12 }}>
        <label style={{ display: 'block', fontSize: 13, marginBottom: 4 }}>{t('compare_with')}</label>
        <select
          value={compareToRunId ?? ''}
          onChange={e => onCompareToRunIdChange(e.target.value || undefined)}
          style={{ width: '100%', padding: '6px', border: '1px solid #ccc', borderRadius: 4, fontSize: 13 }}
        >
          <option value="">{t('no_comparison')}</option>
          {history.data?.map(run => (
            <option key={run.id} value={run.id}>
              {run.user_query.slice(0, 40)}{run.user_query.length > 40 ? '…' : ''} ({run.status})
            </option>
          ))}
        </select>
      </div>

      <button
        type="submit"
        disabled={startSearch.isPending || !!isPolling}
        style={{ width: '100%', padding: '10px', background: '#2563eb', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 14 }}
      >
        {isPolling ? (
          <span>{t('loading')} ⟳</span>
        ) : (
          t('search')
        )}
      </button>

      {startSearch.isError && (
        <p style={{ color: '#c00', fontSize: 12, marginTop: 8 }}>
          {String((startSearch.error as Error)?.message ?? 'Error')}
        </p>
      )}
    </form>
  );
}
