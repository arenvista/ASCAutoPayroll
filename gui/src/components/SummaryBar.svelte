<script lang="ts">
  import { hours, usd } from "../lib/format";
  import type { Summary } from "../lib/types";

  let { summary, count }: { summary: Summary; count: number } = $props();
</script>

<div class="tiles">
  <div class="tile">
    <span class="name">Billed hours</span>
    <span class="value num">{hours(summary.billed_hours)}</span>
    <span class="sub">{count} {count === 1 ? "entry" : "entries"}</span>
  </div>
  <div class="tile">
    <span class="name">Gross pay</span>
    <span class="value num">{usd(summary.gross)}</span>
    <span class="sub num">at {usd(summary.pay_rate)}/h</span>
  </div>
  <div class="tile">
    <span class="name">Estimated take-home</span>
    <span class="value num">≈ {usd(summary.net_estimate)}</span>
    <span class="sub">rough guess after withholding</span>
  </div>
</div>

<style>
  .tiles {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px;
  }

  .tile {
    display: grid;
    gap: 2px;
    padding: 12px 14px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }

  .name {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-3);
  }

  .value {
    font-size: 21px;
    font-weight: 650;
    letter-spacing: -0.01em;
  }

  .sub {
    font-size: 12px;
    color: var(--text-3);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
