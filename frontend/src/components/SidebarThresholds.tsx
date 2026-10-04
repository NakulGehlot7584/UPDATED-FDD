import React, { useState, useEffect } from 'react';
import { Sliders, RotateCcw, ChevronLeft, ChevronRight, Play } from 'lucide-react';
import { NumberInput } from './NumberInput';

interface QuickThresholds {
  persistence: number;
  command_persistence: number;
  sat_error: number;
  valve_error: number;
  static_error: number;
  co2_setpoint: number;
  co2_error: number;
  maximum_humidity: number;
  forward_fill_limit: number;
}

const DEFAULT_QUICK_THRESHOLDS: QuickThresholds = {
  persistence: 3,
  command_persistence: 2,
  sat_error: 3.0,
  valve_error: 15.0,
  static_error: 75.0,
  co2_setpoint: 900.0,
  co2_error: 100.0,
  maximum_humidity: 70.0,
  forward_fill_limit: 3,
};

const PRESETS: Record<string, QuickThresholds> = {
  Standard: DEFAULT_QUICK_THRESHOLDS,
  Sensitive: {
    persistence: 2,
    command_persistence: 2,
    sat_error: 1.0,
    valve_error: 10.0,
    static_error: 30.0,
    co2_setpoint: 800.0,
    co2_error: 100.0,
    maximum_humidity: 65.0,
    forward_fill_limit: 2,
  },
  Lenient: {
    persistence: 5,
    command_persistence: 5,
    sat_error: 3.5,
    valve_error: 25.0,
    static_error: 80.0,
    co2_setpoint: 1000.0,
    co2_error: 250.0,
    maximum_humidity: 75.0,
    forward_fill_limit: 4,
  },
};

interface Props {
  isOpen: boolean;
  onToggle: () => void;
  onThresholdsChange: (overrides: Record<string, Record<string, number>>) => void;
  onApplyAndRerun?: () => void;
  isRunExecuted?: boolean;
}

export const SidebarThresholds: React.FC<Props> = ({
  isOpen,
  onToggle,
  onThresholdsChange,
  onApplyAndRerun,
  isRunExecuted = false,
}) => {
  const [thresholds, setThresholds] = useState<QuickThresholds>(DEFAULT_QUICK_THRESHOLDS);
  const [selectedPreset, setSelectedPreset] = useState<string>('Standard');
  const [hasChangedSinceRun, setHasChangedSinceRun] = useState(false);

  // Sync with parent parameter_overrides only when non-Standard preset or customized
  useEffect(() => {
    if (selectedPreset === 'Standard') {
      onThresholdsChange({});
      return;
    }
    const overrides: Record<string, Record<string, number>> = {
      GLOBAL: {
        confirm_seconds: thresholds.persistence * 300,
        persistence_min: thresholds.persistence,
        sat_err: thresholds.sat_error,
        sat_dev_err: thresholds.sat_error,
        valve_open_pct: thresholds.valve_error / 100.0,
        eps_dsp: thresholds.static_error / 248.84,
        co2_setpoint: thresholds.co2_setpoint,
        co2_error: thresholds.co2_error,
        maximum_humidity: thresholds.maximum_humidity,
        forward_fill_limit: thresholds.forward_fill_limit,
      },
    };
    onThresholdsChange(overrides);
  }, [thresholds, selectedPreset, onThresholdsChange]);

  const handleChange = (key: keyof QuickThresholds, value: number) => {
    setThresholds((prev) => ({ ...prev, [key]: value }));
    setSelectedPreset('Custom');
    if (isRunExecuted) {
      setHasChangedSinceRun(true);
    }
  };

  const handlePresetChange = (presetName: string) => {
    setSelectedPreset(presetName);
    if (PRESETS[presetName]) {
      setThresholds(PRESETS[presetName]);
      if (isRunExecuted) setHasChangedSinceRun(true);
    }
  };

  const handleReset = () => {
    setThresholds(DEFAULT_QUICK_THRESHOLDS);
    setSelectedPreset('Standard');
    setHasChangedSinceRun(false);
    onThresholdsChange({});
  };

  return (
    <>
      {/* Tablet & mobile backdrop overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 lg:hidden transition-opacity duration-300"
          onClick={onToggle}
          aria-hidden="true"
        />
      )}

      {/* Floating reopen button when collapsed (Streamlit style) */}
      {!isOpen && (
        <button
          type="button"
          id="sidebar-toggle-btn"
          onClick={onToggle}
          title="Expand Rule Thresholds Sidebar"
          aria-label="Expand Rule Thresholds Sidebar"
          className="fixed top-4 left-4 z-30 p-2 rounded-md bg-[#262730] hover:bg-[#31333f] text-[#ff4b4b] border border-[rgba(250,250,250,0.12)] shadow-md transition-colors cursor-pointer flex items-center justify-center focus:outline-none focus:ring-1 focus:ring-[#ff4b4b]"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      )}

      {/* Main Sidebar Aside Panel */}
      <aside
        className={`fixed top-0 left-0 bottom-0 z-40 w-[21rem] max-w-[85vw] sm:max-w-sm bg-[#262730] border-r border-[rgba(250,250,250,0.12)] text-[#fafafa] flex flex-col transition-transform duration-300 ease-in-out select-none shadow-xl lg:shadow-none ${
          isOpen ? 'translate-x-0' : '-translate-x-full shadow-none pointer-events-none'
        }`}
        aria-hidden={!isOpen}
      >
        {/* Sidebar Header matching st.header */}
        <div className="h-14 w-full shrink-0 flex items-center justify-between px-4 border-b border-[rgba(250,250,250,0.12)] bg-[#262730]">
          <h2 className="text-base font-bold text-[#fafafa] flex items-center gap-2 truncate">
            <Sliders className="w-4 h-4 text-[#ff4b4b] shrink-0" />
            <span>Rule thresholds</span>
          </h2>
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              onClick={handleReset}
              title="Reset to default thresholds"
              className="text-[#a3a8b8] hover:text-[#fafafa] p-1.5 rounded hover:bg-[#31333f] transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              id={isOpen ? 'sidebar-toggle-btn' : undefined}
              onClick={onToggle}
              title="Collapse Sidebar"
              aria-label="Collapse Sidebar"
              className="text-[#a3a8b8] hover:text-[#fafafa] p-1.5 rounded hover:bg-[#31333f] transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Sidebar Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 font-sans text-xs">
          {/* Preset Selector */}
          <div className="space-y-1">
            <label className="text-[#fafafa] font-medium block text-[0.875rem]">Threshold Preset</label>
            <select
              value={selectedPreset}
              onChange={(e) => handlePresetChange(e.target.value)}
              className="w-full bg-[#1e2129] border border-[rgba(250,250,250,0.2)] rounded-lg h-9 px-3 text-xs text-[#fafafa] outline-none focus:border-[#ff4b4b] shadow-sm transition-colors"
            >
              <option value="Standard">Standard (Open-FDD Baseline)</option>
              <option value="Sensitive">Sensitive (Low Tolerance)</option>
              <option value="Lenient">Lenient (High Tolerance)</option>
              <option value="Custom">Custom Overrides</option>
            </select>
          </div>

          {hasChangedSinceRun && (
            <div className="st-alert-warning text-[11px] py-2 px-3 font-sans rounded-md">
              Thresholds changed. Click &apos;Apply &amp; Re-run&apos; to evaluate against latest parameters.
            </div>
          )}

          {/* 1. Persistence (records) */}
          <NumberInput
            label="Persistence (records)"
            value={thresholds.persistence}
            min={1}
            max={12}
            step={1}
            onChange={(val) => handleChange('persistence', val)}
            formatDecimals={0}
          />

          {/* 2. Command/status persistence */}
          <NumberInput
            label="Command/status persistence"
            value={thresholds.command_persistence}
            min={1}
            max={12}
            step={1}
            onChange={(val) => handleChange('command_persistence', val)}
            formatDecimals={0}
          />

          {/* 3. Allowed SAT error (C) */}
          <NumberInput
            label="Allowed SAT error (C)"
            value={thresholds.sat_error}
            min={0.5}
            max={10.0}
            step={0.5}
            onChange={(val) => handleChange('sat_error', val)}
            formatDecimals={1}
          />

          {/* 4. Valve tracking error (%) */}
          <NumberInput
            label="Valve tracking error (%)"
            value={thresholds.valve_error}
            min={5.0}
            max={50.0}
            step={5.0}
            onChange={(val) => handleChange('valve_error', val)}
            formatDecimals={1}
          />

          {/* 5. Static-pressure error (Pa) */}
          <NumberInput
            label="Static-pressure error (Pa)"
            value={thresholds.static_error}
            min={10.0}
            max={300.0}
            step={5.0}
            onChange={(val) => handleChange('static_error', val)}
            formatDecimals={1}
          />

          {/* 6. Live CO2 setpoint (ppm) */}
          <NumberInput
            label="Live CO2 setpoint (ppm)"
            value={thresholds.co2_setpoint}
            min={400.0}
            max={2000.0}
            step={50.0}
            onChange={(val) => handleChange('co2_setpoint', val)}
            formatDecimals={1}
          />

          {/* 7. CO2 error above setpoint (ppm) */}
          <NumberInput
            label="CO2 error above setpoint (ppm)"
            value={thresholds.co2_error}
            min={25.0}
            max={1000.0}
            step={25.0}
            onChange={(val) => handleChange('co2_error', val)}
            formatDecimals={1}
          />

          {/* 8. Maximum room humidity (%RH) */}
          <NumberInput
            label="Maximum room humidity (%RH)"
            value={thresholds.maximum_humidity}
            min={30.0}
            max={95.0}
            step={1.0}
            onChange={(val) => handleChange('maximum_humidity', val)}
            formatDecimals={1}
          />

          {/* 9. Live-data short-gap fill (records) */}
          <NumberInput
            label="Live-data short-gap fill (records)"
            value={thresholds.forward_fill_limit}
            min={0}
            max={12}
            step={1}
            onChange={(val) => handleChange('forward_fill_limit', val)}
            formatDecimals={0}
          />

          {onApplyAndRerun && (
            <div className="pt-2">
              <button
                type="button"
                onClick={onApplyAndRerun}
                className="w-full st-button-primary text-xs py-2.5 shadow-sm font-semibold flex items-center justify-center gap-1.5"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                Apply &amp; Re-run FDD
              </button>
            </div>
          )}
        </div>
      </aside>
    </>
  );
};
