import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { DatasetDetailResponse, RuleDefinition, FDDExecutionSummary } from '../types/api';
import { listRules } from '../services/api';

interface Props {
  dataset: DatasetDetailResponse;
  executionSummary?: FDDExecutionSummary | null;
}

export const RuleReadinessSection: React.FC<Props> = ({ dataset, executionSummary }) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
  const [allRules, setAllRules] = useState<RuleDefinition[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchRules = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const rules = await listRules();
        setAllRules(rules);
      } catch (err: any) {
        setError(err.message || 'Failed to load rule catalog');
      } finally {
        setIsLoading(false);
      }
    };
    fetchRules();
  }, []);

  // Map of active canonical roles available in current dataset
  const availableRolesSet = new Set<string>();
  for (const col of dataset.columns) {
    if (col.mapped && col.canonical_role) {
      availableRolesSet.add(col.canonical_role.toLowerCase());
    }
  }

  // Create lookup for execution results if FDD was already run
  const execResultMap = new Map<string, { status: string; faultHours: number; missingRoles: string[] }>();
  if (executionSummary) {
    for (const res of executionSummary.results) {
      let fh = 0;
      for (const f of res.findings) {
        if (f.fault_detected) fh += f.fault_hours || 0;
      }
      execResultMap.set(res.rule_id.toUpperCase(), {
        status: res.status,
        faultHours: fh,
        missingRoles: res.missing_roles,
      });
    }
  }

  // Calculate dynamic counts
  const totalRules = allRules.length;
  
  // Applicable to AHU: explicitly tagged "ahu" or untagged (broad)
  const ahuApplicableRules = allRules.filter(
    (r) => !r.equipment_kinds || r.equipment_kinds.length === 0 || r.equipment_kinds.map((k) => k.toLowerCase()).includes('ahu')
  );
  const ahuApplicableCount = ahuApplicableRules.length;
  const notApplicableCount = allRules.length - ahuApplicableCount;

  // For each AHU applicable rule, check whether required roles are available
  const applicableRows = ahuApplicableRules.map((rule) => {
    const reqRoles = (rule.required_roles || []).map((r) => r.toLowerCase());
    const missing = reqRoles.filter((r) => !availableRolesSet.has(r));
    const isReady = missing.length === 0;

    const exec = execResultMap.get(rule.rule_id.toUpperCase());

    let finalStatus: 'READY' | 'SKIPPED' | 'FAULT' | 'NO_FAULT' | 'FAILED' | 'NON_APPLICABLE' = isReady ? 'READY' : 'SKIPPED';
    let reason = isReady ? 'All required telemetry mapped' : `Missing required role(s): ${missing.join(', ')}`;

    if (exec) {
      if (exec.status === 'FAULT_DETECTED') {
        finalStatus = 'FAULT';
        reason = `Active fault detected (${exec.faultHours.toFixed(1)} hrs)`;
      } else if (exec.status === 'NO_FAULT' || exec.status === 'SUCCESS') {
        finalStatus = 'NO_FAULT';
        reason = 'Evaluated: Normal operation (No fault)';
      } else if (exec.status === 'SKIPPED_MISSING_ROLES') {
        finalStatus = 'SKIPPED';
        reason = `Skipped: Missing required role(s): ${(exec.missingRoles && exec.missingRoles.length > 0 ? exec.missingRoles : missing).join(', ')}`;
      } else if (exec.status === 'ERROR') {
        finalStatus = 'FAILED';
        reason = 'Execution error';
      }
    }

    return {
      rule_id: rule.rule_id,
      description: rule.description || rule.rule_id,
      equipment_kinds: rule.equipment_kinds && rule.equipment_kinds.length > 0 ? rule.equipment_kinds.join(', ') : 'Broad',
      required_roles: reqRoles,
      missing_roles: missing,
      is_ready: isReady,
      final_status: finalStatus,
      reason,
    };
  });

  const nonAhuRules = allRules.filter(
    (r) => r.equipment_kinds && r.equipment_kinds.length > 0 && !r.equipment_kinds.map((k) => k.toLowerCase()).includes('ahu')
  );

  const nonApplicableRows = nonAhuRules.map((rule) => ({
    rule_id: rule.rule_id,
    description: rule.description || rule.rule_id,
    equipment_kinds: rule.equipment_kinds.join(', '),
    required_roles: (rule.required_roles || []).map((r) => r.toLowerCase()),
    missing_roles: [],
    is_ready: false,
    final_status: 'NON_APPLICABLE' as const,
    reason: `Not applicable to AHU equipment (Target: ${rule.equipment_kinds.join(', ')})`,
  }));

  const evaluatedRows = [...applicableRows, ...nonApplicableRows];

  // Dynamic status counts based on actual execution or readiness
  let rulesRunCount = 0;
  let rulesNotRunCount = 0;
  let faultedCount = 0;

  if (executionSummary) {
    rulesRunCount = executionSummary.rules_succeeded;
    rulesNotRunCount = executionSummary.rules_skipped;
    faultedCount = executionSummary.rules_faulted;
  } else {
    rulesRunCount = applicableRows.filter((r) => r.is_ready).length;
    rulesNotRunCount = ahuApplicableCount - rulesRunCount;
    faultedCount = 0;
  }

  return (
    <div className="st-expander font-sans select-none shadow-sm">
      {/* Streamlit st.expander header */}
      <button
        type="button"
        id="rule-readiness-toggle"
        data-testid="rule-readiness-toggle"
        onClick={() => setIsExpanded(!isExpanded)}
        className="st-expander-header w-full border-b border-[rgba(250,250,250,0.12)]"
      >
        <span className="text-sm font-semibold text-[#fafafa] flex flex-wrap items-center gap-2">
          Official Open-FDD Universal {totalRules > 0 ? `${totalRules}-Rule ` : ''}Catalog Readiness &amp; Subsystem Audit
          <span className="text-xs text-[#58a6ff] font-mono font-medium">
            ({rulesRunCount}/{ahuApplicableCount} ready)
          </span>
        </span>
        <span className="text-[#a3a8b8] text-xs">
          {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </span>
      </button>

      {isExpanded && (
        <div className="p-4 space-y-4 bg-[#1e2129]">
          {isLoading ? (
            <div className="text-xs text-[#a3a8b8] py-4 text-center">
              Loading rule catalog from backend...
            </div>
          ) : error ? (
            <div className="st-alert-error text-xs">{error}</div>
          ) : (
            <>
              {/* Streamlit st.columns(6) metric cards */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 sm:gap-4">
                <div className="st-metric-card">
                  <div className="st-metric-label">Total Catalog Rules</div>
                  <div className="st-metric-value">{totalRules}</div>
                </div>

                <div className="st-metric-card">
                  <div className="st-metric-label">Applicable (AHU)</div>
                  <div className="st-metric-value text-[#58a6ff]">{ahuApplicableCount}</div>
                </div>

                <div className="st-metric-card">
                  <div className="st-metric-label">Not Applicable</div>
                  <div className="st-metric-value text-[#a3a8b8]">{notApplicableCount}</div>
                </div>

                <div className="st-metric-card">
                  <div className="st-metric-label">Executable Rules</div>
                  <div className="st-metric-value text-[#3fb950]">{rulesRunCount}</div>
                </div>

                <div className="st-metric-card">
                  <div className="st-metric-label">Active Faults</div>
                  <div className="st-metric-value text-[#ff4b4b]">{faultedCount}</div>
                </div>

                <div className="st-metric-card">
                  <div className="st-metric-label">Skipped / Missing Telemetry</div>
                  <div className="st-metric-value text-[#f0883e]">{rulesNotRunCount}</div>
                </div>
              </div>

              {/* Rules Table matching st.dataframe */}
              <div className="st-dataframe-container max-h-96">
                <table className="st-dataframe-table font-mono">
                  <thead>
                    <tr>
                      <th>Rule ID</th>
                      <th>Description</th>
                      <th>Subsystem</th>
                      <th>Required Roles</th>
                      <th>Status</th>
                      <th>Execution / Skip Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evaluatedRows.map((r, idx) => (
                      <tr key={idx}>
                        <td className="font-semibold text-[#58a6ff]">{r.rule_id}</td>
                        <td className="max-w-xs truncate text-[#fafafa]" title={r.description}>
                          {r.description}
                        </td>
                        <td className="text-[#a3a8b8]">{r.equipment_kinds}</td>
                        <td>
                          {r.required_roles.length > 0 ? (
                            <div className="flex flex-wrap gap-1">
                              {r.required_roles.map((req, i) => {
                                const isAvail = availableRolesSet.has(req);
                                return (
                                  <span
                                    key={i}
                                    className={`px-1.5 py-0.5 rounded text-[10px] font-mono ${
                                      isAvail
                                        ? 'bg-[rgba(9,171,59,0.1)] text-[#3fb950] border border-[rgba(9,171,59,0.3)]'
                                        : 'bg-[rgba(255,75,75,0.1)] text-[#ff7b72] border border-[rgba(255,75,75,0.3)]'
                                    }`}
                                  >
                                    {req}
                                  </span>
                                );
                              })}
                            </div>
                          ) : (
                            <span className="text-[#a3a8b8] italic">None</span>
                          )}
                        </td>
                        <td>
                          {r.final_status === 'FAULT' && (
                            <span className="text-[#ff4b4b] font-bold">● FAULT</span>
                          )}
                          {r.final_status === 'NO_FAULT' && (
                            <span className="text-[#3fb950] font-semibold">✓ NO FAULT</span>
                          )}
                          {r.final_status === 'READY' && (
                            <span className="text-[#58a6ff] font-semibold">READY</span>
                          )}
                          {r.final_status === 'SKIPPED' && (
                            <span className="text-[#f0883e] font-medium">SKIPPED</span>
                          )}
                          {r.final_status === 'FAILED' && (
                            <span className="text-[#ff4b4b] font-bold">FAILED</span>
                          )}
                          {r.final_status === 'NON_APPLICABLE' && (
                            <span className="text-[#a3a8b8] text-xs">NON-APPLICABLE</span>
                          )}
                        </td>
                        <td className="text-[#a3a8b8] max-w-sm truncate" title={r.reason}>
                          {r.reason}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};
