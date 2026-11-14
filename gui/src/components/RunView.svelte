<script lang="ts">
  import { app } from "../lib/app.svelte";
  import RunProgress from "./RunProgress.svelte";
  import RunSetup from "./RunSetup.svelte";

  let { onOpenSettings }: { onOpenSettings: () => void } = $props();
</script>

<div class="page">
  {#if app.run}
    <RunProgress run={app.run} />
  {:else}
    <RunSetup {onOpenSettings} />
  {/if}
</div>

<style>
  .page {
    max-width: 1040px;
    margin: 0 auto;
  }
</style>
