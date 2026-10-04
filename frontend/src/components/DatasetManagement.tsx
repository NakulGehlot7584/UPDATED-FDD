import React, { useRef, useState } from 'react';
import {
  UploadCloud,
  Trash2,
  XCircle,
  Loader2,
  Info,
} from 'lucide-react';
import { uploadDatasets } from '../services/api';
import { DatasetDetailResponse, DatasetListResponse, DatasetSummary } from '../types/api';

export const REQUIRED_COLUMNS = [
  'timestamp', 'equipment_id', 'occupied', 'ahu_on_command',
  'ahu_run_status', 'ahu_auto_mode', 'filter_dirty_status',
  'fresh_air_damper_command_pct', 'fresh_air_velocity_mps',
  'chw_valve_command_pct', 'chw_valve_feedback_pct',
  'ec_fan_speed_command_pct', 'duct_static_pressure_pa',
  'duct_static_pressure_setpoint_pa', 'supply_air_temp_c',
  'supply_air_temp_setpoint_c', 'return_air_temp_c', 'co2_ppm',
  'co2_setpoint_ppm', 'chw_supply_temp_c', 'chw_return_temp_c',
  'exhaust_fan_on_command', 'exhaust_fan_run_status',
  'exhaust_fan_auto_mode',
];

interface DatasetManagementProps {
  datasets: DatasetSummary[];
  selectedId: string | null;
  currentDataset: DatasetDetailResponse | null;
  onSelectDataset: (id: string) => void;
  onDeleteDataset: (id: string) => void;
  onClearAll: () => void;
  onUploadSuccess: (res: DatasetListResponse) => void;
}

export const DatasetManagement: React.FC<DatasetManagementProps> = ({
  datasets,
  selectedId,
  currentDataset,
  onSelectDataset,
  onDeleteDataset,
  onClearAll,
  onUploadSuccess,
}) => {
  const [isUploading, setIsUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const colNames = (currentDataset?.columns || []).map((c) => c.source_column.toLowerCase());
  const isFullFormat = REQUIRED_COLUMNS.every((rc) => colNames.includes(rc.toLowerCase()));
  const isLiveBms = !isFullFormat && colNames.some((c) => c.includes('.tl') || c.includes('trend') || c.includes('enteliweb'));
  const modeLabel = isFullFormat
    ? 'Standard 24-column format'
    : isLiveBms
    ? 'Live BMS / enteliWEB format'
    : 'Generic Auto-Mapped BMS / BAS format';

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    const validFiles: File[] = [];
    for (let i = 0; i < files.length; i++) {
      const f = files[i];
      if (f.name.toLowerCase().endsWith('.csv')) {
        validFiles.push(f);
      }
    }

    if (validFiles.length === 0) {
      setErrorMessage('Please select valid .csv telemetry files.');
      return;
    }

    setIsUploading(true);
    setErrorMessage(null);

    try {
      const result = await uploadDatasets(validFiles);
      if (fileInputRef.current) fileInputRef.current.value = '';
      onUploadSuccess(result);
    } catch (err: any) {
      setErrorMessage(err.message || 'Upload failed');
    } finally {
      setIsUploading(false);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  return (
    <section className="space-y-4 select-none font-sans">
      {/* Hidden File Input */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={(e) => handleFiles(e.target.files)}
        multiple
        accept=".csv"
        className="hidden"
      />

      {/* Streamlit st.file_uploader widget */}
      <div className="space-y-1.5">
        <label className="text-sm font-semibold text-[#fafafa] block">
          Upload multi-point or enteliWEB CSV(s)
        </label>
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-lg p-6 transition-all cursor-pointer flex flex-col items-center justify-center gap-2 ${
            isDragging
              ? 'border-[#ff4b4b] bg-[rgba(255,75,75,0.05)]'
              : 'border-[rgba(250,250,250,0.2)] bg-[#1e2129] hover:border-[#ff4b4b]'
          }`}
        >
          {isUploading ? (
            <div className="flex items-center gap-2 text-sm text-[#1c83e1]">
              <Loader2 className="w-5 h-5 animate-spin" />
              <span>Ingesting CSV telemetry...</span>
            </div>
          ) : (
            <>
              <UploadCloud className="w-8 h-8 text-[#a3a8b8]" />
              <div className="text-center">
                <p className="text-sm font-medium text-[#fafafa]">Drag and drop files here</p>
                <p className="text-xs text-[#a3a8b8] mt-0.5">Limit 200MB per file • CSV</p>
              </div>
              <button
                type="button"
                className="st-button-secondary text-xs px-3 py-1.5 mt-1"
              >
                Browse files
              </button>
            </>
          )}
        </div>
      </div>

      {errorMessage && (
        <div className="st-alert-error text-xs flex items-center gap-2">
          <span>{errorMessage}</span>
        </div>
      )}


      {/* Dataset Selector Row matching st.columns([3, 1, 1]) */}
      {datasets.length > 0 && (
        <div className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-12 gap-2 sm:gap-3 items-end">
            {/* Active Site / Dataset Selector (col_sel) */}
            <div className="sm:col-span-12 md:col-span-8">
              <label className="text-sm font-medium text-[#fafafa] block mb-1">
                Active Site / Dataset
              </label>
              <select
                id="active-dataset-select"
                value={selectedId || ''}
                onChange={(e) => onSelectDataset(e.target.value)}
                className="w-full max-w-full st-input cursor-pointer font-sans truncate"
              >
                {datasets.map((d) => (
                  <option key={d.dataset_id} value={d.dataset_id}>
                    {d.file_name}
                  </option>
                ))}
              </select>
            </div>

            {/* Delete Dataset Button (col_del) */}
            <div className="sm:col-span-6 md:col-span-2">
              <button
                type="button"
                onClick={() => selectedId && onDeleteDataset(selectedId)}
                className="w-full st-button-secondary text-xs py-2 flex items-center justify-center gap-1.5 hover:text-[#ff4b4b] hover:border-[#ff4b4b]"
              >
                <Trash2 className="w-3.5 h-3.5 text-[#ff4b4b]" />
                <span>Delete Dataset</span>
              </button>
            </div>

            {/* Clear All Button (col_clr) */}
            <div className="sm:col-span-6 md:col-span-2">
              <button
                type="button"
                onClick={onClearAll}
                className="w-full st-button-secondary text-xs py-2 flex items-center justify-center gap-1.5 hover:text-[#ff4b4b] hover:border-[#ff4b4b]"
              >
                <XCircle className="w-3.5 h-3.5 text-[#ff4b4b]" />
                <span>Clear All</span>
              </button>
            </div>
          </div>

          {/* Info Banner matching st.info */}
          {currentDataset && (
            <div className="st-alert-info text-xs flex flex-wrap items-center gap-2 font-mono break-all sm:break-normal">
              <Info className="w-4 h-4 shrink-0 text-[#1c83e1]" />
              <span className="break-words min-w-0">
                Analyzing: <strong className="text-[#0054a3]">{currentDataset.file_name}</strong> |{' '}
                Import mode: <span className="text-[#09ab3b] font-semibold">{modeLabel}</span> |{' '}
                Loaded Datasets: <strong className="text-[#0054a3]">{datasets.length}</strong>
              </span>
            </div>
          )}
        </div>
      )}
    </section>
  );
};
