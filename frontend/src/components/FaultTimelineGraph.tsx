import React from 'react';
import { FaultTimelinePayload } from '../types/api';

interface Props {
  timeline: FaultTimelinePayload;
  onSelectRule?: (ruleId: string) => void;
  selectedRuleId?: string | null;
}

export const FaultTimelineGraph: React.FC<Props> = ({ timeline, onSelectRule, selectedRuleId }) => {
  if (!timeline || timeline.lanes.length === 0) {
    return (
      <div className="p-4 text-center text-xs text-[#a3a8b8] font-mono bg-[#1e2129] border border-[rgba(250,250,250,0.12)] rounded-lg">
        No active fault episodes recorded across evaluated rules.
      </div>
    );
  }

  // Parse global start and end timestamps
  const startStr = timeline.time_range.start;
  const endStr = timeline.time_range.end;
  const startMs = startStr ? new Date(startStr).getTime() : 0;
  const endMs = endStr ? new Date(endStr).getTime() : 0;
  const totalDurationMs = Math.max(1, endMs - startMs);

  const getLeftPct = (isoTime: string) => {
    const t = new Date(isoTime).getTime();
    return Math.max(0, Math.min(100, ((t - startMs) / totalDurationMs) * 100));
  };

  const getWidthPct = (startIso: string, endIso: string) => {
    const s = new Date(startIso).getTime();
    const e = new Date(endIso).getTime();
    const w = ((e - s) / totalDurationMs) * 100;
    return Math.max(0.5, Math.min(100, w));
  };

  return (
    <div className="bg-[#1e2129] border border-[rgba(250,250,250,0.12)] rounded-lg p-3 shadow-sm font-sans">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2.5 pb-2 border-b border-[rgba(250,250,250,0.12)]">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-[#fafafa] uppercase tracking-wider font-mono">
            Fault Episode Timeline (Swimlanes)
          </span>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-[rgba(255,75,75,0.15)] text-[#ff7b72] border border-[#ff4b4b] font-semibold">
            {timeline.total_episodes} Episodes ({timeline.total_fault_hours.toFixed(1)} hrs total)
          </span>
        </div>
        <div className="text-[10px] font-mono text-[#a3a8b8] flex flex-wrap items-center gap-2 sm:gap-3">
          <span>Start: {startStr ? new Date(startStr).toLocaleDateString() : '--'}</span>
          <span>End: {endStr ? new Date(endStr).toLocaleDateString() : '--'}</span>
        </div>
      </div>

      <div className="space-y-1.5">
        {timeline.lanes.map((lane) => {
          const isSelected = selectedRuleId?.toLowerCase() === lane.rule_id.toLowerCase();
          return (
            <div
              key={lane.rule_id}
              onClick={() => onSelectRule && onSelectRule(lane.rule_id)}
              className={`group flex items-center gap-2.5 p-2 rounded-lg border transition-all cursor-pointer ${
                isSelected
                  ? 'bg-[#262730] border-[#ff4b4b] shadow-sm'
                  : 'bg-[#1e2129] border-[rgba(250,250,250,0.12)] hover:bg-[#262730] hover:border-[rgba(250,250,250,0.25)]'
              }`}
            >
              {/* Lane Header / Rule ID */}
              <div className="w-28 sm:w-44 shrink-0">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono font-semibold text-[#fafafa] truncate" title={lane.rule_id}>
                    {lane.rule_id}
                  </span>
                  <span className="text-[10px] font-mono text-[#ff7b72] font-bold">
                    {lane.total_fault_hours.toFixed(1)}h
                  </span>
                </div>
                <div className="text-[10px] text-[#a3a8b8] truncate" title={lane.rule_name}>
                  {lane.rule_name}
                </div>
              </div>

              {/* Lane Bar Timeline Canvas */}
              <div className="relative flex-1 h-5 bg-[#0e1117] rounded border border-[rgba(250,250,250,0.12)] overflow-hidden">
                {lane.episodes.map((ep, eIdx) => {
                  const left = getLeftPct(ep.start);
                  const width = getWidthPct(ep.start, ep.end);
                  return (
                    <div
                      key={eIdx}
                      className="absolute top-0.5 bottom-0.5 rounded-sm bg-[#ff7b72] hover:bg-[#ff9994] transition-colors cursor-pointer"
                      style={{
                        left: `${left}%`,
                        width: `${width}%`,
                      }}
                      title={`Fault Episode ${eIdx + 1}: ${ep.duration_hours.toFixed(2)}h (${ep.start} to ${ep.end})`}
                    />
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
