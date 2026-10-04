import React, { useState } from 'react';
import {
  ChevronDown,
  ChevronUp,
  Search,
  SlidersHorizontal,
} from 'lucide-react';
import { DatasetDetailResponse, ColumnInspection } from '../types/api';

interface CanonicalMappingSectionProps {
  dataset: DatasetDetailResponse;
}

export const CanonicalMappingSection: React.FC<CanonicalMappingSectionProps> = ({ dataset }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [showUnmappedOnly, setShowUnmappedOnly] = useState(false);
  const [isOpen, setIsOpen] = useState(false);

  const columns = dataset.columns || [];
  const totalCount = dataset.column_count || columns.length;
  // Count canonical mapped roles plus recognized temporal index columns classified as MAPPED
  const temporalMappedCount = columns.filter((c) => c.column_category === 'TEMPORAL_METADATA' && !c.mapped).length;
  const mappedCount = (dataset.mapped_column_count || 0) + temporalMappedCount;

  // Unmapped count (excluding metadata handled and temporal metadata mapped)
  const unmappedCount = columns.filter(
    (c) =>
      !c.mapped &&
      c.column_category !== 'TEMPORAL_METADATA' &&
      c.column_category !== 'TOPOLOGY_METADATA' &&
      c.column_category !== 'BENCHMARK_METADATA' &&
      c.column_category !== 'AUXILIARY_BMS'
  ).length;

  const coveragePct = totalCount > 0 ? ((mappedCount / totalCount) * 100).toFixed(1) : '0.0';

  // Filter columns based on search and unmapped toggle
  const filteredColumns = columns.filter((col) => {
    const isMetadata =
      col.column_category === 'TEMPORAL_METADATA' ||
      col.column_category === 'TOPOLOGY_METADATA' ||
      col.column_category === 'BENCHMARK_METADATA' ||
      col.column_category === 'AUXILIARY_BMS';

    if (showUnmappedOnly && (col.mapped || isMetadata)) {
      return false;
    }

    if (searchTerm.trim()) {
      const q = searchTerm.toLowerCase();
      const matchSource = col.source_column.toLowerCase().includes(q);
      const matchRole = (col.canonical_role || '').toLowerCase().includes(q);
      const matchReason = (col.mapping_reason || '').toLowerCase().includes(q);
      if (!matchSource && !matchRole && !matchReason) return false;
    }

    return true;
  });

  const getRoleDisplay = (col: ColumnInspection) => {
    if (col.column_category === 'TEMPORAL_METADATA') {
      return <span className="text-[#0054a3] font-mono">timestamp (Index)</span>;
    }
    if (col.column_category === 'TOPOLOGY_METADATA') {
      return <span className="text-[#0054a3] font-mono">equipment_id (Identifier)</span>;
    }
    if (col.column_category === 'BENCHMARK_METADATA') {
      return <span className="text-[#0054a3] font-mono">{col.source_column} (Benchmark)</span>;
    }
    if (col.column_category === 'AUXILIARY_BMS') {
      return <span className="text-[#808495] font-mono">{col.source_column} (Auxiliary)</span>;
    }
    if (col.mapped && col.canonical_role) {
      return <span className="text-[#0054a3] font-mono font-bold">{col.canonical_role}</span>;
    }
    return (
      <span className="text-[#808495] font-mono italic">
        [Select Role ▾]
      </span>
    );
  };

  const getStatusBadge = (col: ColumnInspection) => {
    if (col.column_category === 'TEMPORAL_METADATA') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider bg-[rgba(9,171,59,0.1)] text-[#09ab3b] border border-[rgba(9,171,59,0.3)]">
          <span className="w-1.5 h-1.5 rounded-full bg-[#09ab3b]" />
          MAPPED
        </span>
      );
    }
    if (
      col.column_category === 'TOPOLOGY_METADATA' ||
      col.column_category === 'BENCHMARK_METADATA' ||
      col.column_category === 'AUXILIARY_BMS'
    ) {
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider bg-[rgba(28,131,225,0.1)] text-[#0054a3] border border-[rgba(28,131,225,0.3)]">
          <span className="w-1.5 h-1.5 rounded-full bg-[#1c83e1]" />
          HANDLED
        </span>
      );
    }
    if (col.mapped) {
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider bg-[rgba(9,171,59,0.1)] text-[#09ab3b] border border-[rgba(9,171,59,0.3)]">
          <span className="w-1.5 h-1.5 rounded-full bg-[#09ab3b]" />
          MAPPED
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider bg-[rgba(255,75,75,0.1)] text-[#bd4043] border border-[rgba(255,75,75,0.3)]">
        <span className="w-1.5 h-1.5 rounded-full bg-[#ff4b4b]" />
        UNMAPPED
      </span>
    );
  };

  const getConfidenceBadge = (col: ColumnInspection) => {
    if (
      col.column_category === 'TEMPORAL_METADATA' ||
      col.column_category === 'TOPOLOGY_METADATA' ||
      col.column_category === 'BENCHMARK_METADATA' ||
      col.column_category === 'AUXILIARY_BMS'
    ) {
      return (
        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold uppercase bg-[rgba(9,171,59,0.1)] text-[#09ab3b] border border-[rgba(9,171,59,0.3)]">
          HIGH
        </span>
      );
    }
    const score = col.mapping_score ?? 0;
    const normalizedScore = score > 1 ? score / 100 : score;
    if (col.mapped && normalizedScore >= 0.7) {
      return (
        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold uppercase bg-[rgba(9,171,59,0.1)] text-[#09ab3b] border border-[rgba(9,171,59,0.3)]">
          HIGH
        </span>
      );
    }
    if (col.mapped && normalizedScore >= 0.4) {
      return (
        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold uppercase bg-[rgba(255,164,33,0.1)] text-[#e2660c] border border-[rgba(255,164,33,0.3)]">
          MED
        </span>
      );
    }
    return (
      <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold uppercase bg-[rgba(255,75,75,0.1)] text-[#bd4043] border border-[rgba(255,75,75,0.3)]">
        LOW
      </span>
    );
  };

  const getUnitDisplay = (col: ColumnInspection) => {
    if (col.column_category === 'TEMPORAL_METADATA' || col.column_category === 'TOPOLOGY_METADATA') {
      return '—';
    }
    return col.unit || '—';
  };

  const getConversionDisplay = (col: ColumnInspection) => {
    if (!col.conversion_required) return <span className="text-[#808495] font-mono">None</span>;
    if (col.unit && col.canonical_unit) {
      return (
        <span className="text-[#e2660c] font-mono text-[11px] font-semibold">
          {col.unit} → {col.canonical_unit}
        </span>
      );
    }
    const u = (col.unit || '').toUpperCase();
    if (u === 'C' || u === '°C' || u === 'DEG C') {
      return <span className="text-[#e2660c] font-mono text-[11px] font-semibold">°C → °F</span>;
    }
    if (u === 'PA' || u === 'PASCALS') {
      return <span className="text-[#e2660c] font-mono text-[11px] font-semibold">Pa → in. w.c.</span>;
    }
    return <span className="text-[#e2660c] font-mono text-[11px] font-semibold">Required</span>;
  };

  const getReasonDisplay = (col: ColumnInspection) => {
    if (col.column_category === 'TEMPORAL_METADATA') {
      return 'Time-series index.';
    }
    if (col.column_category === 'TOPOLOGY_METADATA') {
      return 'Equipment topology identifier.';
    }
    if (col.column_category === 'BENCHMARK_METADATA') {
      return 'Ground truth simulation flag / benchmark metadata.';
    }
    if (col.column_category === 'AUXILIARY_BMS') {
      return 'Auxiliary building management point.';
    }
    if (col.mapping_reason) {
      return col.mapping_reason;
    }
    if (col.mapped) {
      return 'Matched canonical HVAC semantics.';
    }
    return 'Ambiguous telemetry signal.';
  };

  const unmappedColNames = columns
    .filter((c) => !c.mapped && c.column_category !== 'TEMPORAL_METADATA' && c.column_category !== 'TOPOLOGY_METADATA')
    .map((c) => c.source_column);

  return (
    <div className="st-expander font-sans select-none shadow-sm">
      {/* Streamlit st.expander header */}
      <button
        type="button"
        id="canonical-mapping-toggle"
        onClick={() => setIsOpen(!isOpen)}
        className="st-expander-header w-full border-b border-[rgba(250,250,250,0.12)]"
      >
        <span className="text-sm font-semibold text-[#fafafa] flex flex-wrap items-center gap-2">
          Canonical Point Mapping &amp; Telemetry Discovery
          <span className="text-xs text-[#58a6ff] font-mono font-medium">
            ({mappedCount}/{totalCount} mapped • {coveragePct}%)
          </span>
        </span>
        <span className="text-[#a3a8b8] text-xs">
          {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </span>
      </button>

      {isOpen && (
        <div className="p-4 space-y-4 bg-[#1e2129]">
          {/* Streamlit st.columns(4) metric cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
            <div className="st-metric-card">
              <div className="st-metric-label">Total Source Columns</div>
              <div className="st-metric-value">{totalCount}</div>
            </div>

            <div className="st-metric-card">
              <div className="st-metric-label">Mapped Canonical Roles</div>
              <div className="st-metric-value text-[#3fb950]">{mappedCount}</div>
            </div>

            <div className="st-metric-card">
              <div className="st-metric-label">Unmapped Columns</div>
              <div className="st-metric-value text-[#ff4b4b]">{unmappedCount}</div>
            </div>

            <div className="st-metric-card">
              <div className="st-metric-label">Mapping Coverage</div>
              <div className="st-metric-value">{coveragePct}%</div>
            </div>
          </div>

          {/* Search & Filter row */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
            <div className="relative flex-1 w-full sm:max-w-sm">
              <Search className="w-3.5 h-3.5 text-[#808495] absolute left-2.5 top-2.5 pointer-events-none" />
              <input
                type="text"
                placeholder="Filter columns or roles..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full st-input pl-8 text-xs font-sans"
              />
            </div>

            <button
              type="button"
              onClick={() => setShowUnmappedOnly(!showUnmappedOnly)}
              className={`st-button-secondary text-xs px-3 py-1.5 whitespace-nowrap self-start sm:self-auto ${
                showUnmappedOnly ? 'border-[#ff4b4b] text-[#ff4b4b]' : ''
              }`}
            >
              <SlidersHorizontal className="w-3.5 h-3.5" />
              <span>{showUnmappedOnly ? 'Show All Columns' : 'Show Unmapped Only'}</span>
            </button>
          </div>

          {/* Mapping Table matching st.dataframe */}
          <div className="st-dataframe-container">
            <table className="st-dataframe-table font-mono">
              <thead>
                <tr>
                  <th>Source Column</th>
                  <th>Canonical Role</th>
                  <th>Confidence</th>
                  <th>Detected Unit</th>
                  <th>Conversion</th>
                  <th>Status</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {filteredColumns.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-6 text-center text-[#a3a8b8]">
                      No columns match current filter criteria.
                    </td>
                  </tr>
                ) : (
                  filteredColumns.map((col, idx) => (
                    <tr key={idx}>
                      <td className="font-semibold text-[#fafafa]">{col.source_column}</td>
                      <td>{getRoleDisplay(col)}</td>
                      <td>{getConfidenceBadge(col)}</td>
                      <td className="text-[#a3a8b8]">{getUnitDisplay(col)}</td>
                      <td>{getConversionDisplay(col)}</td>
                      <td>{getStatusBadge(col)}</td>
                      <td className="text-[#a3a8b8] max-w-xs truncate" title={getReasonDisplay(col)}>
                        {getReasonDisplay(col)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Unmapped columns caption matching st.caption */}
          {unmappedColNames.length > 0 && (
            <p className="text-xs text-[#808495] font-sans">
              <strong>Unmapped source columns ({unmappedColNames.length}):</strong>{' '}
              {unmappedColNames.join(', ')}
            </p>
          )}
        </div>
      )}
    </div>
  );
};
