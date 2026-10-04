import React, { useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';
import { DatasetDetailResponse } from '../types/api';

interface DataQualitySectionProps {
  dataset: DatasetDetailResponse;
}

export const DataQualitySection: React.FC<DataQualitySectionProps> = ({ dataset }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [showProfileTable, setShowProfileTable] = useState(false);
  const pf = dataset.preflight;

  // Calculate Data Quality Score (0-100)
  let qualityScore = 100;
  if (!pf.timestamp_valid) qualityScore -= 30;
  if (pf.duplicate_timestamps > 0) qualityScore -= 10;
  if (pf.non_monotonic_timestamps > 0) qualityScore -= 15;
  if (pf.warnings.length > 0) qualityScore -= Math.min(20, pf.warnings.length * 5);
  qualityScore = Math.max(50, qualityScore);

  const isGood = qualityScore >= 80 && pf.timestamp_valid && pf.errors.length === 0;

  const formatSampling = (secs: number | null | undefined) => {
    if (!secs) return 'Unknown';
    if (secs >= 60) {
      const mins = (secs / 60).toFixed(1);
      return `${mins} min`;
    }
    return `${secs.toFixed(1)} s`;
  };

  const missingPercent =
    dataset.row_count > 0 && pf.missing_timestamps
      ? ((pf.missing_timestamps / dataset.row_count) * 100).toFixed(1)
      : '0.0';

  return (
    <div className="st-expander font-sans select-none shadow-sm">
      {/* Streamlit st.expander header */}
      <button
        type="button"
        id="data-quality-toggle"
        onClick={() => setIsOpen(!isOpen)}
        className="st-expander-header w-full border-b border-[rgba(250,250,250,0.12)]"
      >
        <span className="text-sm font-semibold text-[#fafafa] flex flex-wrap items-center gap-2">
          Input Data Quality &amp; Validation
          <span
            className={`text-xs px-2 py-0.5 rounded-sm font-mono ${
              isGood
                ? 'bg-[rgba(9,171,59,0.1)] text-[#09ab3b] border border-[rgba(9,171,59,0.3)]'
                : 'bg-[rgba(255,164,33,0.1)] text-[#e2660c] border border-[rgba(255,164,33,0.3)]'
            }`}
          >
            {qualityScore}% Quality
          </span>
        </span>
        <span className="text-[#808495] text-xs">
          {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </span>
      </button>

      {isOpen && (
        <div className="p-4 space-y-4 bg-[#1e2129]">
          {/* Streamlit st.columns(5) metric cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
            <div className="st-metric-card">
              <div className="st-metric-label">Data Quality Score</div>
              <div
                className={`st-metric-value ${
                  isGood ? 'text-[#3fb950]' : 'text-[#f0883e]'
                }`}
              >
                {qualityScore}/100
              </div>
              <div className={isGood ? 'st-metric-delta-pos' : 'st-metric-delta-neg'}>
                {isGood ? 'Good' : 'Marginal'}
              </div>
            </div>

            <div className="st-metric-card">
              <div className="st-metric-label">Valid Timestamps</div>
              <div className="st-metric-value text-[#fafafa] font-mono">
                {pf.timestamp_valid ? '100.0%' : '0.0%'}
              </div>
            </div>

            <div className="st-metric-card">
              <div className="st-metric-label">Duplicate Rows</div>
              <div className="st-metric-value text-[#fafafa] font-mono">{pf.duplicate_timestamps}</div>
            </div>

            <div className="st-metric-card">
              <div className="st-metric-label">Overall Missing</div>
              <div className="st-metric-value text-[#fafafa] font-mono">{missingPercent}%</div>
            </div>

            <div className="st-metric-card">
              <div className="st-metric-label">Sampling Interval</div>
              <div className="st-metric-value text-[#fafafa] font-mono">{formatSampling(pf.median_sampling_seconds)}</div>
            </div>
          </div>

          {/* Detected Quality Warnings matching st.warning */}
          {pf.warnings.length > 0 && (
            <div className="space-y-2 pt-1">
              <h5 className="text-xs font-semibold text-[#fafafa] uppercase tracking-wide">
                Detected Quality Warnings
              </h5>
              {pf.warnings.map((w, idx) => (
                <div key={idx} className="st-alert-warning text-xs flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 shrink-0 text-[#ffa421]" />
                  <span>{w}</span>
                </div>
              ))}
            </div>
          )}

          {/* Column Profiling DataFrame matching st.dataframe */}
          <div className="space-y-1.5 pt-1">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-[#a3a8b8]">Telemetry Field Profile</span>
              <button
                type="button"
                onClick={() => setShowProfileTable(!showProfileTable)}
                className="text-xs text-[#ff4b4b] hover:underline cursor-pointer font-medium"
              >
                {showProfileTable ? 'Hide profile table' : 'Show column profile table'}
              </button>
            </div>

            {showProfileTable && (
              <div className="st-dataframe-container">
                <table className="st-dataframe-table font-mono">
                  <thead>
                    <tr>
                      <th>Column</th>
                      <th>Category</th>
                      <th>Source Type</th>
                      <th>Unit</th>
                      <th>Role</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(dataset.columns || []).map((col, i) => (
                      <tr key={i}>
                        <td className="font-semibold text-[#fafafa]">{col.source_column}</td>
                        <td className="text-[#a3a8b8]">{col.column_category || '--'}</td>
                        <td>{col.source_dtype ?? '--'}</td>
                        <td>{col.canonical_unit || col.unit || '--'}</td>
                        <td className="text-[#58a6ff] font-medium">{col.canonical_role || '--'}</td>
                        <td>
                          {col.mapped ? (
                            <span className="text-[#3fb950] font-medium">✓ Mapped</span>
                          ) : (
                            <span className="text-[#a3a8b8]">Unmapped</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
