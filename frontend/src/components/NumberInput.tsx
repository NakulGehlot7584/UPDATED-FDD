import React from 'react';
import { Minus, Plus } from 'lucide-react';

interface NumberInputProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (val: number) => void;
  formatDecimals?: number;
}

export const NumberInput: React.FC<NumberInputProps> = ({
  label,
  value,
  min,
  max,
  step,
  onChange,
  formatDecimals,
}) => {
  const handleDecrement = () => {
    const next = Math.max(min, value - step);
    onChange(Number(next.toFixed(formatDecimals ?? (step < 1 ? 1 : 0))));
  };

  const handleIncrement = () => {
    const next = Math.min(max, value + step);
    onChange(Number(next.toFixed(formatDecimals ?? (step < 1 ? 1 : 0))));
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const parsed = parseFloat(e.target.value);
    if (!isNaN(parsed)) {
      const clamped = Math.min(max, Math.max(min, parsed));
      onChange(clamped);
    }
  };

  const displayVal = formatDecimals !== undefined ? value.toFixed(formatDecimals) : value;

  return (
    <div className="space-y-1 font-sans text-xs">
      <label className="text-[#fafafa] font-medium block text-[0.875rem]">{label}</label>
      <div className="flex items-center bg-[#1e2129] border border-[rgba(250,250,250,0.2)] rounded-lg h-9 overflow-hidden focus-within:border-[#ff4b4b] shadow-sm transition-colors">
        <input
          type="number"
          min={min}
          max={max}
          step={step}
          value={displayVal}
          onChange={handleInputChange}
          className="bg-transparent text-[#fafafa] font-mono text-xs px-3 w-full outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
        />
        <div className="flex items-center border-l border-[rgba(250,250,250,0.15)] h-full shrink-0">
          <button
            type="button"
            onClick={handleDecrement}
            disabled={value <= min}
            className="px-2.5 h-full hover:bg-[#262730] text-[#a3a8b8] hover:text-[#fafafa] disabled:opacity-30 disabled:hover:bg-transparent flex items-center justify-center transition-colors"
          >
            <Minus className="w-3 h-3" />
          </button>
          <button
            type="button"
            onClick={handleIncrement}
            disabled={value >= max}
            className="px-2.5 h-full hover:bg-[#262730] text-[#a3a8b8] hover:text-[#fafafa] disabled:opacity-30 disabled:hover:bg-transparent flex items-center justify-center transition-colors border-l border-[rgba(250,250,250,0.15)]"
          >
            <Plus className="w-3 h-3" />
          </button>
        </div>
      </div>
    </div>
  );
};
