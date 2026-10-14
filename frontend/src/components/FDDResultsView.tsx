import React, { useState, useEffect, useMemo } from 'react';
import {
  Download,
  ChevronDown,
  ChevronUp,
  ChevronRight,
  Table,
  Activity,
  Info,
} from 'lucide-react';
import {
  FDDExecutionSummary,
  FaultDetailRecord,
  GraphPayload,
  FaultTimelinePayload,
  SensorFaultDetail,
} from '../types/api';
import {
  getEquipmentFaults,
  getTelemetryGraph,
  getRuleGraph,
  getHistorianEquipmentTelemetry,
  getNormalizedDataDownloadUrl,
  getFaultTimeline,
} from '../services/api';
import { TelemetryGraph } from './TelemetryGraph';
import { FaultTimelineGraph } from './FaultTimelineGraph';
import { ResultValidationSection } from './ResultValidationSection';

interface Props {
  summary: FDDExecutionSummary;
  equipmentId: string;
  buildingId?: string | null;
  availableEquipment?: string[];
  onSelectEquipment?: (eq: string) => void;
}

export const FDDResultsView: React.FC<Props> = ({
  summary,
  equipmentId,
  buildingId,
  availableEquipment = [],
  onSelectEquipment,
}) => {
  const [selectedEquipment, setSelectedEquipment] = useState<string>(equipmentId);
  const [activeTab, setActiveTab] = useState<'faults' | 'temperature' | 'airside' | 'chw'>('faults');
  const [faultDetails, setFaultDetails] = useState<FaultDetailRecord[]>([]);
  const [selectedRuleId, setSelectedRuleId] = useState<string | null>(null);
  const [ruleGraphData, setRuleGraphData] = useState<GraphPayload | null>(null);
  const [tempGraphData, setTempGraphData] = useState<GraphPayload | null>(null);
  const [airsideGraphData, setAirsideGraphData] = useState<GraphPayload | null>(null);
  const [chwGraphData, setChwGraphData] = useState<GraphPayload | null>(null);
  const [isEpisodesExpanded, setIsEpisodesExpanded] = useState<boolean>(false);
  const [expandedRuleIds, setExpandedRuleIds] = useState<Set<string>>(new Set());
  const [timelineData, setTimelineData] = useState<FaultTimelinePayload | null>(null);

  // Normalized sensor data state
  const [normalizedRecords, setNormalizedRecords] = useState<Record<string, any>[]>([]);
  const [normalizedColumns, setNormalizedColumns] = useState<string[]>([]);

  // Sync selectedEquipment when prop changes
  useEffect(() => {
    if (equipmentId) {
      setSelectedEquipment(equipmentId);
    }
  }, [equipmentId]);

  const eqList = useMemo(() => {
    const set = new Set<string>();
    if (equipmentId) set.add(equipmentId);
    for (const eq of availableEquipment) {
      if (eq) set.add(eq);
    }
    for (const r of summary.results) {
      for (const f of r.findings) {
        if (f.equipment_id) set.add(f.equipment_id);
      }
    }
    return Array.from(set).sort();
  }, [equipmentId, availableEquipment, summary]);

  const effectiveEquipmentId = equipmentId || selectedEquipment || eqList[0] || '';

  // Equipment options matching individual equipment IDs only
  const equipmentOptions = useMemo(() => {
    return eqList.length > 0 ? eqList : [equipmentId];
  }, [eqList, equipmentId]);

  // Grouped findings from execution summary with preserved sensor attributions
  const findingsList = useMemo(() => {
    const list: Array<{
      equipment_id: string;
      rule_id: string;
      fault_name: string;
      severity: string;
      samples: number;
      episodes: number;
      total_duration_hours: number;
      first_seen?: string;
      last_seen?: string;
      detail?: FaultDetailRecord;
      sensors: SensorFaultDetail[];
      display_label: string;
    }> = [];

    for (const r of summary.results) {
      for (const f of r.findings) {
        if (f.fault_detected) {
          const eqVal = f.equipment_id || summary.equipment_id || equipmentId;
          const codeVal = f.rule_id;
          const nameVal = f.detail?.title || f.description;
          const sevVal = f.severity || f.detail?.severity || 'HIGH';
          const sampleCount = f.sample_count || (f.episodes ? f.episodes.reduce((a, b) => a + b.samples, 0) : 0);
          const epCount = f.episodes ? f.episodes.length : (f.detail?.episode_count || 1);
          const durHours = f.fault_hours || (f.detail?.total_fault_hours || 0);

          list.push({
            equipment_id: eqVal,
            rule_id: codeVal,
            fault_name: nameVal,
            severity: sevVal,
            samples: sampleCount,
            episodes: epCount,
            total_duration_hours: durHours,
            first_seen: f.episodes && f.episodes.length > 0 ? f.episodes[0].start : undefined,
            last_seen: f.episodes && f.episodes.length > 0 ? f.episodes[f.episodes.length - 1].end : undefined,
            detail: f.detail || undefined,
            sensors: (f.sensors && f.sensors.length > 0) ? f.sensors : (f.detail?.sensors || []),
            display_label: `${codeVal} — ${nameVal}`,
          });
        }
      }
    }
    return list;
  }, [summary, equipmentId]);

  // Filter findings for active equipment selection
  const filteredFindings = useMemo(() => {
    return findingsList.filter(
      (f) => f.equipment_id.toLowerCase() === effectiveEquipmentId.toLowerCase()
    );
  }, [findingsList, effectiveEquipmentId]);

  // Expand / collapse handlers
  const toggleExpandRule = (ruleId: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setExpandedRuleIds((prev) => {
      const next = new Set(prev);
      if (next.has(ruleId)) {
        next.delete(ruleId);
      } else {
        next.add(ruleId);
      }
      return next;
    });
  };

  const expandAllRules = () => {
    const all = new Set(filteredFindings.map((f) => f.rule_id));
    setExpandedRuleIds(all);
  };

  const collapseAllRules = () => {
    setExpandedRuleIds(new Set());
  };

  const getSensorsForFinding = (f: typeof findingsList[0]): SensorFaultDetail[] => {
    if (f.sensors && f.sensors.length > 0) return f.sensors;
    if (f.detail?.sensors && f.detail.sensors.length > 0) return f.detail.sensors;
    const match = faultDetails.find((d) => d.rule_id.toLowerCase() === f.rule_id.toLowerCase());
    return match?.sensors || [];
  };

  // Auto-select first fault rule if none selected
  useEffect(() => {
    if (filteredFindings.length > 0) {
      if (!selectedRuleId || !filteredFindings.some((f) => f.rule_id === selectedRuleId)) {
        setSelectedRuleId(filteredFindings[0].rule_id);
      }
    } else {
      setSelectedRuleId(null);
    }
  }, [filteredFindings, selectedRuleId]);

  // Reset graph data on equipment change to avoid showing previous equipment graphs
  useEffect(() => {
    setRuleGraphData(null);
    setTempGraphData(null);
    setAirsideGraphData(null);
    setChwGraphData(null);
    setTimelineData(null);
    setExpandedRuleIds(new Set());
  }, [effectiveEquipmentId]);

  // Fetch fault timeline for effective equipment
  useEffect(() => {
    const loadTimeline = async () => {
      if (!effectiveEquipmentId) return;
      try {
        const tl = await getFaultTimeline(effectiveEquipmentId, buildingId);
        setTimelineData(tl);
      } catch (e) {
        console.warn('Failed to load fault timeline:', e);
        setTimelineData(null);
      }
    };
    loadTimeline();
  }, [effectiveEquipmentId, buildingId, summary]);

  // Fetch fault details for effective equipment
  useEffect(() => {
    setFaultDetails([]);
    const loadData = async () => {
      if (!effectiveEquipmentId) return;
      try {
        const faults = await getEquipmentFaults(effectiveEquipmentId, buildingId);
        setFaultDetails(faults);
      } catch (e) {
        console.error('Failed to load fault diagnostics:', e);
      }
    };
    loadData();
  }, [effectiveEquipmentId, buildingId]);

  // Fetch normalized sensor telemetry from historian
  useEffect(() => {
    const loadNormalized = async () => {
      if (!effectiveEquipmentId) return;
      try {
        const res = await getHistorianEquipmentTelemetry(effectiveEquipmentId, buildingId, 100);
        setNormalizedColumns(res.columns || []);
        setNormalizedRecords((res as any).preview_rows || (res as any).records || []);
      } catch (e) {
        console.error('Failed to load normalized telemetry:', e);
      }
    };
    loadNormalized();
  }, [effectiveEquipmentId, buildingId]);

  // Fetch rule-specific graph when selectedRuleId changes
  useEffect(() => {
    const loadRuleGraph = async () => {
      if (!effectiveEquipmentId || !selectedRuleId) return;
      try {
        const g = await getRuleGraph(effectiveEquipmentId, selectedRuleId, buildingId);
        setRuleGraphData(g);
      } catch (e) {
        console.error(`Failed to load graph for rule ${selectedRuleId}:`, e);
      }
    };
    if (activeTab === 'faults' && selectedRuleId) {
      loadRuleGraph();
    }
  }, [effectiveEquipmentId, selectedRuleId, buildingId, activeTab]);

  // Fetch category graphs when switching tabs
  useEffect(() => {
    const loadCategoryGraph = async () => {
      if (!effectiveEquipmentId) return;
      try {
        if (activeTab === 'temperature') {
          const g = await getTelemetryGraph(effectiveEquipmentId, buildingId, 'temperature_dynamics');
          setTempGraphData(g);
        } else if (activeTab === 'airside') {
          const g = await getTelemetryGraph(effectiveEquipmentId, buildingId, 'airside');
          setAirsideGraphData(g);
        } else if (activeTab === 'chw') {
          const g = await getTelemetryGraph(effectiveEquipmentId, buildingId, 'hydronic');
          setChwGraphData(g);
        }
      } catch (e) {
        console.error(`Failed to load ${activeTab} graph:`, e);
      }
    };
    loadCategoryGraph();
  }, [activeTab, effectiveEquipmentId, buildingId]);

  // Top metric card values
  const highCount = filteredFindings.filter(
    (f) => f.severity === 'CRITICAL' || f.severity === 'HIGH'
  ).length;
  const uniqueFaults = new Set(filteredFindings.map((f) => f.rule_id)).size;
  const totalFaultSamples = filteredFindings.reduce((a, b) => a + b.samples, 0);

  // Selected fault record
  const selectedDetail = useMemo(() => {
    if (!selectedRuleId) return null;
    const match = faultDetails.find((d) => d.rule_id.toLowerCase() === selectedRuleId.toLowerCase());
    if (match) return match;
    const findMatch = filteredFindings.find((f) => f.rule_id.toLowerCase() === selectedRuleId.toLowerCase());
    return findMatch?.detail || null;
  }, [selectedRuleId, faultDetails, filteredFindings]);

  // Associated sensors for the selected fault record
  const inspectedSensors = useMemo(() => {
    if (!selectedDetail && !selectedRuleId) return [];
    if (selectedDetail?.sensors && selectedDetail.sensors.length > 0) {
      return selectedDetail.sensors;
    }
    const matchFinding = filteredFindings.find(
      (f) => f.rule_id.toLowerCase() === (selectedRuleId || selectedDetail?.rule_id || '').toLowerCase()
    );
    if (matchFinding?.sensors && matchFinding.sensors.length > 0) {
      return matchFinding.sensors;
    }
    return [];
  }, [selectedDetail, selectedRuleId, filteredFindings]);

  // CSV Export handler matching st.download_button
  const handleDownloadCSV = () => {
    if (filteredFindings.length === 0) return;
    const headers = ['fault_code', 'fault_name', 'severity', 'samples', 'episodes', 'total_duration_hours', 'first_seen', 'last_seen'];

    const rows = filteredFindings.map((f) => {
      return [
        f.rule_id,
        `"${f.fault_name.replace(/"/g, '""')}"`,
        f.severity,
        f.samples,
        f.episodes,
        f.total_duration_hours.toFixed(2),
        f.first_seen || '',
        f.last_seen || '',
      ];
    });

    const csvContent = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `fdd_diagnostic_findings_${effectiveEquipmentId}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Airside table columns to display below Airside graph matching Open-FDD standard
  const airsideCols = useMemo(() => {
    const candidates = [
      'timestamp',
      'ec_fan_speed_command_pct',
      'fan_cmd',
      'fan_vfd_speed',
      'duct_static_pressure_pa',
      'duct_static',
      'duct_static_pressure_setpoint_pa',
      'duct_static_sp',
      'co2_ppm',
      'co2',
      'room_humidity_pct',
      'room_humidity',
      'ahu_run_status',
    ];
    return candidates.filter((c) => normalizedColumns.includes(c));
  }, [normalizedColumns]);

  return (
    <div className="space-y-5 font-sans select-none text-[#fafafa]">
      {/* Equipment Discovery & Selector matching st.selectbox("Equipment", ...) */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-[rgba(250,250,250,0.12)] pb-3">
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm font-medium text-[#a3a8b8] whitespace-nowrap">Equipment:</label>
          <select
            id="equipment-selector"
            value={effectiveEquipmentId}
            onChange={(e) => {
              const val = e.target.value;
              setSelectedEquipment(val);
              if (onSelectEquipment) {
                onSelectEquipment(val);
              }
            }}
            className="st-input cursor-pointer font-sans font-semibold text-sm px-3 py-1.5 w-full sm:w-auto min-w-0 sm:min-w-44"
          >
            {equipmentOptions.map((opt) => (
              <option key={opt} value={opt}>
                {opt}
              </option>
            ))}
          </select>
        </div>

        {/* 4 Streamlit Metrics matching c1, c2, c3, c4 = st.columns(4) */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4 flex-1 w-full lg:max-w-2xl">
          <div className="st-metric-card">
            <div className="st-metric-label">Validated Timestamps</div>
            <div className="st-metric-value font-mono text-[#fafafa]">{normalizedRecords.length}</div>
          </div>
          <div className="st-metric-card">
            <div className="st-metric-label">Mapped Points</div>
            <div className="st-metric-value font-mono text-[#58a6ff]">
              {normalizedColumns.filter((c) => !['timestamp', 'equipment_id'].includes(c)).length}
            </div>
          </div>
          <div className="st-metric-card">
            <div className="st-metric-label">Fault Samples</div>
            <div className="st-metric-value font-mono text-[#ff7b72]">{totalFaultSamples}</div>
          </div>
          <div className="st-metric-card">
            <div className="st-metric-label">Unique Fault Types</div>
            <div className="st-metric-value font-mono text-[#ff7b72]">{uniqueFaults}</div>
            {highCount > 0 && <div className="st-metric-delta-neg">↓ {highCount} high-severity</div>}
          </div>
        </div>
      </div>


      {/* 4 Main Tabs matching tab1, tab2, tab3, tab4 = st.tabs(...) */}
      <div className="flex border-b border-[rgba(250,250,250,0.12)] overflow-x-auto scrollbar-none">
        {[
          { id: 'faults', label: 'Faults & Diagnostics' },
          { id: 'temperature', label: 'Air temperatures' },
          { id: 'airside', label: 'Airside' },
          { id: 'chw', label: 'Chilled water' },
        ].map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setActiveTab(t.id as any)}
            className={`st-tab-btn whitespace-nowrap shrink-0 ${activeTab === t.id ? 'st-tab-btn-active' : ''}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="space-y-4 pt-1">
        {/* TAB 1: FAULTS & DIAGNOSTICS */}
        {activeTab === 'faults' && (
          <div className="space-y-4">
            {/* Fault Episode Timeline Swimlanes */}
            {timelineData && (
              <div className="space-y-2">
                <FaultTimelineGraph
                  timeline={timelineData}
                  onSelectRule={(ruleId) => setSelectedRuleId(ruleId)}
                  selectedRuleId={selectedRuleId}
                />
              </div>
            )}

            {/* Fault Summary Table matching st.dataframe */}
            <div className="space-y-2">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-[#a3a8b8]">
                    Detected Fault Summary ({filteredFindings.length} active fault findings)
                  </span>
                  <span className="text-[11px] text-[#58a6ff] bg-[#161b22] px-2 py-0.5 rounded border border-[rgba(88,166,255,0.2)]">
                    Click chevron to inspect associated sensors
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-2 self-start sm:self-auto">
                  <button
                    type="button"
                    onClick={expandAllRules}
                    className="st-button-secondary text-xs px-2.5 py-1 flex items-center gap-1 hover:text-[#58a6ff]"
                    title="Expand all sensor details"
                  >
                    <ChevronDown className="w-3.5 h-3.5 text-[#58a6ff]" />
                    Expand all sensors
                  </button>
                  <button
                    type="button"
                    onClick={collapseAllRules}
                    className="st-button-secondary text-xs px-2.5 py-1 flex items-center gap-1 hover:text-[#a3a8b8]"
                    title="Collapse all sensor details"
                  >
                    <ChevronUp className="w-3.5 h-3.5 text-[#a3a8b8]" />
                    Collapse all
                  </button>
                  <button
                    type="button"
                    id="download-diagnostic-csv-btn"
                    onClick={handleDownloadCSV}
                    className="st-button-secondary text-xs px-2.5 py-1 flex items-center gap-1.5"
                  >
                    <Download className="w-3.5 h-3.5 text-[#58a6ff]" />
                    Download diagnostic CSV
                  </button>
                </div>
              </div>

              {filteredFindings.length === 0 ? (
                <div className="st-alert-success text-xs">
                  ✓ No persistent faults were detected for the active selection.
                </div>
              ) : (
                <div className="st-dataframe-container max-h-96 overflow-auto border border-[rgba(250,250,250,0.12)] rounded">
                  <table id="faults-detected-table" className="st-dataframe-table font-mono text-xs w-full">
                    <thead>
                      <tr>
                        <th className="w-8 text-center"></th>
                        <th>Fault Code</th>
                        <th>Fault Name</th>
                        <th>Samples</th>
                        <th>Episodes</th>
                        <th>Duration (Hours)</th>
                        <th>First Seen</th>
                        <th>Last Seen</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredFindings.map((f) => {
                        const isSelected = selectedRuleId?.toLowerCase() === f.rule_id.toLowerCase();
                        const isExpanded = expandedRuleIds.has(f.rule_id);
                        const findingSensors = getSensorsForFinding(f);
                        const formatFullTimestamp = (ts?: string) => {
                          if (!ts) return '--';
                          return ts.replace('T', ' ');
                        };
                        return (
                          <React.Fragment key={`${f.equipment_id}_${f.rule_id}`}>
                            <tr
                              onClick={() => setSelectedRuleId(f.rule_id)}
                              className={`cursor-pointer transition-colors ${
                                isSelected ? 'bg-[#262730] font-semibold' : 'hover:bg-[#1a1c23]'
                              }`}
                            >
                              <td
                                className="text-center px-1 py-2 text-[#a3a8b8] hover:text-[#58a6ff] cursor-pointer"
                                onClick={(e) => toggleExpandRule(f.rule_id, e)}
                                title={isExpanded ? 'Collapse sensor breakdown' : 'Expand sensor breakdown'}
                              >
                                {isExpanded ? (
                                  <ChevronDown className="w-4 h-4 inline-block text-[#58a6ff]" />
                                ) : (
                                  <ChevronRight className="w-4 h-4 inline-block" />
                                )}
                              </td>
                              <td className="text-[#58a6ff] font-bold">{f.rule_id}</td>
                              <td className="text-[#fafafa] font-sans">
                                <div className="flex items-center gap-2">
                                  <span>{f.fault_name}</span>
                                  {findingSensors.length > 0 && (
                                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#21262d] text-[#8b949e] border border-[rgba(250,250,250,0.08)]">
                                      {findingSensors.length} sensor{findingSensors.length > 1 ? 's' : ''}
                                    </span>
                                  )}
                                </div>
                              </td>
                              <td>{f.samples}</td>
                              <td>{f.episodes}</td>
                              <td className="text-[#ff7b72] font-bold">{f.total_duration_hours.toFixed(1)}</td>
                              <td className="text-[#a3a8b8] whitespace-nowrap">
                                {formatFullTimestamp(f.first_seen)}
                              </td>
                              <td className="text-[#a3a8b8] whitespace-nowrap">
                                {formatFullTimestamp(f.last_seen)}
                              </td>
                            </tr>
                            {isExpanded && (
                              <tr className="bg-[#12151c] border-b border-[rgba(250,250,250,0.1)]">
                                <td colSpan={8} className="p-3 pl-8">
                                  <div className="rounded border border-[rgba(250,250,250,0.12)] bg-[#1e222b] p-3 shadow-inner space-y-2">
                                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[rgba(250,250,250,0.08)] pb-2">
                                      <div className="flex items-center gap-2">
                                        <Activity className="w-4 h-4 text-[#58a6ff]" />
                                        <span className="text-xs font-bold text-[#fafafa] font-mono tracking-wide">
                                          ASSOCIATED SENSORS & TELEMETRY BREAKDOWN — {f.rule_id}
                                        </span>
                                        <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[rgba(88,166,255,0.15)] text-[#58a6ff] border border-[rgba(88,166,255,0.3)]">
                                          {findingSensors.length} {findingSensors.length === 1 ? 'Sensor Point' : 'Sensor Points'}
                                        </span>
                                      </div>
                                      <span className="text-[11px] text-[#a3a8b8] font-sans">
                                        Equipment: <strong className="text-[#fafafa] font-mono">{f.equipment_id}</strong>
                                      </span>
                                    </div>

                                    {findingSensors.length === 0 ? (
                                      <div className="p-3 text-xs text-[#a3a8b8] italic bg-[#161b22] rounded border border-[rgba(250,250,250,0.06)] flex items-center gap-2">
                                        <Info className="w-4 h-4 text-[#a3a8b8] shrink-0" />
                                        <span>Sensor attribution unavailable: Equipment-level finding without isolated single-sensor telemetry point.</span>
                                      </div>
                                    ) : (
                                      <div className="overflow-x-auto">
                                        <table className="w-full text-left font-mono text-xs border-collapse">
                                          <thead>
                                            <tr className="border-b border-[rgba(250,250,250,0.08)] text-[11px] text-[#a3a8b8] uppercase">
                                              <th className="py-1.5 px-2">Sensor Name</th>
                                              <th className="py-1.5 px-2">Canonical Role</th>
                                              <th className="py-1.5 px-2">Original CSV Column</th>
                                              <th className="py-1.5 px-2">Role Type / Detected Condition</th>
                                              <th className="py-1.5 px-2">Fault Interval</th>
                                              <th className="py-1.5 px-2">Duration</th>
                                              <th className="py-1.5 px-2 text-right">Observed Value</th>
                                            </tr>
                                          </thead>
                                          <tbody className="divide-y divide-[rgba(250,250,250,0.05)]">
                                            {findingSensors.map((s, idx) => (
                                              <tr key={`${s.canonical_role}_${idx}`} className="hover:bg-[rgba(255,255,255,0.02)]">
                                                <td className="py-2 px-2 font-sans font-medium text-[#fafafa] whitespace-nowrap">
                                                  {s.sensor_name || s.canonical_role}
                                                </td>
                                                <td className="py-2 px-2 whitespace-nowrap">
                                                  <span className="px-1.5 py-0.5 rounded text-[11px] font-mono bg-[#21262d] text-[#58a6ff] border border-[rgba(88,166,255,0.25)]">
                                                    {s.canonical_role}
                                                  </span>
                                                </td>
                                                <td className="py-2 px-2 whitespace-nowrap">
                                                  <code className="px-1.5 py-0.5 rounded text-[11px] font-mono bg-[#161b22] text-[#7ee787] border border-[rgba(126,231,135,0.25)]">
                                                    {s.original_column || '—'}
                                                  </code>
                                                </td>
                                                <td className="py-2 px-2 font-sans text-xs">
                                                  <div className="flex flex-wrap items-center gap-1.5">
                                                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono uppercase font-semibold ${
                                                      s.role_type === 'primary' ? 'bg-[rgba(255,75,75,0.15)] text-[#ff7b72] border border-[#ff4b4b]' :
                                                      s.role_type === 'reference_setpoint' ? 'bg-[rgba(210,153,34,0.15)] text-[#d29922] border border-[rgba(210,153,34,0.4)]' :
                                                      s.role_type === 'control_command' ? 'bg-[rgba(187,128,255,0.15)] text-[#d2a8ff] border border-[rgba(187,128,255,0.4)]' :
                                                      'bg-[rgba(88,166,255,0.1)] text-[#79c0ff] border border-[rgba(88,166,255,0.2)]'
                                                    }`}>
                                                      {(s.role_type || s.sensor_role_type || 'primary').replace('_', ' ')}
                                                    </span>
                                                    <span className="text-[#e6edf3]">{s.condition_detected || s.error_type}</span>
                                                  </div>
                                                </td>
                                                <td className="py-2 px-2 whitespace-nowrap">
                                                  {s.interval_available && s.fault_start ? (
                                                    <span className="text-[#fafafa] font-mono text-[11px]">
                                                      {s.fault_start.replace('T', ' ')} → {s.fault_end ? s.fault_end.replace('T', ' ') : 'Present'}
                                                    </span>
                                                  ) : (
                                                    <span className="text-[#8b949e] italic text-[11px]">
                                                      Individual sensor interval unavailable
                                                    </span>
                                                  )}
                                                  {s.interval_note && (
                                                    <div className="text-[10px] text-[#8b949e] italic">{s.interval_note}</div>
                                                  )}
                                                </td>
                                                <td className="py-2 px-2 whitespace-nowrap">
                                                  {s.interval_available && s.duration_hours !== null && s.duration_hours !== undefined ? (
                                                    <span className="text-[#ff7b72] font-bold">
                                                      {s.duration_hours.toFixed(2)} hrs
                                                    </span>
                                                  ) : (
                                                    <span className="text-[#8b949e]">--</span>
                                                  )}
                                                </td>
                                                <td className="py-2 px-2 text-right whitespace-nowrap">
                                                  {s.observed_value !== null && s.observed_value !== undefined ? (
                                                    <div>
                                                      <span className="text-[#fafafa] font-bold">
                                                        {typeof s.observed_value === 'number' ? s.observed_value.toFixed(2) : s.observed_value}
                                                      </span>
                                                      {s.engineering_unit && (
                                                        <span className="text-[#8b949e] ml-1 text-[11px]">{s.engineering_unit}</span>
                                                      )}
                                                      {s.expected_range && (
                                                        <div className="text-[10px] text-[#8b949e]">Range: {s.expected_range}</div>
                                                      )}
                                                    </div>
                                                  ) : (
                                                    <span className="text-[#8b949e]">--</span>
                                                  )}
                                                </td>
                                              </tr>
                                            ))}
                                          </tbody>
                                        </table>
                                      </div>
                                    )}
                                  </div>
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Inspect fault selectbox matching st.selectbox("Inspect fault", ...) */}
            {filteredFindings.length > 0 && (
              <div className="space-y-1">
                <label className="text-xs font-medium text-[#a3a8b8] block">Inspect fault</label>
                <select
                  id="inspect-fault-select"
                  value={selectedRuleId || ''}
                  onChange={(e) => setSelectedRuleId(e.target.value)}
                  className="w-full st-input cursor-pointer font-sans text-xs"
                >
                  {filteredFindings.map((f) => (
                    <option key={f.rule_id} value={f.rule_id}>
                      {f.display_label} ({f.total_duration_hours.toFixed(1)} hrs)
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Diagnostic Insight 2-Column Panel matching st.columns(2) */}
            {selectedDetail && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
                {/* Left Column: Evidence, Sources, Basis */}
                <div className="space-y-3">
                  <div className="st-alert-error text-sm">
                    <strong className="block font-mono">
                      [{selectedDetail.rule_id}] {selectedDetail.severity}: {selectedDetail.title} (Equipment:{' '}
                      {selectedDetail.equipment_id || effectiveEquipmentId})
                    </strong>
                  </div>

                  <p className="text-xs text-[#a3a8b8]">
                    Diagnostic Confidence:{' '}
                    <strong className="text-[#fafafa]">
                      {selectedDetail.evidence?.[0]?.confidence || 'CONFIRMED'}
                    </strong>{' '}
                    | Total Duration:{' '}
                    <strong className="text-[#fafafa]">
                      {selectedDetail.total_fault_hours.toFixed(1)} hrs
                    </strong>{' '}
                    across{' '}
                    <strong className="text-[#fafafa]">
                      {selectedDetail.episodes?.length || 1} episode(s)
                    </strong>
                  </p>

                  <div>
                    <h4 className="text-sm font-bold text-[#fafafa] mb-1">Evidence</h4>
                    <p className="text-xs text-[#fafafa] leading-relaxed">
                      {selectedDetail.evidence?.[0]?.evidence_text || selectedDetail.description}
                    </p>
                  </div>

                  {selectedDetail.associated_roles && selectedDetail.associated_roles.length > 0 && (
                    <p className="text-xs text-[#a3a8b8]">
                      <strong className="text-[#fafafa]">Evidence Sources</strong>:{' '}
                      <code className="text-[#58a6ff] font-mono bg-[#262730] px-1.5 py-0.5 rounded border border-[rgba(250,250,250,0.12)]">
                        history.parquet ({selectedDetail.associated_roles.join(', ')})
                      </code>
                    </p>
                  )}

                  <p className="text-xs text-[#a3a8b8] italic">
                    Diagnostic Basis: Continuous physical telemetry evaluation against official Open-FDD SQL rules
                  </p>
                </div>

                {/* Right Column: Possible causes & Recommended checks */}
                <div className="space-y-3">
                  <div>
                    <h4 className="text-sm font-bold text-[#fafafa] mb-1">Possible causes</h4>
                    <ul className="space-y-1 text-xs text-[#fafafa]">
                      {selectedDetail.possible_causes && selectedDetail.possible_causes.length > 0 ? (
                        selectedDetail.possible_causes.map((c, i) => (
                          <li key={i} className="flex items-start gap-1.5">
                            <span className="text-[#a3a8b8]">•</span>
                            <span>{c}</span>
                          </li>
                        ))
                      ) : (
                        <li className="text-[#a3a8b8] italic">No specific causes cataloged</li>
                      )}
                    </ul>
                  </div>

                  <div>
                    <h4 className="text-sm font-bold text-[#fafafa] mb-1">Recommended checks</h4>
                    <ul className="space-y-1 text-xs text-[#fafafa]">
                      {selectedDetail.recommended_checks && selectedDetail.recommended_checks.length > 0 ? (
                        selectedDetail.recommended_checks.map((chk, i) => (
                          <li key={i} className="flex items-start gap-1.5">
                            <span className="text-[#a3a8b8]">•</span>
                            <span>{chk}</span>
                          </li>
                        ))
                      ) : (
                        <li className="text-[#a3a8b8] italic">No specific checks cataloged</li>
                      )}
                    </ul>
                  </div>
                </div>
              </div>
            )}

            {/* Associated Sensors Breakdown for Inspected Fault */}
            {selectedDetail && (
              <div className="st-expander mt-3">
                <div className="p-3 bg-[#1e2129] rounded-lg border border-[rgba(250,250,250,0.12)]">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[rgba(250,250,250,0.08)] pb-2.5 mb-3">
                    <div className="flex items-center gap-2">
                      <Activity className="w-4 h-4 text-[#58a6ff]" />
                      <h4 className="text-sm font-semibold text-[#fafafa] font-mono">
                        Associated Sensors & Telemetry Points ({inspectedSensors.length} attributed)
                      </h4>
                    </div>
                    <span className="text-[11px] text-[#a3a8b8] font-mono">
                      Rule: <strong className="text-[#58a6ff]">{selectedDetail.rule_id}</strong> | Equipment: <strong className="text-[#fafafa]">{effectiveEquipmentId}</strong>
                    </span>
                  </div>

                  {inspectedSensors.length === 0 ? (
                    <div className="text-xs text-[#a3a8b8] italic p-3 bg-[#161b22] rounded border border-[rgba(250,250,250,0.08)] flex items-center gap-2">
                      <Info className="w-4 h-4 text-[#a3a8b8] shrink-0" />
                      <span>Sensor attribution unavailable: Equipment-level fault without isolated single-sensor telemetry point.</span>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                      {inspectedSensors.map((s, idx) => (
                        <div key={`${s.canonical_role}_${idx}`} className="bg-[#161b22] border border-[rgba(250,250,250,0.1)] rounded p-3 space-y-2">
                          <div className="flex items-start justify-between gap-1">
                            <div>
                              <h5 className="text-xs font-bold text-[#fafafa] font-sans">{s.sensor_name || s.canonical_role}</h5>
                              <span className="text-[10px] font-mono text-[#58a6ff]">{s.canonical_role}</span>
                            </div>
                            <span className={`px-1.5 py-0.5 rounded text-[9px] font-mono uppercase font-semibold ${
                              s.role_type === 'primary' ? 'bg-[rgba(255,75,75,0.15)] text-[#ff7b72] border border-[#ff4b4b]' :
                              s.role_type === 'reference_setpoint' ? 'bg-[rgba(210,153,34,0.15)] text-[#d29922] border border-[rgba(210,153,34,0.4)]' :
                              s.role_type === 'control_command' ? 'bg-[rgba(187,128,255,0.15)] text-[#d2a8ff] border border-[rgba(187,128,255,0.4)]' :
                              'bg-[rgba(88,166,255,0.1)] text-[#79c0ff] border border-[rgba(88,166,255,0.2)]'
                            }`}>
                              {(s.role_type || s.sensor_role_type || 'primary').replace('_', ' ')}
                            </span>
                          </div>
                          <div className="text-[11px] font-mono text-[#a3a8b8] space-y-1 border-t border-[rgba(250,250,250,0.06)] pt-1.5">
                            <div className="flex justify-between">
                              <span>Original CSV:</span>
                              <code className="text-[#7ee787] bg-[#21262d] px-1 py-0.5 rounded">{s.original_column || '—'}</code>
                            </div>
                            {s.observed_value !== null && s.observed_value !== undefined && (
                              <div className="flex justify-between">
                                <span>Observed:</span>
                                <span className="text-[#fafafa] font-bold">
                                  {typeof s.observed_value === 'number' ? s.observed_value.toFixed(2) : s.observed_value} {s.engineering_unit || ''}
                                </span>
                              </div>
                            )}
                            {s.expected_range && (
                              <div className="flex justify-between">
                                <span>Expected Range:</span>
                                <span className="text-[#fafafa]">{s.expected_range}</span>
                              </div>
                            )}
                            <div className="flex flex-col gap-0.5 pt-1 border-t border-[rgba(250,250,250,0.05)]">
                              <span className="text-[10px] text-[#a3a8b8]">Condition:</span>
                              <span className="text-xs text-[#fafafa] font-sans">{s.condition_detected}</span>
                            </div>
                            <div className="flex flex-col gap-0.5 pt-1">
                              <span className="text-[10px] text-[#a3a8b8]">Fault Interval:</span>
                              {s.interval_available && s.fault_start ? (
                                <span className="text-[10px] text-[#fafafa] font-mono">
                                  {s.fault_start.replace('T', ' ')} → {s.fault_end ? s.fault_end.replace('T', ' ') : 'Present'}
                                  {s.duration_hours !== null && s.duration_hours !== undefined ? ` (${s.duration_hours.toFixed(1)} hrs)` : ''}
                                </span>
                              ) : (
                                <span className="text-[10px] text-[#8b949e] italic">
                                  Individual sensor interval unavailable
                                </span>
                              )}
                              {s.interval_note && (
                                <span className="text-[9px] text-[#8b949e] italic">{s.interval_note}</span>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Contiguous Fault Episodes Expander matching st.expander(...) */}
            {selectedDetail && selectedDetail.episodes && selectedDetail.episodes.length > 0 && (
              <div className="st-expander mt-3">
                <button
                  type="button"
                  id="episodes-toggle"
                  onClick={() => setIsEpisodesExpanded((prev) => !prev)}
                  className="st-expander-header w-full"
                >
                  <span className="text-sm font-medium text-[#fafafa]">
                    Contiguous Fault Episodes ({selectedDetail.episodes.length} active streaks)
                  </span>
                  <span className="text-[#a3a8b8] text-xs">
                    {isEpisodesExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </span>
                </button>
                {isEpisodesExpanded && (
                  <div className="p-3 bg-[#1e2129]">
                    <div className="st-dataframe-container">
                      <table className="st-dataframe-table font-mono text-xs">
                        <thead>
                          <tr>
                            <th>Episode Start</th>
                            <th>Episode End</th>
                            <th>Fault Records</th>
                            <th>Duration (Hours)</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selectedDetail.episodes.map((ep, i) => (
                            <tr key={`${ep.episode_id || `${ep.start}_${ep.end}`}_${i}`}>
                              <td>{ep.start}</td>
                              <td>{ep.end}</td>
                              <td>{ep.samples}</td>
                              <td className="text-[#ff7b72] font-bold">
                                {ep.duration_hours.toFixed(2)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Related Telemetry Trend & Active Period Highlight Graph */}
            {ruleGraphData && (
              <div className="space-y-2 pt-2">
                <h4 className="text-xs font-semibold text-[#fafafa] uppercase tracking-wider font-mono">
                  Related Telemetry Trend & Active Period Highlight ({effectiveEquipmentId} — [{selectedRuleId}])
                </h4>
                <TelemetryGraph data={ruleGraphData} height={340} />
              </div>
            )}
          </div>
        )}

        {/* TAB 2: AIR TEMPERATURES */}
        {activeTab === 'temperature' && (
          <div>
            {tempGraphData ? (
              <div className="space-y-2">
                <h4 className="text-xs font-semibold text-[#fafafa] font-mono">
                  Temperature Trends — {effectiveEquipmentId}
                </h4>
                <TelemetryGraph data={tempGraphData} height={380} />
              </div>
            ) : (
              <div className="text-xs text-[#a3a8b8] py-12 text-center font-mono">
                Loading temperature dynamics telemetry...
              </div>
            )}
          </div>
        )}

        {/* TAB 3: AIRSIDE */}
        {activeTab === 'airside' && (
          <div className="space-y-4">
            {airsideGraphData ? (
              <div className="space-y-4">
                <div className="space-y-2">
                  <h4 className="text-xs font-semibold text-[#fafafa] font-mono">
                    Airside Trends — {effectiveEquipmentId}
                  </h4>
                  <TelemetryGraph data={airsideGraphData} height={380} />
                </div>

                {/* Airside Telemetry Data Table matching Open-FDD standard */}
                {airsideCols.length > 0 && normalizedRecords.length > 0 && (
                  <div className="space-y-2 pt-2">
                    <span className="text-xs font-semibold text-[#fafafa] block font-mono">
                      Airside Telemetry Data ({airsideCols.length} channels)
                    </span>
                    <div className="st-dataframe-container max-h-56 overflow-auto">
                      <table className="st-dataframe-table font-mono text-xs">
                        <thead>
                          <tr>
                            {airsideCols.map((col, idx) => (
                              <th key={idx}>{col}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {normalizedRecords.slice(0, 50).map((row, rIdx) => (
                            <tr key={rIdx}>
                              {airsideCols.map((col, cIdx) => (
                                <td key={cIdx}>
                                  {row[col] !== null && row[col] !== undefined
                                    ? typeof row[col] === 'number'
                                      ? row[col].toFixed(2)
                                      : String(row[col])
                                    : '—'}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-xs text-[#a3a8b8] py-12 text-center font-mono">
                Loading airside and duct static telemetry...
              </div>
            )}
          </div>
        )}

        {/* TAB 4: CHILLED WATER */}
        {activeTab === 'chw' && (
          <div>
            {chwGraphData ? (
              <div className="space-y-2">
                <h4 className="text-xs font-semibold text-[#fafafa] font-mono">
                  Chilled Water Trends — {effectiveEquipmentId}
                </h4>
                <TelemetryGraph data={chwGraphData} height={380} />
              </div>
            ) : (
              <div className="text-xs text-[#a3a8b8] py-12 text-center font-mono">
                Loading hydronic / chilled water telemetry...
              </div>
            )}
          </div>
        )}
      </div>

      {/* Normalized Sensor Data Download Action */}
      <div className="pt-6 border-t border-[rgba(250,250,250,0.12)] flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-0.5">
          <h3 className="text-sm font-semibold text-[#fafafa] flex items-center gap-2 font-mono">
            <Table className="w-4 h-4 text-[#58a6ff]" />
            Normalized Sensor Data ({effectiveEquipmentId})
          </h3>
          <p className="text-xs text-[#a3a8b8]">
            Canonical normalized telemetry partitioned for equipment {effectiveEquipmentId}.
          </p>
        </div>

        <a
          href={getNormalizedDataDownloadUrl(
            effectiveEquipmentId,
            buildingId
          )}
          download
          id="download-normalized-data-btn"
          className="st-button-secondary text-xs px-4 py-2 inline-flex items-center gap-2 font-semibold shadow-sm hover:text-[#58a6ff] hover:border-[#58a6ff] transition-colors"
        >
          <Download className="w-3.5 h-3.5" />
          Download Normalized Data
        </a>
      </div>

      {/* Result Validation & Verification Section */}
      <div className="pt-2">
        <ResultValidationSection equipmentId={effectiveEquipmentId} buildingId={buildingId} />
      </div>
    </div>
  );
};
