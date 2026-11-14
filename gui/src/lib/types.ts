// Shapes of the messages exchanged with src/autopayroll/bridge.py.

export interface Period {
  period: number;
  start: string; // YYYY-MM-DD
  end: string;
}

export type PasswordSource = "file" | "keyring" | null;

export interface Settings {
  username: string;
  profile_dir: string;
  pay_rate: number;
  /** Only present when fetched through the `settings` method. */
  password?: PasswordSource;
}

export type Source = "trac" | "schedule";

export interface RunParams {
  source: Source;
  start: string;
  end: string;
  dry_run: boolean;
  schedule_path: string | null;
}

export interface BackendEvent {
  event: string;
  data: any;
}

export interface InitResult {
  config_dir: string;
  data_dir: string;
  settings: Settings;
  browser_open: boolean;
  run: { params: RunParams; events: BackendEvent[] } | null;
  periods: Period[];
  current_period: number | null;
}

export type StageId = "trac" | "parse" | "schedule" | "review" | "peoplesoft" | "verify";

export type StageStatus =
  | "pending"
  | "active"
  | "waiting"
  | "done"
  | "skipped"
  | "error"
  | "cancelled";

export interface Entry {
  date: string;
  formatted_date: string;
  day_of_week: string;
  start_time: string; // HH:MM, 24-hour
  end_time: string;
  duration_mins: number;
  billed_hours: number;
}

export interface Summary {
  billed_hours: number;
  gross: number;
  net_estimate: number;
  pay_rate: number;
}

export interface Entries {
  rows: Entry[];
  summary: Summary;
  csv_path: string | null;
}

export interface Issue {
  field: "date" | "start" | "end";
  expected: string;
  got: string | null;
  /** false: mismatch; null: the value could not be confirmed. */
  match: false | null;
}

export interface RowCheck {
  index: number;
  date: string;
  issues: Issue[];
}

export interface Verification {
  rows: RowCheck[];
  all_ok: boolean;
}

export interface Prompt {
  id: string;
  kind: "continue" | "confirm" | "text" | "password";
  message: string;
  /** Set when the prompt belongs inside a step rather than a dialog. */
  stage?: StageId;
  confirm_label?: string;
  cancel_label?: string;
  default?: boolean;
}

export interface LogLine {
  level: "debug" | "info" | "warning" | "error" | "critical" | "stderr";
  message: string;
  time: number; // seconds since the epoch
}
