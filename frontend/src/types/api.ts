export type SearchRunStatus = 'pending' | 'running' | 'done' | 'failed';

export interface CriterionBreakdown {
  type: string;
  confidence: number;
  actual_value?: number;
  threshold?: number;
  raw_data?: Record<string, unknown>;
  confidence_note?: string;
}

export interface SearchResult {
  city_id: number;
  city_name: string;
  province: string;
  lat: number;
  lon: number;
  overall_confidence: number;
  criteria_breakdown: CriterionBreakdown[];
}

export interface ComparisonSummary {
  added_cities: number[];
  removed_cities: number[];
  confidence_deltas: Record<string, number>;
}

export interface SearchRunResponse {
  run_id: string;
  status: SearchRunStatus;
  user_query: string;
  created_at: string;
  completed_at?: string;
  results?: SearchResult[];
  comparison_summary?: ComparisonSummary;
}

export interface HistoryItem {
  id: string;
  user_query: string;
  created_at: string;
  status: SearchRunStatus;
}
