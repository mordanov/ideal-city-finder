import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import i18n from './i18n';
import { useSearchRun } from './hooks/useSearchRun';
import { SearchForm } from './components/SearchForm';
import { MapView } from './components/MapView';
import { CityTable } from './components/CityTable';
import { HistoryPanel } from './components/HistoryPanel';
import { apiClient } from './api/client';

export default function App() {
  const { t } = useTranslation();
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [selectedCityId, setSelectedCityId] = useState<number | null>(null);
  const [tolerance, setTolerance] = useState(20);
  const [compareToRunId, setCompareToRunId] = useState<string | undefined>();

  const { data: runData } = useSearchRun(activeRunId);
  const results = runData?.results ?? [];
  const comparisonSummary = runData?.comparison_summary;

  function handleLanguageToggle(lang: 'en' | 'ru') {
    i18n.changeLanguage(lang);
    document.cookie = `i18next=${lang}; path=/`;
  }

  async function handleLogout() {
    try {
      await apiClient.post('/api/auth/logout');
    } catch {
      // ignore
    }
    document.cookie = 'access_token=; Max-Age=0; path=/';
    window.location.href = '/login';
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', fontFamily: 'system-ui, sans-serif' }}>
      {/* Header */}
      <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 16px', background: '#1d4ed8', color: '#fff', flexShrink: 0 }}>
        <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>{t('app_title')}</h1>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button onClick={() => handleLanguageToggle('en')} style={{ background: i18n.language.startsWith('en') ? '#fff' : 'transparent', color: i18n.language.startsWith('en') ? '#1d4ed8' : '#fff', border: '1px solid rgba(255,255,255,0.5)', borderRadius: 4, padding: '4px 10px', cursor: 'pointer', fontWeight: 600 }}>EN</button>
          <button onClick={() => handleLanguageToggle('ru')} style={{ background: i18n.language.startsWith('ru') ? '#fff' : 'transparent', color: i18n.language.startsWith('ru') ? '#1d4ed8' : '#fff', border: '1px solid rgba(255,255,255,0.5)', borderRadius: 4, padding: '4px 10px', cursor: 'pointer', fontWeight: 600 }}>RU</button>
          <button onClick={handleLogout} style={{ background: 'transparent', color: '#fff', border: '1px solid rgba(255,255,255,0.5)', borderRadius: 4, padding: '4px 10px', cursor: 'pointer' }}>{t('logout')}</button>
        </div>
      </header>

      {/* Body */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Sidebar */}
        <aside style={{ width: '22%', minWidth: 240, maxWidth: 320, borderRight: '1px solid #e5e7eb', padding: '12px 14px', overflowY: 'auto', background: '#fff' }}>
          <SearchForm
            onRunStarted={(id) => { setActiveRunId(id); setSelectedCityId(null); }}
            tolerance={tolerance}
            onToleranceChange={setTolerance}
            compareToRunId={compareToRunId}
            onCompareToRunIdChange={setCompareToRunId}
            activeRunId={activeRunId}
          />
          <HistoryPanel
            onSelectRun={(id) => { setActiveRunId(id); setSelectedCityId(null); }}
            activeRunId={activeRunId}
          />
        </aside>

        {/* Main content: map top, table bottom */}
        <main style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ flex: '0 0 55%', minHeight: 200 }}>
            {results.length > 0 ? (
              <MapView
                results={results}
                comparisonSummary={comparisonSummary}
                selectedCityId={selectedCityId}
                onCitySelect={setSelectedCityId}
              />
            ) : (
              <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#9ca3af', fontSize: 14 }}>
                {t('no_results')}
              </div>
            )}
          </div>
          <div style={{ flex: '0 0 45%', borderTop: '1px solid #e5e7eb', overflow: 'hidden' }}>
            {results.length > 0 ? (
              <CityTable
                results={results}
                comparisonSummary={comparisonSummary}
                tolerance={tolerance}
                selectedCityId={selectedCityId}
                onCitySelect={setSelectedCityId}
              />
            ) : (
              <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#9ca3af', fontSize: 14 }}>
                {t('no_results')}
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
