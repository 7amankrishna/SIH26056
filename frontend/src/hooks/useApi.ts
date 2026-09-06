// Centralized React Query wrappers. Each dashboard screen composes these hooks
// instead of hand-rolling fetch + state management.

import { useQuery } from "@tanstack/react-query";
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

export function useQualityRejected() {
  return useQuery({ queryKey: ["quality", "rejected"], queryFn: api.qualityRejected });
}

export function useCollectionRuns() {
  return useQuery({ queryKey: ["collection-runs"], queryFn: api.collectionRuns, refetchInterval: 60_000 });
}

export function useMethodology() {
  return useQuery({ queryKey: ["methodology"], queryFn: api.methodology });
}

export function useProvenance(indexId: string) {
  return useQuery({ queryKey: ["provenance", indexId], queryFn: () => api.provenance(indexId), enabled: !!indexId });
}

export function useStatsOverview() {
  return useQuery({ queryKey: ["stats-overview"], queryFn: api.statsOverview });
}
