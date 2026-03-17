export type DetectionResult = {
  is_fake: boolean;
  confidence: number;
  pulse_value: number;
  landmarks: Array<{ x: number; y: number; z: number }>;
  reasons: string[];
  signal_breakdown: Record<string, number>;
  mode: string;
  threat_level: string;
  timestamp: number;
};

export type ScanLog = {
  id: string;
  label: string;
  confidence: number;
  threat: string;
  timestamp: string;
};
