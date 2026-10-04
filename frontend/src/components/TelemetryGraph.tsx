import React, { useState, useMemo, useRef, useCallback, useEffect } from 'react';
import { RotateCcw } from 'lucide-react';
import { GraphPayload } from '../types/api';

interface Props {
  data: GraphPayload;
  height?: number;
}

const SERIES_COLORS = [
  '#38bdf8', // sky
  '#10b981', // emerald
  '#f59e0b', // amber
  '#a855f7', // purple
  '#06b6d4', // cyan
  '#f43f5e', // rose
  '#3b82f6', // blue
  '#eab308', // yellow
];

export const TelemetryGraph: React.FC<Props> = ({ data, height = 360 }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const [hiddenSeries, setHiddenSeries] = useState<Set<string>>(new Set());

  // Zoom / Pan state: fractional range [start, end] from 0 to 1
  const [zoomRange, setZoomRange] = useState<{ start: number; end: number }>({ start: 0, end: 1 });
  const [isPanning, setIsPanning] = useState(false);
  const panStartRef = useRef<{ clientX: number; start: number; end: number } | null>(null);

  const isZoomed = zoomRange.start > 0.001 || zoomRange.end < 0.999;

  const handleResetZoom = useCallback(() => {
    setZoomRange({ start: 0, end: 1 });
  }, []);

  // Collect and sort unique timestamps across all active series
  const activeSeries = useMemo(() => {
    return data.series.filter((s) => !hiddenSeries.has(s.role) && s.timestamps.length > 0);
  }, [data.series, hiddenSeries]);

  const timestamps = useMemo(() => {
    if (activeSeries.length === 0) return [];
    // Take timestamps from the longest series as base
    let longest = activeSeries[0].timestamps;
    for (const s of activeSeries) {
      if (s.timestamps.length > longest.length) longest = s.timestamps;
    }
    return longest;
  }, [activeSeries]);

  // Separate series by Y-axis (y1 left, y2 right)
  const y1Series = useMemo(() => activeSeries.filter((s) => s.y_axis !== 'y2'), [activeSeries]);
  const y2Series = useMemo(() => activeSeries.filter((s) => s.y_axis === 'y2'), [activeSeries]);

  // Calculate Y1 min/max
  const { y1Min, y1Max } = useMemo(() => {
    let min = Infinity;
    let max = -Infinity;
    for (const s of y1Series) {
      for (const v of s.values) {
        if (v !== null && Number.isFinite(v)) {
          if (v < min) min = v;
          if (v > max) max = v;
        }
      }
    }
    if (!Number.isFinite(min)) min = 0;
    if (!Number.isFinite(max)) max = 100;
    if (min === max) {
      min -= 1;
      max += 1;
    }
    const pad = (max - min) * 0.08;
    return { y1Min: min - pad, y1Max: max + pad };
  }, [y1Series]);

  // Calculate Y2 min/max
  const { y2Min, y2Max } = useMemo(() => {
    if (y2Series.length === 0) return { y2Min: 0, y2Max: 100 };
    let min = Infinity;
    let max = -Infinity;
    for (const s of y2Series) {
      for (const v of s.values) {
        if (v !== null && Number.isFinite(v)) {
          if (v < min) min = v;
          if (v > max) max = v;
        }
      }
    }
    if (!Number.isFinite(min)) min = 0;
    if (!Number.isFinite(max)) max = 100;
    if (min === max) {
      min -= 1;
      max += 1;
    }
    const pad = (max - min) * 0.08;
    return { y2Min: min - pad, y2Max: max + pad };
  }, [y2Series]);

  // Chart layout dimensions
  const padLeft = 55;
  const padRight = y2Series.length > 0 ? 55 : 20;
  const padTop = 25;
  const padBottom = 35;
  const svgWidth = 800; // coordinate system width
  const svgHeight = height;

  const chartW = svgWidth - padLeft - padRight;
  const chartH = svgHeight - padTop - padBottom;

  const totalPoints = timestamps.length;

  // Viewport index range based on zoom
  const startIdx = totalPoints > 0 ? Math.max(0, Math.floor(zoomRange.start * (totalPoints - 1))) : 0;
  const endIdx = totalPoints > 0 ? Math.min(totalPoints - 1, Math.ceil(zoomRange.end * (totalPoints - 1))) : 0;
  const spanIdx = Math.max(1, endIdx - startIdx);

  const getX = (idx: number) => {
    if (totalPoints <= 1) return padLeft + chartW / 2;
    return padLeft + ((idx - startIdx) / spanIdx) * chartW;
  };

  const getY1 = (val: number) => {
    return padTop + chartH - ((val - y1Min) / (y1Max - y1Min)) * chartH;
  };

  const getY2 = (val: number) => {
    return padTop + chartH - ((val - y2Min) / (y2Max - y2Min)) * chartH;
  };

  // Convert time to X coordinate for fault boxes
  const getTimeX = (timeStr: string) => {
    if (totalPoints === 0) return padLeft;
    // Find closest timestamp
    const t = new Date(timeStr).getTime();
    if (isNaN(t)) return padLeft;
    let closestIdx = 0;
    let minDiff = Infinity;
    for (let i = 0; i < totalPoints; i++) {
      const curT = new Date(timestamps[i]).getTime();
      const diff = Math.abs(curT - t);
      if (diff < minDiff) {
        minDiff = diff;
        closestIdx = i;
      }
    }
    return getX(closestIdx);
  };

  const svgRef = useRef<SVGSVGElement>(null);

  // Wheel and touchpad pinch zoom handling strictly on the SVG element
  useEffect(() => {
    const svgEl = svgRef.current;
    if (!svgEl) return;

    const onWheel = (e: WheelEvent) => {
      // Isolate wheel/pinch to the SVG: prevent document scroll and browser pinch-zoom
      e.preventDefault();
      e.stopPropagation();

      if (totalPoints <= 1) return;

      const rect = svgEl.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const normX = (mouseX / rect.width) * svgWidth;
      const relX = normX - padLeft;
      const cursorFraction = Math.max(0, Math.min(1, relX / chartW));

      // Current time fraction at mouse cursor
      const currentSpan = zoomRange.end - zoomRange.start;
      const focusPoint = zoomRange.start + cursorFraction * currentSpan;

      // Handle standard vertical mouse wheel and touchpad pinch (which has ctrlKey=true)
      let zoomFactor: number;
      if (e.ctrlKey) {
        // Touchpad pinch-to-zoom
        zoomFactor = Math.exp(e.deltaY * 0.01);
      } else {
        // Standard mouse wheel
        zoomFactor = e.deltaY < 0 ? 0.75 : 1.35;
      }

      let newSpan = currentSpan * zoomFactor;

      // Minimum span (at least 5 points visible) and maximum span (1.0 = 100%)
      const minSpan = Math.max(0.005, 5 / totalPoints);
      if (newSpan < minSpan) newSpan = minSpan;
      if (newSpan > 1) newSpan = 1;

      let newStart = focusPoint - cursorFraction * newSpan;
      let newEnd = newStart + newSpan;

      if (newStart < 0) {
        newStart = 0;
        newEnd = Math.min(1, newSpan);
      }
      if (newEnd > 1) {
        newEnd = 1;
        newStart = Math.max(0, 1 - newSpan);
      }

      setZoomRange({ start: newStart, end: newEnd });
    };

    // Attach as non-passive so e.preventDefault() works reliably to stop page scroll & pinch zoom
    svgEl.addEventListener('wheel', onWheel, { passive: false });

    return () => {
      svgEl.removeEventListener('wheel', onWheel);
    };
  }, [totalPoints, zoomRange, chartW, padLeft, svgWidth]);

  // Pointer drag panning (works seamlessly with mouse and touchpad pointer)
  const handlePointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    if (e.button !== 0) return; // Only primary button
    if (isZoomed) {
      e.currentTarget.setPointerCapture(e.pointerId);
      setIsPanning(true);
      panStartRef.current = {
        clientX: e.clientX,
        start: zoomRange.start,
        end: zoomRange.end,
      };
    }
  };

  const handlePointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!svgRef.current || totalPoints === 0) return;

    if (isPanning && panStartRef.current) {
      const rect = svgRef.current.getBoundingClientRect();
      const deltaPx = e.clientX - panStartRef.current.clientX;
      const fractionShift = (deltaPx / rect.width) * (panStartRef.current.end - panStartRef.current.start);

      let newStart = panStartRef.current.start - fractionShift;
      let newEnd = panStartRef.current.end - fractionShift;
      const span = panStartRef.current.end - panStartRef.current.start;

      if (newStart < 0) {
        newStart = 0;
        newEnd = span;
      }
      if (newEnd > 1) {
        newEnd = 1;
        newStart = 1 - span;
      }

      setZoomRange({ start: newStart, end: newEnd });
      return;
    }

    const rect = svgRef.current.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const normX = (mouseX / rect.width) * svgWidth;
    const relX = normX - padLeft;
    const ratio = Math.max(0, Math.min(1, relX / chartW));
    const idx = Math.round(startIdx + ratio * spanIdx);
    setHoverIdx(Math.max(0, Math.min(totalPoints - 1, idx)));
  };

  const handlePointerUp = (e: React.PointerEvent<SVGSVGElement>) => {
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
    setIsPanning(false);
    panStartRef.current = null;
  };

  const handlePointerLeave = () => {
    if (!isPanning) {
      setHoverIdx(null);
    }
  };

  const toggleSeries = (role: string) => {
    setHiddenSeries((prev) => {
      const next = new Set(prev);
      if (next.has(role)) next.delete(role);
      else next.add(role);
      return next;
    });
  };

  // Y1 Axis Ticks
  const y1Ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => {
    const val = y1Min + f * (y1Max - y1Min);
    return { val, y: getY1(val) };
  });

  // Y2 Axis Ticks
  const y2Ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => {
    const val = y2Min + f * (y2Max - y2Min);
    return { val, y: getY2(val) };
  });

  // Time X Ticks (up to 6 ticks across visible zoom viewport)
  const xTicks = useMemo(() => {
    if (totalPoints === 0) return [];
    const count = Math.min(6, spanIdx + 1);
    const step = Math.max(1, Math.floor(spanIdx / count));
    const ticks = [];
    for (let i = startIdx; i <= endIdx; i += step) {
      ticks.push({ idx: i, time: timestamps[i], x: getX(i) });
    }
    return ticks;
  }, [totalPoints, timestamps, startIdx, endIdx, spanIdx]);

  const formatTimestamp = (ts: string) => {
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' });
    } catch {
      return ts;
    }
  };

  return (
    <div className="bg-[#1e2129] border border-[rgba(250,250,250,0.12)] rounded-lg p-3 shadow-sm select-none font-sans">
      {/* Chart Title and Series Legend */}
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2 px-1">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-[#fafafa] uppercase tracking-wider font-mono">
            {data.title || 'Telemetry Trend'}
          </span>
          {isZoomed && (
            <button
              type="button"
              onClick={handleResetZoom}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-[#262730] hover:bg-[#323440] text-[#58a6ff] border border-[rgba(88,166,255,0.4)] cursor-pointer transition-colors shadow-xs"
              title="Reset zoom to full dataset range"
            >
              <RotateCcw className="w-2.5 h-2.5" />
              Reset Zoom ({Math.round(spanIdx / (totalPoints || 1) * 100)}%)
            </button>
          )}
        </div>

        {/* Legend toggles */}
        <div className="flex flex-wrap items-center gap-2 text-[11px]">
          {data.series.map((s, idx) => {
            const isHidden = hiddenSeries.has(s.role);
            const color = s.color || SERIES_COLORS[idx % SERIES_COLORS.length];
            const isSetpoint = s.role.includes('_sp') || s.name.toLowerCase().includes('setpoint');
            return (
              <button
                key={s.role}
                type="button"
                onClick={() => toggleSeries(s.role)}
                className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-mono transition-opacity cursor-pointer border ${
                  isHidden
                    ? 'opacity-40 bg-[#262730] border-[rgba(250,250,250,0.15)] text-[#a3a8b8]'
                    : 'bg-[#262730] border-[rgba(250,250,250,0.2)] text-[#fafafa] hover:border-[rgba(250,250,250,0.4)]'
                }`}
              >
                <span
                  className="w-2.5 h-0.5 inline-block"
                  style={{
                    backgroundColor: color,
                    borderTop: isSetpoint ? `1px dashed ${color}` : undefined,
                  }}
                />
                <span>{s.name}</span>
                {s.unit && <span className="text-[#a3a8b8] text-[10px]">({s.unit})</span>}
              </button>
            );
          })}
          {data.fault_episodes.length > 0 && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono bg-[rgba(255,75,75,0.15)] border border-[#ff4b4b] text-[#ff7b72] font-semibold">
              <span className="w-2 h-2 rounded-sm bg-[#ff4b4b] inline-block" />
              FAULT ({data.fault_episodes.length})
            </span>
          )}
        </div>
      </div>

      {/* SVG Plot */}
      <div ref={containerRef} className="relative w-full overflow-hidden">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          className={`w-full h-auto block select-none touch-none ${isPanning ? 'cursor-grabbing' : isZoomed ? 'cursor-grab' : 'cursor-crosshair'}`}
          style={{ touchAction: 'none', userSelect: 'none' }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
          onPointerLeave={handlePointerLeave}
        >
          {/* Background Grid Lines */}
          {y1Ticks.map((t, i) => (
            <line
              key={`grid-${i}`}
              x1={padLeft}
              y1={t.y}
              x2={padLeft + chartW}
              y2={t.y}
              stroke="rgba(250, 250, 250, 0.08)"
              strokeDasharray="2 2"
              strokeWidth="1"
            />
          ))}

          {/* Fault Episode Highlight Boxes (D:\csvopenfdd Plotly style) */}
          {data.fault_episodes.map((ep, i) => {
            const x0 = getTimeX(ep.start);
            const x1 = getTimeX(ep.end);
            const boxW = Math.max(3, x1 - x0);
            return (
              <g key={`fault-box-${i}`}>
                <rect
                  x={x0}
                  y={padTop}
                  width={boxW}
                  height={chartH}
                  fill="rgba(255, 75, 75, 0.16)"
                  stroke="rgba(255, 75, 75, 0.5)"
                  strokeWidth="1"
                  strokeDasharray="3 3"
                />
                <text
                  x={x0 + 3}
                  y={padTop + 10}
                  fill="#ff7b72"
                  fontSize="9"
                  fontFamily="monospace"
                  fontWeight="bold"
                >
                  FAULT
                </text>
              </g>
            );
          })}

          {/* Y1 Axis Line & Labels (Left) */}
          <line x1={padLeft} y1={padTop} x2={padLeft} y2={padTop + chartH} stroke="rgba(250, 250, 250, 0.2)" strokeWidth="1" />
          {y1Ticks.map((t, i) => (
            <text
              key={`y1-lbl-${i}`}
              x={padLeft - 6}
              y={t.y + 3}
              fill="#a3a8b8"
              fontSize="10"
              textAnchor="end"
              fontFamily="monospace"
            >
              {t.val.toFixed(1)}
            </text>
          ))}

          {/* Y2 Axis Line & Labels (Right) */}
          {y2Series.length > 0 && (
            <>
              <line
                x1={padLeft + chartW}
                y1={padTop}
                x2={padLeft + chartW}
                y2={padTop + chartH}
                stroke="rgba(250, 250, 250, 0.2)"
                strokeWidth="1"
              />
              {y2Ticks.map((t, i) => (
                <text
                  key={`y2-lbl-${i}`}
                  x={padLeft + chartW + 6}
                  y={t.y + 3}
                  fill="#a3a8b8"
                  fontSize="10"
                  textAnchor="start"
                  fontFamily="monospace"
                >
                  {t.val.toFixed(0)}%
                </text>
              ))}
            </>
          )}

          {/* X Axis Line & Time Ticks */}
          <line
            x1={padLeft}
            y1={padTop + chartH}
            x2={padLeft + chartW}
            y2={padTop + chartH}
            stroke="rgba(250, 250, 250, 0.2)"
            strokeWidth="1"
          />
          {xTicks.map((t, i) => (
            <g key={`x-tick-${i}`}>
              <line x1={t.x} y1={padTop + chartH} x2={t.x} y2={padTop + chartH + 4} stroke="rgba(250, 250, 250, 0.2)" />
              <text
                x={t.x}
                y={padTop + chartH + 16}
                fill="#a3a8b8"
                fontSize="9"
                textAnchor="middle"
                fontFamily="monospace"
              >
                {formatTimestamp(t.time)}
              </text>
            </g>
          ))}

          {/* Series Polylines */}
          {activeSeries.map((s, sIdx) => {
            const color = s.color || SERIES_COLORS[sIdx % SERIES_COLORS.length];
            const isSetpoint = s.role.includes('_sp') || s.name.toLowerCase().includes('setpoint');
            const isY2 = s.y_axis === 'y2';
            const getY = isY2 ? getY2 : getY1;

            const pts: string[] = [];
            for (let i = 0; i < s.values.length; i++) {
              const val = s.values[i];
              if (val !== null && Number.isFinite(val)) {
                pts.push(`${getX(i)},${getY(val)}`);
              }
            }

            if (pts.length < 2) return null;

            return (
              <polyline
                key={s.role}
                fill="none"
                stroke={color}
                strokeWidth={isSetpoint ? 1.5 : 1.8}
                strokeDasharray={isSetpoint ? '4 3' : undefined}
                points={pts.join(' ')}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            );
          })}

          {/* Hover Crosshair & Dot Indicators */}
          {hoverIdx !== null && hoverIdx >= 0 && hoverIdx < totalPoints && (
            <>
              <line
                x1={getX(hoverIdx)}
                y1={padTop}
                x2={getX(hoverIdx)}
                y2={padTop + chartH}
                stroke="rgba(250, 250, 250, 0.4)"
                strokeWidth="1"
                strokeDasharray="2 2"
              />
              {activeSeries.map((s, sIdx) => {
                const color = s.color || SERIES_COLORS[sIdx % SERIES_COLORS.length];
                const val = s.values[hoverIdx];
                if (val === null || !Number.isFinite(val)) return null;
                const isY2 = s.y_axis === 'y2';
                const yPos = (isY2 ? getY2 : getY1)(val);
                return (
                  <circle
                    key={`hover-pt-${s.role}`}
                    cx={getX(hoverIdx)}
                    cy={yPos}
                    r="3.5"
                    fill={color}
                    stroke="#1e2129"
                    strokeWidth="1.5"
                  />
                );
              })}
            </>
          )}
        </svg>

        {/* Hover Unified Tooltip */}
        {hoverIdx !== null && hoverIdx >= 0 && hoverIdx < totalPoints && (
          <div
            className="absolute top-3 left-16 bg-[#262730]/95 border border-[rgba(250,250,250,0.2)] rounded-lg p-2.5 shadow-lg text-xs z-20 pointer-events-none backdrop-blur-sm"
            style={{ maxWidth: '280px' }}
          >
            <div className="text-[10px] font-mono text-[#a3a8b8] border-b border-[rgba(250,250,250,0.1)] pb-1 mb-1.5 font-semibold">
              {timestamps[hoverIdx]}
            </div>
            <div className="space-y-1">
              {activeSeries.map((s, idx) => {
                const color = s.color || SERIES_COLORS[idx % SERIES_COLORS.length];
                const val = s.values[hoverIdx];
                return (
                  <div key={s.role} className="flex items-center justify-between gap-3 text-[11px]">
                    <span className="flex items-center gap-1.5 text-[#fafafa]">
                      <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: color }} />
                      <span className="truncate">{s.name}:</span>
                    </span>
                    <span className="font-mono font-semibold text-[#fafafa]">
                      {val !== null && Number.isFinite(val) ? val.toFixed(2) : '--'}
                      {s.unit ? ` ${s.unit}` : ''}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
