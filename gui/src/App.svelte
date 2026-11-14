<script lang="ts">
  import { getCurrentWindow } from "@tauri-apps/api/window";
  import { ask } from "@tauri-apps/plugin-dialog";
  import { onMount } from "svelte";
  import Icon from "./components/Icon.svelte";
  import LogPanel from "./components/LogPanel.svelte";
  import PromptDialog from "./components/PromptDialog.svelte";
  import RunView from "./components/RunView.svelte";
  import SettingsView from "./components/SettingsView.svelte";
  import { app, errorMessage } from "./lib/app.svelte";

  let tab = $state<"run" | "settings">("run");
  let closingBrowser = $state(false);

  const dialogPrompt = $derived(app.prompts.find((p) => !p.stage) ?? null);

  onMount(() => {
    app.start();
    // Quitting closes Firefox too (the bridge quits it on the way out), so
    // check first if that would interrupt a run or an unsubmitted timesheet.
    const unlisten = getCurrentWindow().onCloseRequested(async (event) => {
      const running = app.run?.running ?? false;
      if (!running && !app.browserOpen) return;
      const quit = await ask(
        running
          ? "A run is still in progress. Quitting stops it and closes Firefox."
          : "Firefox will close too. Make sure you've submitted your timesheet first.",
        { title: "Quit AutoPayroll?", kind: "warning", okLabel: "Quit", cancelLabel: "Keep open" },
      );
      if (!quit) event.preventDefault();
    });
    return () => {
      unlisten.then((stop) => stop());
    };
  });

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
</script>

<div class="shell">
  <header class="topbar">
    <div class="brand">
      <svg class="logo" viewBox="0 0 1024 1024" aria-hidden="true">
        <rect x="64" y="64" width="896" height="896" rx="200" fill="#1b1c20" />
        <circle cx="512" cy="512" r="280" fill="none" stroke="#fdb515" stroke-width="72" />
        <path
          d="M512 380 V512 L600 575"
          fill="none"
          stroke="#fff"
          stroke-width="64"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
      <span>AutoPayroll</span>
    </div>

    <nav class="tabs" aria-label="Sections">
      <button
        class:active={tab === "run"}
        aria-current={tab === "run" ? "page" : undefined}
        onclick={() => (tab = "run")}
      >
        Run
      </button>
      <button
        class:active={tab === "settings"}
        aria-current={tab === "settings" ? "page" : undefined}
        onclick={() => (tab = "settings")}
      >
        Settings
      </button>
    </nav>

    {#if app.browserOpen}
      <div class="browser" title="The Firefox window this app is driving">
        <span class="live"></span>
        Firefox open
        <button
          class="btn quiet small"
          disabled={closingBrowser || (app.run?.running ?? false)}
          onclick={closeBrowser}
        >
          Close
        </button>
      </div>
    {/if}
  </header>

  <main>
    {#if app.connection === "connecting"}
      <div class="center">
        <Icon name="spinner" size={22} />
        <p>Starting the payroll engine…</p>
      </div>
    {:else if app.connection === "down"}
      <div class="center">
        <div class="card problem">
          <Icon name="alert" size={22} />
          <h2>The payroll engine isn't running</h2>
          <p class="selectable">{app.problem}</p>
          <p class="hint">The log below may say why.</p>
          <button class="btn primary" onclick={() => app.reconnect()}>
            <Icon name="refresh" />
            Restart
          </button>
        </div>
      </div>
    {:else if tab === "run"}
      <RunView onOpenSettings={() => (tab = "settings")} />
    {:else}
      <SettingsView />
    {/if}
  </main>

  <LogPanel />
</div>

{#if dialogPrompt}
  {#key dialogPrompt.id}
    <PromptDialog prompt={dialogPrompt} />
  {/key}
{/if}

<style>
  .shell {
    display: grid;
    grid-template-rows: auto minmax(0, 1fr) auto;
    height: 100vh;
  }

  .topbar {
    display: flex;
    align-items: center;
    gap: 22px;
    height: 52px;
    padding: 0 18px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 9px;
    font-weight: 650;
    font-size: 15px;
    letter-spacing: -0.01em;
  }

  .logo {
    width: 26px;
    height: 26px;
  }

  .tabs {
    display: flex;
    gap: 2px;
    height: 100%;
  }

  .tabs button {
    position: relative;
    padding: 0 12px;
    border: 0;
    background: none;
    color: var(--text-2);
    font-weight: 550;
    cursor: pointer;
  }

  .tabs button:hover,
  .tabs button.active {
    color: var(--text);
  }

  .tabs button.active::after {
    content: "";
    position: absolute;
    left: 10px;
    right: 10px;
    bottom: -1px;
    height: 2px;
    border-radius: 2px;
    background: var(--accent);
  }

  .browser {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-left: auto;
    padding: 0 4px 0 12px;
    height: 32px;
    border: 1px solid var(--border);
    border-radius: 999px;
    font-size: 13px;
    color: var(--text-2);
  }

  .live {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--ok);
    box-shadow: 0 0 0 3px var(--ok-soft);
  }

  main {
    overflow: auto;
    padding: 24px;
  }

  .center {
    display: grid;
    place-items: center;
    align-content: center;
    gap: 12px;
    min-height: 100%;
    color: var(--text-2);
  }

  .problem {
    display: grid;
    justify-items: center;
    gap: 10px;
    max-width: 440px;
    padding: 28px;
    text-align: center;
    color: var(--danger);
  }

  .problem h2 {
    font-size: 16px;
    color: var(--text);
  }

  .problem p {
    color: var(--text-2);
  }
</style>
