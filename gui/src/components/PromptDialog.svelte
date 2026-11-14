<script lang="ts">
  import { onMount } from "svelte";
  import { app, errorMessage } from "../lib/app.svelte";
  import type { Prompt } from "../lib/types";
  import Icon from "./Icon.svelte";

  // Questions the pipeline asks outside any step: so far, the sign-in
  // details it needs and hasn't been given.
  let { prompt }: { prompt: Prompt } = $props();

  let dialog: HTMLDialogElement;
  let value = $state("");
  let sending = $state(false);

  const asksForText = $derived(prompt.kind === "text" || prompt.kind === "password");
  const label = $derived(prompt.message.replace(/:\s*$/, ""));

  onMount(() => dialog.showModal());

  async function reply(answer: unknown) {
    sending = true;
    try {
      await app.respond(prompt, answer);
    } catch (error) {
      app.log("error", errorMessage(error));
    }
  }

  function submit(event: SubmitEvent) {
    event.preventDefault();
    if (asksForText && !value) return;
    reply(asksForText ? value : true);
  }

  // Declining to give a username or password ends the run. Cancel it outright:
  // answering with nothing would surface as a sign-in error, not a cancel.
  async function cancelRun() {
    sending = true;
    try {
      await app.cancelRun();
    } catch (error) {
      app.log("error", errorMessage(error));
    }
  }

  function dismiss(event: Event) {
    event.preventDefault(); // Escape: answer instead of leaving it open
    if (asksForText) cancelRun();
    else reply(false);
  }
</script>

<dialog bind:this={dialog} oncancel={dismiss} aria-labelledby="prompt-title">
  <form onsubmit={submit}>
    <div class="head">
      <span class="badge"><Icon name="key" size={18} /></span>
      <h2 id="prompt-title">UMBC sign-in</h2>
    </div>

    {#if asksForText}
      <label class="field">
        <span class="label">{label}</span>
        <!-- svelte-ignore a11y_autofocus -->
        <input
          class="input"
          type={prompt.kind === "password" ? "password" : "text"}
          autocomplete="off"
          spellcheck="false"
          autofocus
          bind:value
        />
      </label>
      <p class="hint">
        {prompt.kind === "password"
          ? "Firefox needs it to sign in to UMBC."
          : "Firefox needs it to sign in to UMBC. Save it in Settings to skip this next time."}
      </p>
    {:else}
      <p class="message">{prompt.message}</p>
    {/if}

    <div class="actions">
      <button type="button" class="btn" disabled={sending} onclick={() => (asksForText ? cancelRun() : reply(false))}>
        {asksForText ? "Cancel run" : "No"}
      </button>
      <button type="submit" class="btn primary" disabled={sending || (asksForText && !value)}>
        {asksForText ? "Continue" : "Yes"}
      </button>
    </div>
  </form>
</dialog>

<style>
  dialog {
    width: min(420px, calc(100vw - 32px));
    padding: 0;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--surface);
    color: var(--text);
    box-shadow: 0 18px 50px rgb(0 0 0 / 0.25);
  }

  dialog::backdrop {
    background: rgb(20 18 12 / 0.45);
  }

  form {
    display: grid;
    gap: 14px;
    padding: 22px;
  }

  .head {
    display: flex;
    align-items: center;
    gap: 11px;
  }

  .badge {
    display: grid;
    place-items: center;
    width: 34px;
    height: 34px;
    border-radius: 50%;
    background: var(--accent-soft);
    color: var(--warn);
  }

  h2 {
    font-size: 16px;
  }

  .message {
    color: var(--text-2);
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 4px;
  }
</style>
