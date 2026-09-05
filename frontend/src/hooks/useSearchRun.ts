import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import type { SearchRunResponse, HistoryItem } from '../types/api';

export function useStartSearch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      query: string;
      tolerance: number;
      compare_to_run_id?: string;
      language: string;
    }) =>
      apiClient
        .post<{ run_id: string }>('/api/search', payload)
        .then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['history'] }),
  });
}

export function useSearchRun(runId: string | null) {
  return useQuery<SearchRunResponse>({
    queryKey: ['run', runId],
    queryFn: () =>
      apiClient.get(`/api/search/${runId}`).then((r) => r.data),
    enabled: !!runId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'done' || status === 'failed' ? false : 2000;
    },
  });
}

export function useSearchHistory() {
  return useQuery<HistoryItem[]>({
    queryKey: ['history'],
    queryFn: () => apiClient.get('/api/search/history').then((r) => r.data),
  });
}
