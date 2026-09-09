// Centralized React Query wrappers. Each dashboard screen composes these hooks
// instead of hand-rolling fetch + state management.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 60_000 });
}

export function useOverview() {
  return useQuery({ queryKey: ["overview"], queryFn: api.overview, refetchInterval: 60_000 });
}

export function useTrend(range: string) {
  return useQuery({ queryKey: ["trend", range], queryFn: () => api.trend(range) });
}

export function useRoutes(top?: number) {
  return useQuery({ queryKey: ["routes", top], queryFn: () => api.routes(top) });
}

export function useRouteHeatmap() {
  return useQuery({ queryKey: ["routes", "heatmap"], queryFn: api.routeHeatmap });
}

export function useRouteDetail(route: string) {
  return useQuery({
    queryKey: ["route", route],
    queryFn: () => api.routeDetail(route),
    enabled: !!route,
  });
}

export function useAirlines(route?: string) {
  return useQuery({ queryKey: ["airlines", route], queryFn: () => api.airlines(route) });
}

export function useLeadTime(params?: { route?: string; airline?: string; source?: string }) {
  return useQuery({ queryKey: ["leadtime", params], queryFn: () => api.leadTime(params) });
}

export function useFareDistribution(route?: string) {
  return useQuery({ queryKey: ["distribution", route], queryFn: () => api.fareDistribution(route) });
}

export function useQuality() {
  return useQuery({ queryKey: ["quality"], queryFn: api.quality });
}

export function useCollectionRuns() {
  return useQuery({ queryKey: ["collection-runs"], queryFn: api.collectionRuns, refetchInterval: 60_000 });
}

export function useProvenance(indexId: string) {
  return useQuery({ queryKey: ["provenance", indexId], queryFn: () => api.provenance(indexId), enabled: !!indexId });
}

export function useStatsOverview() {
  return useQuery({ queryKey: ["stats-overview"], queryFn: api.statsOverview });
}

// --- imported data (upload / manage files) --------------------------------- //

export function useDataFiles() {
  return useQuery({ queryKey: ["data-files"], queryFn: api.dataFiles });
}

/** Everything that changes when the imported data changes. */
const DATA_KEYS = [
  "data-files", "overview", "trend", "routes", "airlines", "leadtime",
  "distribution", "quality", "collection-runs", "stats-overview", "provenance",
];

export function useUploadDataFiles() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (files: File[]) => api.uploadDataFiles(files),
    onSuccess: () => DATA_KEYS.forEach((k) => qc.invalidateQueries({ queryKey: [k] })),
  });
}

export function useDeleteDataFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.deleteDataFile(name),
    onSuccess: () => DATA_KEYS.forEach((k) => qc.invalidateQueries({ queryKey: [k] })),
  });
}

export function useDatabaseStatus() {
  return useQuery({ queryKey: ["data-database"], queryFn: api.databaseStatus });
}

export function usePersistDataFiles() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file?: string) => api.persistDataFiles(file),
    onSuccess: () => {
      DATA_KEYS.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      qc.invalidateQueries({ queryKey: ["data-database"] });
    },
  });
}

export function useReloadDataFiles() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.reloadDataFiles(),
    onSuccess: () => DATA_KEYS.forEach((k) => qc.invalidateQueries({ queryKey: [k] })),
  });
}
