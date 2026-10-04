import {
  DatasetDetailResponse,
  DatasetListResponse,
  DatasetColumnsResponse,
  DatasetDeleteResponse,
  RuleDefinition,
  ExecuteRuleRequest,
  FDDExecutionSummary,
  FaultDetailRecord,
  GraphPayload,
  FaultTimelinePayload,
  ThresholdCatalogResponse,
  ResultValidationReport,
  HistorianTelemetryResponse,
} from '../types/api';

// Configurable API base URL: supports production Render URL via VITE_API_BASE_URL
// and falls back to '/api' for local dev (proxied to http://127.0.0.1:8000 via vite.config.ts)
const RAW_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || '';
const API_BASE = RAW_BASE
  ? (RAW_BASE.replace(/\/+$/, '').endsWith('/api')
      ? RAW_BASE.replace(/\/+$/, '')
      : `${RAW_BASE.replace(/\/+$/, '')}/api`)
  : '/api';

async function safeFetch(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (err: any) {
    const target = API_BASE.startsWith('http') ? API_BASE : 'http://127.0.0.1:8000';
    throw new Error(
      `Cannot connect to Open-FDD backend (${err.message || 'Failed to fetch'}). Please ensure the FastAPI backend is running at ${target}.`
    );
  }
}

async function handleResponseJson<T>(res: Response, fallbackMessage: string): Promise<T> {
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: `${fallbackMessage} (${res.status})` }));
    throw new Error(errorData.detail || `${fallbackMessage} (${res.status})`);
  }
  return res.json();
}

export async function checkHealth(): Promise<{ status: string }> {
  const res = await safeFetch(`${API_BASE}/health`);
  return handleResponseJson(res, 'Health check failed');
}

export async function uploadDatasets(files: File[]): Promise<DatasetListResponse> {
  const formData = new FormData();
  for (const file of files) {
    formData.append('files', file);
  }

  // Do NOT set Content-Type header so browser automatically sets boundary
  const res = await safeFetch(`${API_BASE}/datasets/upload`, {
    method: 'POST',
    body: formData,
  });

  return handleResponseJson(res, 'Failed to upload datasets');
}

export async function getDatasets(): Promise<DatasetListResponse> {
  const res = await safeFetch(`${API_BASE}/datasets`);
  return handleResponseJson(res, 'Failed to fetch datasets list');
}

export async function getDatasetDetails(datasetId: string): Promise<DatasetDetailResponse> {
  const res = await safeFetch(`${API_BASE}/datasets/${encodeURIComponent(datasetId)}`);
  return handleResponseJson(res, `Failed to fetch dataset details for ${datasetId}`);
}

export async function getDatasetColumns(datasetId: string): Promise<DatasetColumnsResponse> {
  const res = await safeFetch(`${API_BASE}/datasets/${encodeURIComponent(datasetId)}/columns`);
  return handleResponseJson(res, `Failed to fetch dataset columns for ${datasetId}`);
}

export async function deleteDataset(datasetId: string): Promise<DatasetDeleteResponse> {
  const res = await safeFetch(`${API_BASE}/datasets/${encodeURIComponent(datasetId)}`, {
    method: 'DELETE',
  });
  return handleResponseJson(res, `Failed to delete dataset ${datasetId}`);
}

// ==========================================
// FDD Execution & Rule Catalog APIs
// ==========================================

export async function listRules(equipmentKind?: string): Promise<RuleDefinition[]> {
  const query = equipmentKind ? `?equipment_kind=${encodeURIComponent(equipmentKind)}` : '';
  const res = await safeFetch(`${API_BASE}/fdd/rules${query}`);
  return handleResponseJson(res, 'Failed to fetch rules catalog');
}

export async function getRuleDetails(ruleId: string): Promise<RuleDefinition> {
  const res = await safeFetch(`${API_BASE}/fdd/rules/${encodeURIComponent(ruleId)}`);
  return handleResponseJson(res, `Failed to fetch rule details for ${ruleId}`);
}

export async function executeRulesForEquipment(
  equipmentId: string,
  buildingId?: string | null,
  payload?: ExecuteRuleRequest
): Promise<FDDExecutionSummary> {
  const query = buildingId ? `?building_id=${encodeURIComponent(buildingId)}` : '';
  const res = await safeFetch(`${API_BASE}/fdd/execute/${encodeURIComponent(equipmentId)}${query}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  });
  return handleResponseJson(res, `FDD execution failed for equipment ${equipmentId}`);
}

export async function executeAllEquipment(
  buildingId?: string | null,
  payload?: ExecuteRuleRequest
): Promise<FDDExecutionSummary[]> {
  const query = buildingId ? `?building_id=${encodeURIComponent(buildingId)}` : '';
  const res = await safeFetch(`${API_BASE}/fdd/execute-all${query}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  });
  return handleResponseJson(res, 'Fleet FDD execution failed');
}

export async function getEquipmentFaults(
  equipmentId: string,
  buildingId?: string | null
): Promise<FaultDetailRecord[]> {
  const query = buildingId ? `?building_id=${encodeURIComponent(buildingId)}` : '';
  const res = await safeFetch(`${API_BASE}/fdd/faults/${encodeURIComponent(equipmentId)}${query}`);
  return handleResponseJson(res, `Failed to fetch faults for equipment ${equipmentId}`);
}

export async function getEquipmentRuleFault(
  equipmentId: string,
  ruleId: string,
  buildingId?: string | null
): Promise<FaultDetailRecord> {
  const query = buildingId ? `?building_id=${encodeURIComponent(buildingId)}` : '';
  const res = await safeFetch(
    `${API_BASE}/fdd/faults/${encodeURIComponent(equipmentId)}/${encodeURIComponent(ruleId)}${query}`
  );
  return handleResponseJson(res, `Failed to fetch rule fault for ${equipmentId} / ${ruleId}`);
}

// ==========================================
// Graph & Visualization APIs
// ==========================================

export async function getAvailableGraphs(equipmentId: string, buildingId?: string | null): Promise<any[]> {
  const query = buildingId ? `?building_id=${encodeURIComponent(buildingId)}` : '';
  const res = await safeFetch(`${API_BASE}/graphs/available/${encodeURIComponent(equipmentId)}${query}`);
  return handleResponseJson(res, `Failed to fetch available graphs for ${equipmentId}`);
}

export async function getTelemetryGraph(
  equipmentId: string,
  buildingId?: string | null,
  category?: string
): Promise<GraphPayload> {
  const params = new URLSearchParams();
  if (buildingId) params.set('building_id', buildingId);
  if (category) params.set('category', category);
  params.set('max_points', '5000');

  const res = await safeFetch(`${API_BASE}/graphs/telemetry/${encodeURIComponent(equipmentId)}?${params.toString()}`);
  return handleResponseJson(res, `Failed to fetch telemetry graph for ${equipmentId}`);
}

export async function getRuleGraph(
  equipmentId: string,
  ruleId: string,
  buildingId?: string | null
): Promise<GraphPayload> {
  const params = new URLSearchParams();
  if (buildingId) params.set('building_id', buildingId);
  params.set('max_points', '5000');

  const res = await safeFetch(
    `${API_BASE}/graphs/rule/${encodeURIComponent(equipmentId)}/${encodeURIComponent(ruleId)}?${params.toString()}`
  );
  return handleResponseJson(res, `Failed to fetch rule graph for ${ruleId}`);
}

export async function getFaultTimeline(
  equipmentId: string,
  buildingId?: string | null
): Promise<FaultTimelinePayload> {
  const query = buildingId ? `?building_id=${encodeURIComponent(buildingId)}` : '';
  const res = await safeFetch(`${API_BASE}/graphs/timeline/${encodeURIComponent(equipmentId)}${query}`);
  return handleResponseJson(res, `Failed to fetch fault timeline for ${equipmentId}`);
}

// ==========================================
// Threshold Metadata API
// ==========================================

export async function getThresholdMetadata(): Promise<ThresholdCatalogResponse> {
  const res = await safeFetch(`${API_BASE}/fdd/threshold-metadata`);
  return handleResponseJson(res, 'Failed to fetch threshold catalog metadata');
}

// ==========================================
// Result Validation & Historian Data APIs
// ==========================================

export async function getResultValidationReport(
  equipmentId: string,
  buildingId?: string | null
): Promise<ResultValidationReport> {
  const query = buildingId ? `?building_id=${encodeURIComponent(buildingId)}` : '';
  const res = await safeFetch(`${API_BASE}/fdd/validation-report/${encodeURIComponent(equipmentId)}${query}`);
  return handleResponseJson(res, `Failed to fetch validation report for ${equipmentId}`);
}

export async function getHistorianEquipmentTelemetry(
  equipmentId: string,
  buildingId?: string | null,
  previewLimit: number = 100
): Promise<HistorianTelemetryResponse> {
  const params = new URLSearchParams();
  if (buildingId) params.set('building_id', buildingId);
  params.set('preview_limit', previewLimit.toString());

  const res = await safeFetch(`${API_BASE}/historian/equipment/${encodeURIComponent(equipmentId)}?${params.toString()}`);
  return handleResponseJson(res, `Failed to fetch historical telemetry for ${equipmentId}`);
}

export function getNormalizedDataDownloadUrl(
  equipmentId?: string | null,
  buildingId?: string | null
): string {
  const params = new URLSearchParams();
  if (equipmentId) {
    params.set('equipment_id', equipmentId);
  }
  if (buildingId) {
    params.set('building_id', buildingId);
  }
  return `${API_BASE}/historian/download/csv?${params.toString()}`;
}


