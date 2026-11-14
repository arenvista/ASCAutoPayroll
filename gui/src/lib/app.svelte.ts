// Application state, fed by bridge events. Live events and the run history a
// reloaded window gets back from `init` both go through `apply`, so the two
// can't drift apart.

import { call, connect, restart } from "./backend";
import type {
  Entries,
  InitResult,
  LogLine,
  Period,
  Prompt,
  RunParams,
  Settings,
  StageId,
  StageStatus,
  Verification,
} from "./types";

const STAGE_LABELS: Record<StageId, string> = {
  trac: "Get TRAC attendance",
  parse: "Round to billable time",
  schedule: "Build from schedule",
  review: "Review entries",
  peoplesoft: "Fill in PeopleSoft",
  verify: "Check the entered rows",
};

/** Steps a dry run (or an empty period) never reaches. */
const LATE_STAGES: StageId[] = ["review", "peoplesoft", "verify"];

const MAX_LOG_LINES = 2000;

export interface Step {
  id: StageId;
  label: string;
  status: StageStatus;
  detail: string | null;
}

export interface RunResult {
  status: "ok" | "aborted" | "error";
  message: string;
}

export class Run {
  readonly params: RunParams;
  steps = $state<Step[]>([]);
  entries = $state<Entries | null>(null);
  progress = $state<{ done: number; total: number } | null>(null);
  verification = $state<Verification | null>(null);
  finished = $state<RunResult | null>(null);

  constructor(params: RunParams) {
    this.params = params;
    const ids: StageId[] =
      params.source === "trac" ? ["trac", "parse", ...LATE_STAGES] : ["schedule", ...LATE_STAGES];
    this.steps = ids.map((id) => ({
      id,
      label: STAGE_LABELS[id],
      status: params.dry_run && LATE_STAGES.includes(id) ? "skipped" : "pending",
      detail: null,
    }));
  }

  get running(): boolean {
    return this.finished === null;
  }

  apply(event: string, data: any): void {
    switch (event) {
      case "stage": {
        const step = this.steps.find((s) => s.id === data.stage);
        if (step) {
          step.status = data.status;
          step.detail = data.detail ?? null;
        }
        break;
      }
      case "entries":
        this.entries = data;
        break;
      case "progress":
        this.progress = data;
        break;
      case "verification":
        this.verification = data;
        break;
      case "run_finished":
        this.finished = data;
        break;
    }
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

class AppState {
  connection = $state<"connecting" | "ready" | "down">("connecting");
  problem = $state<string | null>(null);
  configDir = $state("");
  dataDir = $state("");
  settings = $state<Settings>({ username: "", profile_dir: "", pay_rate: 17.5 });
  periods = $state<Period[]>([]);
  currentPeriod = $state<number | null>(null);
  browserOpen = $state(false);
  run = $state<Run | null>(null);
  /** Open questions from the bridge: inline ones carry a `stage`. */
  prompts = $state<Prompt[]>([]);
  logs = $state<LogLine[]>([]);

  async start(): Promise<void> {
    try {
      await connect({
        event: (name, data) => this.apply(name, data),
        stderr: (line) => this.log("stderr", line),
        exit: (code) => this.lost(code),
      });
      await this.load();
    } catch (error) {
      this.connection = "down";
      this.problem = errorMessage(error);
    }
  }

  async reconnect(): Promise<void> {
    this.connection = "connecting";
    this.problem = null;
    try {
      await restart();
      await this.load();
    } catch (error) {
      this.connection = "down";
      this.problem = errorMessage(error);
    }
  }

  private async load(): Promise<void> {
    const init = await call<InitResult>("init");
    this.configDir = init.config_dir;
    this.dataDir = init.data_dir;
    this.settings = init.settings;
    this.periods = init.periods;
    this.currentPeriod = init.current_period;
    this.browserOpen = init.browser_open;
    this.prompts = [];
    this.run = init.run ? new Run(init.run.params) : null;
    for (const { event, data } of init.run?.events ?? []) this.apply(event, data);
    this.connection = "ready";
  }

  private apply(event: string, data: any): void {
    switch (event) {
      case "log":
        this.log(data.level, data.message, data.time);
        return;
      case "browser":
        this.browserOpen = data.open;
        return;
      case "prompt":
        this.prompts.push(data);
        break;
      case "prompt_closed":
        this.prompts = this.prompts.filter((p) => p.id !== data.id);
        break;
    }
    this.run?.apply(event, data);
  }

  log(level: LogLine["level"], message: string, time = Date.now() / 1000): void {
    this.logs.push({ level, message, time });
    if (this.logs.length > MAX_LOG_LINES) this.logs.splice(0, this.logs.length - MAX_LOG_LINES);
  }

  private lost(code: number | null): void {
    this.connection = "down";
    this.problem =
      code === null
        ? "The payroll backend stopped unexpectedly."
        : `The payroll backend stopped (exit code ${code}).`;
    this.prompts = [];
    this.browserOpen = false;
    if (this.run?.running) {
      this.run.finished = { status: "error", message: "The payroll backend stopped during the run." };
    }
  }

  // -- actions --------------------------------------------------------------

  async startRun(params: RunParams): Promise<void> {
    const run = new Run(params);
    this.prompts = [];
    this.run = run;
    try {
      await call("run", params);
    } catch (error) {
      if (this.run === run) this.run = null;
      throw error;
    }
  }

  async respond(prompt: Prompt, value: unknown): Promise<void> {
    this.prompts = this.prompts.filter((p) => p.id !== prompt.id);
    await call("respond", { prompt_id: prompt.id, value });
  }

  cancelRun(): Promise<unknown> {
    return call("cancel");
  }

  /** Leave a finished run and go back to the form. */
  async newRun(): Promise<void> {
    this.run = null;
    // The app may have been open across a pay-period boundary.
    const { periods, current_period } = await call<{
      periods: Period[];
      current_period: number | null;
    }>("periods");
    this.periods = periods;
    this.currentPeriod = current_period;
  }

  closeBrowser(): Promise<unknown> {
    return call("close_browser");
  }

  async loadSettings(): Promise<void> {
    this.settings = await call<Settings>("settings");
  }

  async saveSettings(values: Omit<Settings, "password">): Promise<void> {
    this.settings = await call<Settings>("save_settings", values);
  }

  async setPassword(password: string): Promise<void> {
    this.settings = await call<Settings>("set_password", { password });
  }

  async forgetPassword(): Promise<void> {
    this.settings = await call<Settings>("forget_password");
  }

  previewSchedule(path: string, start: string, end: string): Promise<Entries> {
    return call<Entries>("preview_schedule", { path, start, end });
  }
}

export const app = new AppState();
