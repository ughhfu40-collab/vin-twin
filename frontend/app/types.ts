export type Policy = "none" | "delivery" | "reorder";
export type Params = {
  delay: number;
  robot_minutes: number;
  robot_start?: number;
  eta_override?: number | null;
  policy: Policy;
  decision_time: number;
  contribution: number;
};
export type Operation = {
  station: number;
  start: number;
  end: number;
  previous_ready: number;
  resource_ready: number;
  segments: number[][];
  material_wait: number[] | null;
};
export type Vehicle = {
  id: string;
  kit: "A" | "B";
  model: string;
  completion: number;
  baseline_completion: number;
  delay_minutes: number;
  affected: boolean;
  operations: Operation[];
};
export type Station = {
  name: string;
  status: string;
  label: string;
  vin: string | null;
  queue: string[];
  utilization: number | null;
};
export type Frame = {
  time: number;
  actual_output: number;
  inventory: { A: number; B: number };
  stations: Station[];
};
export type Action = {
  policy: Policy;
  name: string;
  cost: number;
  output: number | null;
  saved: number | null;
  effect: number | null;
  available: boolean;
  reason: string;
};
export type Snapshot = {
  snapshot_id: string;
  input_version: string;
  model_version: string;
  source: string;
  updated_at: string;
  now: number;
  params: Params;
  output: number;
  baseline_output: number;
  capacity: number;
  plan: number;
  eta: number;
  supply: { quantity: number; kit: string };
  frames: Frame[];
  vehicles: Vehicle[];
  affected: string[];
  after_shift: string[];
  policies: Action[];
  recommended: Policy;
  material_waits: { vin: string; start: number; end: number; kit: string }[];
  incidents: {
    id: string;
    title: string;
    type: string;
    received_at: number;
    source: string;
    detail: string;
  }[];
  assumptions: string[];
  sensitivity: {
    contribution: number;
    recommended: Policy;
    effects: Partial<Record<Policy, number>>;
  }[];
  thresholds: { left: Policy; right: Policy; contribution: number }[];
};
export type Chat = {
  snapshot_id: string;
  intent: string;
  fact_refs: string[];
  source_mode: string;
  answer: string;
};
