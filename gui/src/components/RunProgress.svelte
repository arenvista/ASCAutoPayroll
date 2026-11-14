<script lang="ts">
  import { openPath } from "@tauri-apps/plugin-opener";
  import { app, errorMessage, type Run, type Step } from "../lib/app.svelte";
  import { basename, periodRange } from "../lib/format";
  import type { Prompt } from "../lib/types";
  import EntriesTable from "./EntriesTable.svelte";
  import Icon, { type IconName } from "./Icon.svelte";
  import SummaryBar from "./SummaryBar.svelte";

  let { run }: { run: Run } = $props();

  let cancelling = $state(false);
  let answering = $state(false);
  let closingBrowser = $state(false);

  const STEP_ICONS: Record<Step["status"], IconName> = {
    pending: "circle",
    active: "spinner",
    waiting: "hand",
    done: "check",
    skipped: "minus",
    error: "x",
    cancelled: "ban",
  };

  const inlinePrompt = $derived(app.prompts.find((p) => p.stage) ?? null);
  const entering = $derived(
    run.steps.find((s) => s.id === "peoplesoft")?.status === "active" && run.progress !== null,
  );
  const source = $derived(
    run.params.source === "trac"
      ? "TRAC attendance"
      : `Schedule · ${basename(run.params.schedule_path ?? "")}`,
  );

  function stepDetail(step: Step): string | null {
    switch (step.status) {
      case "waiting":
        return "Waiting for you";
      case "active":
        if (step.id === "peoplesoft" && run.progress) {
          return `Row ${run.progress.done} of ${run.progress.total}`;
        }
        return step.detail ?? "Working…";
      case "skipped":
        return run.params.dry_run ? "Skipped (dry run)" : "Skipped";
      case "error":
        return "Failed";
      case "cancelled":
        return "Cancelled";
      case "done":
        if ((step.id === "parse" || step.id === "schedule") && run.entries) {
          const n = run.entries.rows.length;
          return `${n} ${n === 1 ? "entry" : "entries"}`;
        }
        if (step.id === "peoplesoft" && run.progress) return `${run.progress.total} rows entered`;
        if (step.id === "verify" && run.verification) {
          return run.verification.all_ok ? "Everything matches" : "Some fields need a look";
        }
        return null;
      default:
        return null;
    }
  }

  type Banner = { tone: "ok" | "warn" | "info" | "error"; icon: IconName; title: string };

  const banner = $derived.by((): Banner | null => {
    const result = run.finished;
    if (!result) return null;
    if (result.status === "error") return { tone: "error", icon: "alert", title: "The run stopped" };
    if (result.status === "aborted") return { tone: "info", icon: "ban", title: "Run cancelled" };
    if (run.params.dry_run) return { tone: "ok", icon: "check", title: "Dry run complete" };
    if (!run.entries?.rows.length) return { tone: "info", icon: "info", title: "Nothing to enter" };
    if (run.verification && !run.verification.all_ok) {
      return { tone: "warn", icon: "alert", title: "Entered, but some fields didn't match" };
    }
    return { tone: "ok", icon: "check", title: "Entered into PeopleSoft" };
  });

  async function cancel() {
    cancelling = true;
    try {
      await app.cancelRun();
    } catch (error) {
      app.log("error", errorMessage(error));
    }
  }

  async function answer(prompt: Prompt, value: boolean) {
    answering = true;
    try {
      await app.respond(prompt, value);
    } catch (error) {
      app.log("error", errorMessage(error));
    } finally {
      answering = false;
    }
  }

  async function closeBrowser() {
    closingBrowser = true;
    try {
      await app.closeBrowser();
    } catch (error) {
      app.log("error", errorMessage(error));
    } finally {
      closingBrowser = false;
    }
  }

  async function reveal(path: string) {
    try {
      await openPath(path);
    } catch (error) {
      app.log("error", `Could not open ${path}: ${errorMessage(error)}`);
    }
  }
</script>

<header class="head">
  <div>
    <h1 class="num">{periodRange(run.params.start, run.params.end)}</h1>
    <p class="sub">
      {source}{#if run.params.dry_run}<span class="tag">Dry run</span>{/if}
    </p>
  </div>
  {#if run.running}
    <button class="btn" disabled={cancelling} onclick={cancel}>
      {#if cancelling}<Icon name="spinner" /> Cancelling…{:else}Cancel run{/if}
    </button>
  {:else}
    <button class="btn primary" onclick={() => app.newRun()}>New run</button>
  {/if}
</header>

<div class="layout">
  <ol class="steps">
    {#each run.steps as step (step.id)}
      {@const detail = stepDetail(step)}
      <li class="step {step.status}" aria-current={step.status === "active" || step.status === "waiting" ? "step" : undefined}>
        <span class="icon"><Icon name={STEP_ICONS[step.status]} size={14} /></span>
        <span class="text">
          <span class="label">{step.label}</span>
          {#if detail}<span class="detail">{detail}</span>{/if}
        </span>
      </li>
    {/each}
  </ol>

  <div class="panel">
    {#if banner && run.finished}
      <div class="banner {banner.tone}">
        <Icon name={banner.icon} size={18} />
        <div class="banner-text">
          <strong>{banner.title}</strong>
          <span class="selectable">{run.finished.message}</span>
          {#if run.finished.status === "error"}<span class="hint">The log below has details.</span>{/if}
        </div>
        {#if app.browserOpen && !run.params.dry_run && run.finished.status === "ok"}
          <button class="btn small" disabled={closingBrowser} onclick={closeBrowser}>Close Firefox</button>
        {/if}
      </div>
    {/if}

    {#if inlinePrompt}
      {@const review = inlinePrompt.stage === "review"}
      <div class="action" class:review>
        <span class="action-icon"><Icon name={review ? "file" : "hand"} size={18} /></span>
        <div class="action-text">
          <strong>{review ? inlinePrompt.message : "Over to you in Firefox"}</strong>
          <span>
            {review
              ? "Firefox opens your timesheet and types each row in. Nothing is submitted: you check it and submit it yourself."
              : inlinePrompt.message}
          </span>
        </div>
        <div class="action-buttons">
          <button class="btn" disabled={answering} onclick={() => answer(inlinePrompt, false)}>
            {inlinePrompt.cancel_label ?? "Cancel run"}
          </button>
          <button class="btn primary" disabled={answering} onclick={() => answer(inlinePrompt, true)}>
            {inlinePrompt.confirm_label ?? "Continue"}
          </button>
        </div>
      </div>
    {/if}

    {#if entering && run.progress}
      <div class="entering">
        <div class="entering-text">
          <span>Typing rows into PeopleSoft. Leave the Firefox window alone until it's done.</span>
          <span class="num">{run.progress.done} / {run.progress.total}</span>
        </div>
        <progress max={run.progress.total} value={run.progress.done}></progress>
      </div>
    {/if}

    {#if run.entries}
      <SummaryBar summary={run.entries.summary} count={run.entries.rows.length} />
      {#if run.entries.rows.length}
        <div class="card table-wrap">
          <EntriesTable
            rows={run.entries.rows}
            checks={run.verification?.rows ?? null}
            entered={run.progress?.done ?? null}
            showVisit={run.params.source === "trac"}
          />
        </div>
      {/if}
      {#if run.entries.csv_path}
        <p class="saved">
          <Icon name="file" size={14} />
          <span>Saved as <span class="selectable">{basename(run.entries.csv_path)}</span></span>
          <button class="btn quiet small" onclick={() => reveal(run.entries!.csv_path!)}>Open</button>
          <button class="btn quiet small" onclick={() => reveal(app.dataDir)}>Show folder</button>
        </p>
      {/if}
    {:else if run.running && !inlinePrompt}
      <div class="placeholder">
        <Icon name="spinner" size={20} />
        <span>{run.steps.find((s) => s.status === "active")?.detail ?? "Working…"}</span>
      </div>
    {/if}
  </div>
</div>

<style>
  .head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 22px;
  }

  h1 {
    font-size: 19px;
    letter-spacing: -0.01em;
  }

  .sub {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 3px;
    color: var(--text-2);
  }

  .tag {
    padding: 1px 7px;
    border-radius: 999px;
    background: var(--accent-soft);
    color: var(--warn);
    font-size: 12px;
    font-weight: 600;
  }

  .layout {
    display: grid;
    grid-template-columns: 230px minmax(0, 1fr);
    gap: 26px;
    align-items: start;
  }

  .steps {
    position: sticky;
    top: 0;
    display: grid;
    gap: 2px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .step {
    position: relative;
    display: flex;
    gap: 11px;
    padding: 8px 0;
  }

  /* The line joining one step's marker to the next. */
  .step:not(:last-child)::after {
    content: "";
    position: absolute;
    left: 11px;
    top: 34px;
    bottom: -8px;
    width: 2px;
    border-radius: 1px;
    background: var(--border);
  }

  .step.done:not(:last-child)::after {
    background: var(--ok);
    opacity: 0.45;
  }

  .icon {
    display: grid;
    place-items: center;
    flex: none;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    border: 1.5px solid var(--border-strong);
    background: var(--surface);
    color: var(--text-3);
  }

  .done .icon {
    border-color: var(--ok);
    background: var(--ok);
    color: var(--surface);
  }

  .active .icon {
    border-color: var(--accent-line);
    color: var(--text);
  }

  .waiting .icon {
    border-color: var(--accent-hover);
    background: var(--accent);
    color: var(--accent-ink);
  }

  .error .icon {
    border-color: var(--danger);
    background: var(--danger);
    color: var(--surface);
  }

  .skipped .icon,
  .cancelled .icon {
    border-style: dashed;
  }

  .text {
    display: grid;
    gap: 1px;
    padding-top: 2px;
    min-width: 0;
  }

  .label {
    font-weight: 550;
  }

  .pending .label,
  .skipped .label,
  .cancelled .label {
    color: var(--text-3);
  }

  .detail {
    font-size: 12.5px;
    color: var(--text-3);
  }

  .waiting .detail {
    color: var(--warn);
    font-weight: 600;
  }

  .error .detail {
    color: var(--danger);
  }

  .panel {
    display: grid;
    gap: 14px;
    min-width: 0;
  }

  .banner {
    display: flex;
    gap: 12px;
    align-items: flex-start;
    padding: 14px 16px;
    border-radius: var(--radius);
  }

  .banner.ok {
    background: var(--ok-soft);
    color: var(--ok);
  }

  .banner.warn {
    background: var(--warn-soft);
    color: var(--warn);
  }

  .banner.info {
    background: var(--surface-3);
    color: var(--text-2);
  }

  .banner.error {
    background: var(--danger-soft);
    color: var(--danger);
  }

  .banner-text {
    display: grid;
    gap: 2px;
    flex: 1;
  }

  .banner-text strong {
    color: var(--text);
  }

  .banner-text span {
    color: var(--text-2);
  }

  .action {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 6px 12px;
    padding: 16px 18px;
    border: 1px solid var(--accent-line);
    border-radius: var(--radius);
    background: var(--accent-soft);
  }

  .action-icon {
    display: grid;
    place-items: center;
    width: 34px;
    height: 34px;
    border-radius: 50%;
    background: var(--accent);
    color: var(--accent-ink);
  }

  .action-text {
    display: grid;
    gap: 3px;
    align-self: center;
  }

  .action-text span {
    color: var(--text-2);
  }

  .action-buttons {
    grid-column: 2;
    display: flex;
    gap: 8px;
    justify-content: flex-end;
    margin-top: 6px;
  }

  .entering {
    display: grid;
    gap: 8px;
    padding: 14px 16px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
  }

  .entering-text {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    color: var(--text-2);
  }

  progress {
    width: 100%;
    height: 6px;
    appearance: none;
    border: 0;
    border-radius: 3px;
    background: var(--surface-3);
    overflow: hidden;
  }

  progress::-webkit-progress-bar {
    background: var(--surface-3);
  }

  progress::-webkit-progress-value {
    background: var(--accent);
    transition: width 0.3s;
  }

  .table-wrap {
    overflow-x: auto;
  }

  .saved {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: var(--text-3);
  }

  .saved > span {
    margin-right: 4px;
  }

  .placeholder {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 36px;
    justify-content: center;
    border: 1px dashed var(--border-strong);
    border-radius: var(--radius);
    color: var(--text-2);
  }

  /* Narrow windows: the steps become a compact row above the panel. */
  @media (max-width: 860px) {
    .layout {
      grid-template-columns: 1fr;
      gap: 18px;
    }

    .steps {
      position: static;
      display: flex;
    }

    .step {
      flex: 1;
      flex-direction: column;
      align-items: center;
      gap: 6px;
      padding: 0 4px;
      text-align: center;
    }

    .step:not(:last-child)::after {
      top: 11px;
      bottom: auto;
      left: calc(50% + 18px);
      right: calc(-50% + 18px);
      width: auto;
      height: 2px;
    }

    .label {
      font-size: 12px;
    }

    .detail {
      display: none;
    }
  }
</style>
