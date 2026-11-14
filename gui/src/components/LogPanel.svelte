<script lang="ts">
  import { tick } from "svelte";
  import { app } from "../lib/app.svelte";
  import type { LogLine } from "../lib/types";
  import Icon from "./Icon.svelte";

  let open = $state(false);
  let copied = $state(false);
  let list = $state<HTMLElement>();
  // Lines already seen, so the problem badge only counts new ones.
  let seen = $state(0);

  const problems = $derived(
    app.logs.slice(seen).filter((l) => l.level === "error" || l.level === "critical").length,
  );

  // Follow the newest line while the panel is open.
  $effect(() => {
    void app.logs.length;
    if (!open) return;
    seen = app.logs.length;
    tick().then(() => list?.scrollTo({ top: list.scrollHeight }));
  });

  function stamp(line: LogLine): string {
    return new Date(line.time * 1000).toLocaleTimeString([], { hour12: false });
  }

  async function copy() {
    const text = app.logs.map((l) => `${stamp(l)} ${l.level.toUpperCase()} ${l.message}`).join("\n");
    try {
      await navigator.clipboard.writeText(text);
      copied = true;
      setTimeout(() => (copied = false), 1500);
    } catch {
      app.log("warning", "Couldn't copy the log to the clipboard.");
    }
  }

  function clear() {
    app.logs = [];
    seen = 0;
  }
</script>

<footer class:open>
  <div class="bar">
    <button class="toggle" aria-expanded={open} onclick={() => (open = !open)}>
      <Icon name="terminal" size={14} />
      Log
      {#if problems && !open}<span class="badge">{problems}</span>{/if}
      <Icon name={open ? "chevronDown" : "chevronUp"} size={14} />
    </button>
    {#if open}
      <div class="tools">
        <button class="btn quiet small" onclick={copy}>
          <Icon name={copied ? "check" : "copy"} size={14} />
          {copied ? "Copied" : "Copy"}
        </button>
        <button class="btn quiet small" onclick={clear}><Icon name="trash" size={14} /> Clear</button>
      </div>
    {/if}
  </div>

  {#if open}
    <div class="lines selectable" bind:this={list}>
      {#each app.logs as line, i (i)}
        <div class="line {line.level}">
          <time>{stamp(line)}</time>
          <span>{line.message}</span>
        </div>
      {:else}
        <p class="empty">Nothing logged yet.</p>
      {/each}
    </div>
  {/if}
</footer>

<style>
  footer {
    border-top: 1px solid var(--border);
    background: var(--surface);
  }

  .bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 34px;
    padding: 0 10px;
  }

  .toggle {
    display: flex;
    align-items: center;
    gap: 7px;
    height: 26px;
    padding: 0 8px;
    border: 0;
    border-radius: 6px;
    background: none;
    color: var(--text-2);
    font-size: 13px;
    font-weight: 550;
    cursor: pointer;
  }

  .toggle:hover {
    background: var(--surface-3);
    color: var(--text);
  }

  .badge {
    min-width: 18px;
    padding: 0 5px;
    border-radius: 999px;
    background: var(--danger);
    color: #fff;
    font-size: 11px;
    line-height: 18px;
    text-align: center;
  }

  .tools {
    display: flex;
    gap: 4px;
  }

  .lines {
    height: 200px;
    overflow: auto;
    padding: 6px 14px 10px;
    border-top: 1px solid var(--border);
    background: var(--surface-2);
    font: 12.5px/1.55 var(--mono);
  }

  .line {
    display: flex;
    gap: 12px;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  time {
    flex: none;
    color: var(--text-3);
  }

  .debug,
  .stderr {
    color: var(--text-3);
  }

  .warning {
    color: var(--warn);
  }

  .error,
  .critical {
    color: var(--danger);
  }

  .empty {
    color: var(--text-3);
  }
</style>
