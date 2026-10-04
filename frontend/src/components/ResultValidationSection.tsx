import React, { useState, useEffect } from 'react';
import { AlertCircle, ChevronDown, ChevronUp, Loader2, ShieldCheck } from 'lucide-react';
import { ResultValidationReport } from '../types/api';
import { getResultValidationReport } from '../services/api';

interface Props {
  equipmentId: string;
  buildingId?: string | null;
  report?: ResultValidationReport | null;
}

export const ResultValidationSection: React.FC<Props> = ({
  equipmentId,
  buildingId,
  report: initialReport,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<'rules' | 'findings' | 'reconciliation'>('rules');
  const [report, setReport] = useState<ResultValidationReport | null>(initialReport || null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialReport) {
      setReport(initialReport);
      return;
    }
    if (!equipmentId) return;

    let isMounted = true;
    const loadReport = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const res = await getResultValidationReport(equipmentId, buildingId);
        if (isMounted) setReport(res);
      } catch (err: any) {
        if (isMounted) setError(err.message || 'Failed to load validation report');
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    loadReport();
    return () => {
      isMounted = false;
    };
  }, [equipmentId, buildingId, initialReport]);

  const overallStatus = report?.overall_status || 'VALID';
  const isPassing = overallStatus === 'VALID';
  const isWarning = overallStatus === 'WARNING';

  return (
    <div className="st-expander font-sans select-none shadow-sm">
      {/* Streamlit st.expander header */}
      <button
        type="button"
        id="result-validation-toggle"
        onClick={() => setIsOpen(!isOpen)}
        className="st-expander-header w-full border-b border-[rgba(250,250,250,0.12)]"
      >
        <span className="text-sm font-semibold text-[#fafafa] flex flex-wrap items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-[#ff4b4b]" />
          FDD Result &amp; Evidence Validation
          <span
            className={`text-xs px-2 py-0.5 rounded-sm font-mono ${
              isPassing
                ? 'bg-[rgba(9,171,59,0.15)] text-[#56d364] border border-[rgba(9,171,59,0.3)]'
                : isWarning
                ? 'bg-[rgba(255,164,33,0.15)] text-[#e3b341] border border-[rgba(255,164,33,0.3)]'
                : 'bg-[rgba(255,75,75,0.15)] text-[#ff7b72] border border-[rgba(255,75,75,0.3)]'
            }`}
          >
            {overallStatus}
          </span>
        </span>
        <span className="text-[#a3a8b8] text-xs">
          {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </span>
      </button>

      {isOpen && (
        <div className="p-4 space-y-4 bg-[#1e2129]">
          {isLoading ? (
            <div className="flex items-center justify-center gap-2 text-xs text-[#a3a8b8] py-8 font-mono">
              <Loader2 className="w-4 h-4 animate-spin text-[#1c83e1]" />
              <span>Auditing rule execution, evidence integrity &amp; reconciliation...</span>
            </div>
          ) : error ? (
            <div className="st-alert-error text-xs font-mono">{error}</div>
          ) : !report ? (
            <div className="text-xs text-[#a3a8b8] py-4 text-center font-mono">
              No validation report available. Run FDD to audit execution and evidence.
            </div>
          ) : (
            <>
              {/* 5 Metric Cards matching vc1, vc2, vc3, vc4, vc5 = st.columns(5) */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                <div className="st-metric-card">
                  <div className="st-metric-label">Validation Status</div>
                  <div
                    className={`st-metric-value text-base font-bold font-mono ${
                      isPassing ? 'text-[#3fb950]' : isWarning ? 'text-[#f0883e]' : 'text-[#ff4b4b]'
                    }`}
                  >
                    {report.overall_status}
                  </div>
                </div>

                <div className="st-metric-card">
                  <div className="st-metric-label">Rules Validated</div>
                  <div className="st-metric-value font-mono text-[#fafafa]">
                    {report.rules_valid_count}/{report.rules_validated_count}
                  </div>
                </div>

                <div className="st-metric-card">
                  <div className="st-metric-label">Valid Findings</div>
                  <div className="st-metric-value font-mono text-[#fafafa]">
                    {report.findings_valid_count}/{report.findings_validated_count}
                  </div>
                </div>

                <div className="st-metric-card">
                  <div className="st-metric-label">Evidence Issues</div>
                  <div
                    className={`st-metric-value font-mono ${
                      report.findings_with_evidence_issues > 0 ? 'text-[#f0883e]' : 'text-[#3fb950]'
                    }`}
                  >
                    {report.findings_with_evidence_issues}
                  </div>
                </div>

                <div className="st-metric-card">
                  <div className="st-metric-label">Reconciliation Errors</div>
                  <div
                    className={`st-metric-value font-mono ${
                      report.reconciliation_errors_count > 0 ? 'text-[#ff4b4b]' : 'text-[#3fb950]'
                    }`}
                  >
                    {report.reconciliation_errors_count}
                  </div>
                </div>
              </div>

              {/* Detected Warnings Banner */}
              {report.issues_summary && report.issues_summary.length > 0 && (
                <div className="space-y-1 pt-1">
                  <div className="text-xs font-semibold text-[#fafafa] flex items-center gap-1.5">
                    <AlertCircle className="w-3.5 h-3.5 text-[#ffa421]" />
                    <span>Detected Result &amp; Finding Warnings ({report.issues_summary.length})</span>
                  </div>
                  <div className="space-y-1 max-h-36 overflow-y-auto">
                    {report.issues_summary.map((iss, i) => (
                      <div key={i} className="st-alert-warning text-[11px] py-1 px-2.5 font-mono">
                        {iss}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 3 Tabs matching vtab1, vtab2, vtab3 = st.tabs(...) */}
              <div className="pt-2">
                <div className="flex border-b border-[rgba(250,250,250,0.12)] text-xs">
                  {[
                    { id: 'rules', label: 'Rule Results Audit' },
                    { id: 'findings', label: 'Finding & Evidence Quality' },
                    { id: 'reconciliation', label: 'Rule ↔ Finding Reconciliation' },
                  ].map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => setActiveTab(t.id as any)}
                      className={`st-tab-btn text-xs py-1.5 px-3 ${
                        activeTab === t.id ? 'st-tab-btn-active' : ''
                      }`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>

                <div className="pt-3">
                  {/* TAB 1: Rule Results Audit */}
                  {activeTab === 'rules' && (
                    <div className="st-dataframe-container max-h-64 overflow-y-auto">
                      <table className="st-dataframe-table font-mono text-xs">
                        <thead>
                          <tr>
                            <th>Rule ID</th>
                            <th>Rule Name</th>
                            <th>Status</th>
                            <th>Valid</th>
                            <th>Missing Roles</th>
                            <th>Issues</th>
                          </tr>
                        </thead>
                        <tbody>
                          {report.rules_table.map((r, i) => (
                            <tr key={i}>
                              <td className="text-[#58a6ff] font-bold">{r['Rule ID']}</td>
                              <td className="text-[#fafafa] font-sans">{r['Rule Name']}</td>
                              <td>{r['Status']}</td>
                              <td className={r['Valid'] === 'Yes' ? 'text-[#3fb950] font-medium' : 'text-[#ff4b4b] font-medium'}>
                                {r['Valid']}
                              </td>
                              <td className="text-[#a3a8b8]">{r['Missing Roles']}</td>
                              <td className={r['Issues'] === 'None' ? 'text-[#a3a8b8]' : 'text-[#f0883e]'}>
                                {r['Issues']}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {/* TAB 2: Finding & Evidence Quality */}
                  {activeTab === 'findings' && (
                    <div className="st-dataframe-container max-h-64 overflow-auto">
                      {report.findings_table.length === 0 ? (
                        <div className="text-xs text-[#a3a8b8] py-4 text-center font-mono">
                          No findings generated to inspect.
                        </div>
                      ) : (
                        <table className="st-dataframe-table font-mono text-xs">
                          <thead>
                            <tr>
                              <th>Timestamp</th>
                              <th>Equipment</th>
                              <th>Fault Code</th>
                              <th>Severity</th>
                              <th>Persistence</th>
                              <th>Evidence Status</th>
                              <th>Duplicate</th>
                              <th>Issues</th>
                            </tr>
                          </thead>
                          <tbody>
                            {report.findings_table.map((f, i) => (
                              <tr key={i}>
                                <td>{f['Timestamp']}</td>
                                <td>{f['Equipment']}</td>
                                <td className="text-[#58a6ff] font-bold">{f['Fault Code']}</td>
                                <td>{f['Severity']}</td>
                                <td>{f['Persistence']}</td>
                                <td
                                  className={
                                    f['Evidence Status'] === 'VALID'
                                      ? 'text-[#3fb950] font-medium'
                                      : 'text-[#f0883e] font-medium'
                                  }
                                >
                                  {f['Evidence Status']}
                                </td>
                                <td>{f['Duplicate']}</td>
                                <td className={f['Issues'] === 'None' ? 'text-[#a3a8b8]' : 'text-[#ff4b4b]'}>
                                  {f['Issues']}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </div>
                  )}

                  {/* TAB 3: Rule ↔ Finding Reconciliation */}
                  {activeTab === 'reconciliation' && (
                    <div className="st-dataframe-container max-h-64 overflow-auto">
                      <table className="st-dataframe-table font-mono text-xs">
                        <thead>
                          <tr>
                            <th>Rule ID</th>
                            <th>Rule Name</th>
                            <th>Official Status</th>
                            <th>Dashboard Findings</th>
                            <th>Reconciliation</th>
                          </tr>
                        </thead>
                        <tbody>
                          {report.reconciliation_table.map((rec, i) => (
                            <tr key={i}>
                              <td className="text-[#58a6ff] font-bold">{rec['Rule ID']}</td>
                              <td className="text-[#fafafa] font-sans">{rec['Rule Name']}</td>
                              <td>{rec['Official Status']}</td>
                              <td>{rec['Dashboard Findings']}</td>
                              <td
                                className={
                                  rec['Reconciliation'] === 'MATCH'
                                    ? 'text-[#3fb950] font-semibold'
                                    : 'text-[#ff4b4b] font-semibold'
                                }
                              >
                                {rec['Reconciliation']}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};
