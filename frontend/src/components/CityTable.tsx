import { useRef, useEffect, useState } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from '@tanstack/react-table';
import { useTranslation } from 'react-i18next';
import type { SearchResult, ComparisonSummary, CriterionBreakdown } from '../types/api';
import { criterionConfidence } from '../lib/confidence';

interface Props {
  results: SearchResult[];
  comparisonSummary?: ComparisonSummary;
  tolerance: number;
  selectedCityId: number | null;
  onCitySelect: (id: number) => void;
}

interface TableRow extends SearchResult {
  computedConfidence: number;
  delta?: number;
  isAdded?: boolean;
  isDropped?: boolean;
}

function recomputeConfidence(result: SearchResult, tolerance: number): number {
  if (!result.criteria_breakdown?.length) return result.overall_confidence;
  const scores = result.criteria_breakdown.map(c => {
    if (c.actual_value !== undefined && c.threshold !== undefined) {
      return criterionConfidence(c.actual_value, c.threshold, tolerance);
    }
    return c.confidence;
  });
  return scores.length ? Math.min(...scores) : result.overall_confidence;
}

const col = createColumnHelper<TableRow>();

function CriterionRow({ c }: { c: CriterionBreakdown }) {
  const { t } = useTranslation();
  const key = `criteria_${c.type}`;
  return (
    <div style={{ padding: '4px 8px', borderBottom: '1px solid #f0f0f0', fontSize: 12 }}>
      <strong>{t(key, c.type)}</strong>: {Math.round(c.confidence * 100)}%
      {c.actual_value !== undefined && <span style={{ color: '#666' }}> (actual: {c.actual_value})</span>}
      {c.confidence_note && <span style={{ color: '#888', fontStyle: 'italic' }}> — {c.confidence_note}</span>}
    </div>
  );
}

export function CityTable({ results, comparisonSummary, tolerance, selectedCityId, onCitySelect }: Props) {
  const { t } = useTranslation();
  const rowRefs = useRef<Record<number, HTMLTableRowElement | null>>({});
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (selectedCityId !== null && rowRefs.current[selectedCityId]) {
      rowRefs.current[selectedCityId]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [selectedCityId]);

  const addedSet = new Set(comparisonSummary?.added_cities ?? []);
const deltas = comparisonSummary?.confidence_deltas ?? {};
  const hasComparison = !!comparisonSummary;

  const rows: TableRow[] = [
    ...results.map(r => ({
      ...r,
      computedConfidence: recomputeConfidence(r, tolerance),
      delta: deltas[String(r.city_id)] !== undefined ? deltas[String(r.city_id)] : undefined,
      isAdded: addedSet.has(r.city_id),
      isDropped: false,
    })),
    // Dropped cities have no results entry — show as stubs
    ...(comparisonSummary?.removed_cities.map(id => ({
      city_id: id,
      city_name: `#${id}`,
      province: '—',
      lat: 0,
      lon: 0,
      overall_confidence: 0,
      criteria_breakdown: [],
      computedConfidence: 0,
      isDropped: true,
    })) ?? []),
  ];

  const columns = [
    col.accessor('city_name', {
      header: t('city'),
      cell: info => {
        const row = info.row.original;
        return (
          <span>
            {row.isAdded && <span style={{ color: '#16a34a', fontWeight: 'bold', marginRight: 4 }}>{t('new_city')}</span>}
            {row.isDropped && <span style={{ color: '#9ca3af', fontWeight: 'bold', marginRight: 4 }}>{t('dropped_city')}</span>}
            {info.getValue()}
          </span>
        );
      },
    }),
    col.accessor('province', { header: t('province') }),
    col.accessor('computedConfidence', {
      header: t('confidence'),
      cell: info => `${Math.round(info.getValue() * 100)}%`,
    }),
    ...(hasComparison
      ? [
          col.accessor('delta', {
            header: t('confidence_delta'),
            cell: info => {
              const v = info.getValue();
              if (v === undefined) return '—';
              const pct = Math.round(v * 100);
              return (
                <span style={{ color: pct >= 0 ? '#16a34a' : '#dc2626' }}>
                  {pct >= 0 ? '▲' : '▼'} {Math.abs(pct)}%
                </span>
              );
            },
          }),
        ]
      : []),
  ];

  const table = useReactTable({ data: rows, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <div style={{ overflowY: 'auto', height: '100%' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead style={{ position: 'sticky', top: 0, background: '#f9fafb' }}>
          {table.getHeaderGroups().map(hg => (
            <tr key={hg.id}>
              <th style={{ width: 24, padding: '6px 4px', borderBottom: '2px solid #e5e7eb' }} />
              {hg.headers.map(h => (
                <th key={h.id} style={{ padding: '6px 8px', textAlign: 'left', borderBottom: '2px solid #e5e7eb', whiteSpace: 'nowrap' }}>
                  {flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map(row => {
            const city = row.original;
            const isSelected = city.city_id === selectedCityId;
            const isExpanded = expandedRows.has(city.city_id);
            const bg = city.isDropped ? '#f3f4f6' : isSelected ? '#dbeafe' : undefined;

            return (
              <>
                <tr
                  key={row.id}
                  ref={el => { rowRefs.current[city.city_id] = el; }}
                  onClick={() => !city.isDropped && onCitySelect(city.city_id)}
                  style={{ cursor: city.isDropped ? 'default' : 'pointer', background: bg, opacity: city.isDropped ? 0.5 : 1 }}
                >
                  <td
                    style={{ padding: '4px', textAlign: 'center', borderBottom: '1px solid #e5e7eb' }}
                    onClick={e => { e.stopPropagation(); setExpandedRows(prev => { const n = new Set(prev); n.has(city.city_id) ? n.delete(city.city_id) : n.add(city.city_id); return n; }); }}
                  >
                    {city.criteria_breakdown.length > 0 && (isExpanded ? '▼' : '▶')}
                  </td>
                  {row.getVisibleCells().map(cell => (
                    <td key={cell.id} style={{ padding: '6px 8px', borderBottom: '1px solid #e5e7eb' }}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
                {isExpanded && city.criteria_breakdown.length > 0 && (
                  <tr key={`${row.id}-detail`} style={{ background: '#f8fafc' }}>
                    <td colSpan={columns.length + 1} style={{ borderBottom: '1px solid #e5e7eb' }}>
                      {city.criteria_breakdown.map((c, i) => <CriterionRow key={i} c={c} />)}
                    </td>
                  </tr>
                )}
              </>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
