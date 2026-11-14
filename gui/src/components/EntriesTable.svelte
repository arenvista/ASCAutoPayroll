<script lang="ts">
  import { clock, hours, minutes, shortDate, weekday } from "../lib/format";
  import type { Entry, Issue, RowCheck } from "../lib/types";
  import Icon from "./Icon.svelte";

  let {
    rows,
    checks = null,
    entered = null,
    showVisit = false,
  }: {
    rows: Entry[];
    /** Read-back results from PeopleSoft, one per row. */
    checks?: RowCheck[] | null;
    /** How many rows have been typed in so far, while entering. */
    entered?: number | null;
    /** Show the visit's real length (TRAC rows are rounded). */
    showVisit?: boolean;
  } = $props();

  const FIELD_NAMES = { date: "Date", start: "Start", end: "End" } as const;
  const showStatus = $derived(checks !== null || entered !== null);

  function rowState(index: number): "ok" | "mismatch" | "unconfirmed" | "entered" | "pending" {
    const check = checks?.find((c) => c.index === index);
    if (check) {
      if (check.issues.some((i) => i.match === false)) return "mismatch";
      return check.issues.length ? "unconfirmed" : "ok";
    }
    return entered !== null && index < entered ? "entered" : "pending";
  }

  function describe(issue: Issue): string {
    const expected = issue.field === "date" ? issue.expected : clock(issue.expected);
    const got = issue.got ? `“${issue.got}”` : "nothing";
    return issue.match === false
      ? `${FIELD_NAMES[issue.field]}: expected ${expected}, PeopleSoft shows ${got}`
      : `${FIELD_NAMES[issue.field]}: couldn't confirm (PeopleSoft shows ${got})`;
  }
</script>

<table class="table">
  <thead>
    <tr>
      <th>Date</th>
      <th>Start</th>
      <th>End</th>
      <th class="right">Hours</th>
      {#if showVisit}<th class="right" title="Actual visit length in TRAC">Visit</th>{/if}
      {#if showStatus}<th class="status-col"><span class="sr-only">Status</span></th>{/if}
    </tr>
  </thead>
  <tbody>
    {#each rows as row, i (i)}
      {@const state = rowState(i)}
      {@const issues = checks?.find((c) => c.index === i)?.issues ?? []}
      <tr class={state}>
        <td><span class="day">{weekday(row.date)}</span> {shortDate(row.date)}</td>
        <td>{clock(row.start_time)}</td>
        <td>{clock(row.end_time)}</td>
        <td class="right">{hours(row.billed_hours)}</td>
        {#if showVisit}<td class="right muted">{minutes(row.duration_mins)}</td>{/if}
        {#if showStatus}
          <td class="status-col">
            {#if state === "ok"}
              <span class="mark ok"><Icon name="check" size={15} label="Matches" /></span>
            {:else if state === "mismatch"}
              <span class="mark bad"><Icon name="x" size={15} label="Doesn't match" /></span>
            {:else if state === "unconfirmed"}
              <span class="mark unsure" title="Couldn't confirm">?</span>
            {:else if state === "entered"}
              <span class="mark" title="Entered"><span class="typed-dot"></span></span>
            {/if}
          </td>
        {/if}
      </tr>
      {#if issues.length}
        <tr class="issues">
          <td colspan={4 + (showVisit ? 1 : 0) + (showStatus ? 1 : 0)}>
            {#each issues as issue}
              <div class:bad={issue.match === false}>{describe(issue)}</div>
            {/each}
          </td>
        </tr>
      {/if}
    {/each}
  </tbody>
</table>

<style>
  .day {
    display: inline-block;
    width: 34px;
    color: var(--text-3);
  }

  .muted {
    color: var(--text-3);
  }

  .status-col {
    width: 40px;
    text-align: center;
  }

  .mark {
    display: inline-grid;
    place-items: center;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    font-weight: 700;
    font-size: 13px;
  }

  .mark.ok {
    color: var(--ok);
    background: var(--ok-soft);
  }

  .mark.bad {
    color: var(--danger);
    background: var(--danger-soft);
  }

  .mark.unsure {
    color: var(--warn);
    background: var(--warn-soft);
  }

  .typed-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--accent-hover);
  }

  tr.mismatch td,
  tr.mismatch + tr.issues td {
    background: color-mix(in srgb, var(--danger-soft) 55%, transparent);
  }

  tr:has(+ tr.issues) td {
    border-bottom: 0;
  }

  tr.issues td {
    padding-top: 0;
    font-size: 13px;
    white-space: normal;
    color: var(--warn);
    user-select: text;
  }

  tr.issues .bad {
    color: var(--danger);
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
  }
</style>
