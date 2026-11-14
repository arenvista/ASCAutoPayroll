<script lang="ts">
  import { open } from "@tauri-apps/plugin-dialog";
  import { app, errorMessage } from "../lib/app.svelte";
  import { basename, hours, periodRange, usd } from "../lib/format";
  import type { Entries, Source } from "../lib/types";
  import EntriesTable from "./EntriesTable.svelte";
  import Icon from "./Icon.svelte";
  import SummaryBar from "./SummaryBar.svelte";

  let { onOpenSettings }: { onOpenSettings: () => void } = $props();

  // Per-machine conveniences; the form works the same without them.
  const SOURCE_KEY = "autopayroll.source";
  const SCHEDULE_KEY = "autopayroll.schedulePath";

  function remembered(key: string): string | null {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  }

  function remember(key: string, value: string): void {
    try {
      localStorage.setItem(key, value);
    } catch {
      // Not worth interrupting a run over.
    }
  }

  let period = $state<number | null>(app.currentPeriod ?? app.periods.at(-1)?.period ?? null);
  let source = $state<Source>(remembered(SOURCE_KEY) === "schedule" ? "schedule" : "trac");
  let schedulePath = $state(remembered(SCHEDULE_KEY) ?? "");
  let dryRun = $state(false);
  let starting = $state(false);
  let error = $state<string | null>(null);
  let preview = $state<Entries | null>(null);
  let previewError = $state<string | null>(null);

  const selected = $derived(app.periods.find((p) => p.period === period) ?? null);
  const needsBrowser = $derived(source === "trac" || !dryRun);
  const missing = $derived(
    [
      !app.settings.username && "your UMBC username",
      !app.settings.profile_dir && "a Firefox profile",
    ].filter(Boolean) as string[],
  );
  const canStart = $derived(
    !!selected && !starting && (source === "trac" || (!!schedulePath && !previewError)),
  );

  // Keep a live preview of what the schedule expands to for this period.
  $effect(() => {
    if (source !== "schedule" || !schedulePath || !selected) {
      preview = null;
      previewError = null;
      return;
    }
    let stale = false;
    app.previewSchedule(schedulePath, selected.start, selected.end).then(
      (entries) => {
        if (stale) return;
        preview = entries;
        previewError = null;
      },
      (failure) => {
        if (stale) return;
        preview = null;
        previewError = errorMessage(failure);
      },
    );
    return () => {
      stale = true;
    };
  });

  async function chooseSchedule() {
    const picked = await open({
      title: "Choose a schedule CSV",
      filters: [{ name: "CSV", extensions: ["csv"] }],
      multiple: false,
      directory: false,
    });
    if (typeof picked === "string") {
      schedulePath = picked;
      remember(SCHEDULE_KEY, picked);
    }
  }

  async function start() {
    if (!selected) return;
    starting = true;
    error = null;
    remember(SOURCE_KEY, source);
    try {
      await app.startRun({
        source,
        start: selected.start,
        end: selected.end,
        dry_run: dryRun,
        schedule_path: source === "schedule" ? schedulePath : null,
      });
    } catch (failure) {
      error = errorMessage(failure);
    } finally {
      starting = false;
    }
  }
</script>

<section class="card setup">
  <div class="intro">
    <h1>New timesheet run</h1>
    <p>Pick a pay period and where your hours come from. You'll review every entry before anything is typed into PeopleSoft.</p>
  </div>

  <div class="field">
    <label for="period">Pay period</label>
    <select id="period" class="input num" bind:value={period}>
      {#each app.periods as p (p.period)}
        <option value={p.period}>
          {periodRange(p.start, p.end)}{p.period === app.currentPeriod ? "  ·  current" : ""}
        </option>
      {/each}
    </select>
  </div>

  <fieldset class="field">
    <legend>Hours from</legend>
    <div class="choices">
      <label class="choice" class:selected={source === "trac"}>
        <input type="radio" name="source" value="trac" bind:group={source} />
        <span class="choice-title"><Icon name="globe" /> TRAC attendance</span>
        <span class="choice-text">Scrape your visits from TRAC Cloud and round them to billable time.</span>
      </label>
      <label class="choice" class:selected={source === "schedule"}>
        <input type="radio" name="source" value="schedule" bind:group={source} />
        <span class="choice-title"><Icon name="calendar" /> Weekly schedule</span>
        <span class="choice-text">Enter fixed shifts from a CSV, exactly as written. TRAC isn't used.</span>
      </label>
    </div>
  </fieldset>

  {#if source === "schedule"}
    <div class="field">
      <span class="label">Schedule CSV</span>
      <div class="file">
        <Icon name="file" />
        <span class="path" class:empty={!schedulePath} title={schedulePath}>
          {schedulePath ? basename(schedulePath) : "No file chosen"}
        </span>
        <button class="btn small" onclick={chooseSchedule}>Choose…</button>
      </div>
      {#if previewError}
        <div class="alert error"><Icon name="alert" /><span>{previewError}</span></div>
      {:else if preview}
        <p class="found num">
          <Icon name="check" size={14} />
          {preview.rows.length} shifts this period · {hours(preview.summary.billed_hours)} ·
          {usd(preview.summary.gross)} gross
        </p>
      {:else}
        <p class="hint">
          Columns <code>day,start,stop</code>, plus an optional <code>week</code> (1 or 2) when the
          two weeks differ.
        </p>
      {/if}
    </div>
  {/if}

  <label class="check">
    <input type="checkbox" bind:checked={dryRun} />
    <span>
      <strong>Dry run</strong>
      <span class="hint">Build and save the entries, then stop before PeopleSoft.</span>
    </span>
  </label>

  {#if needsBrowser && missing.length}
    <div class="alert info">
      <Icon name="info" />
      <span>
        Add {missing.join(" and ")} in
        <button class="link" onclick={onOpenSettings}>Settings</button> to sign in automatically. Otherwise
        you'll be asked as you go.
      </span>
    </div>
  {/if}

  {#if error}
    <div class="alert error"><Icon name="alert" /><span>{error}</span></div>
  {/if}

  <div class="actions">
    <button class="btn primary start" disabled={!canStart} onclick={start}>
      {#if starting}<Icon name="spinner" />{:else}<Icon name="play" />{/if}
      {dryRun ? "Start dry run" : "Start"}
    </button>
  </div>
</section>

{#if source === "schedule" && preview}
  <section class="preview">
    <h2>Preview</h2>
    <SummaryBar summary={preview.summary} count={preview.rows.length} />
    <div class="card table-wrap">
      <EntriesTable rows={preview.rows} />
    </div>
  </section>
{/if}

<style>
  .setup {
    display: grid;
    gap: 20px;
    max-width: 680px;
    margin: 0 auto;
    padding: 26px 28px;
  }

  .intro {
    display: grid;
    gap: 6px;
  }

  h1 {
    font-size: 19px;
    letter-spacing: -0.01em;
  }

  .intro p {
    color: var(--text-2);
  }

  .choices {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }

  .choice {
    position: relative;
    display: grid;
    gap: 4px;
    padding: 13px 14px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    cursor: pointer;
  }

  .choice:hover {
    background: var(--surface-2);
  }

  .choice.selected {
    border-color: var(--accent-line);
    background: var(--accent-soft);
    box-shadow: inset 0 0 0 1px var(--accent-line);
  }

  .choice input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }

  .choice:has(input:focus-visible) {
    outline: 2px solid var(--focus);
    outline-offset: 2px;
  }

  .choice-title {
    display: flex;
    align-items: center;
    gap: 7px;
    font-weight: 600;
  }

  .choice-text {
    font-size: 13px;
    color: var(--text-2);
  }

  .file {
    display: flex;
    align-items: center;
    gap: 9px;
    height: 40px;
    padding: 0 6px 0 11px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    color: var(--text-2);
  }

  .path {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--text);
    font-weight: 500;
  }

  .path.empty {
    color: var(--text-3);
    font-weight: 400;
  }

  .found {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: var(--ok);
  }

  .check {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    cursor: pointer;
  }

  .check input {
    width: 16px;
    height: 16px;
    margin: 2px 0 0;
    accent-color: var(--accent-hover);
  }

  .check > span {
    display: grid;
    gap: 1px;
  }

  .link {
    padding: 0;
    border: 0;
    background: none;
    color: inherit;
    font-weight: 600;
    text-decoration: underline;
    cursor: pointer;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
  }

  .start {
    min-width: 132px;
    height: 38px;
  }

  .preview {
    display: grid;
    gap: 12px;
    max-width: 680px;
    margin: 28px auto 0;
  }

  .preview h2 {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-2);
  }

  .table-wrap {
    overflow-x: auto;
  }

  @media (max-width: 640px) {
    .choices {
      grid-template-columns: 1fr;
    }
  }
</style>
