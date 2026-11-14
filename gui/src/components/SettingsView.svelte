<script lang="ts">
  import { open } from "@tauri-apps/plugin-dialog";
  import { openPath } from "@tauri-apps/plugin-opener";
  import { onMount } from "svelte";
  import { app, errorMessage } from "../lib/app.svelte";
  import Icon from "./Icon.svelte";

  let username = $state(app.settings.username);
  let profileDir = $state(app.settings.profile_dir);
  let payRate = $state<number | null>(app.settings.pay_rate);
  let password = $state("");

  let saving = $state(false);
  let saved = $state(false);
  let error = $state<string | null>(null);
  let passwordBusy = $state(false);
  let passwordError = $state<string | null>(null);

  // undefined until the keyring has been checked.
  const passwordSource = $derived(app.settings.password);
  const locked = $derived(app.run?.running ?? false);
  const usernameSaved = $derived(!!app.settings.username && username.trim() === app.settings.username);
  const dirty = $derived(
    username.trim() !== app.settings.username ||
      profileDir !== app.settings.profile_dir ||
      payRate !== app.settings.pay_rate,
  );
  const validRate = $derived(payRate !== null && payRate > 0);

  onMount(async () => {
    try {
      await app.loadSettings();
    } catch (failure) {
      error = errorMessage(failure);
    }
  });

  async function save() {
    saving = true;
    error = null;
    try {
      await app.saveSettings({
        username: username.trim(),
        profile_dir: profileDir,
        pay_rate: payRate as number,
      });
      username = app.settings.username;
      saved = true;
      setTimeout(() => (saved = false), 2000);
    } catch (failure) {
      error = errorMessage(failure);
    } finally {
      saving = false;
    }
  }

  function discard() {
    username = app.settings.username;
    profileDir = app.settings.profile_dir;
    payRate = app.settings.pay_rate;
    error = null;
  }

  async function chooseProfile() {
    const picked = await open({
      title: "Choose a Firefox profile folder",
      directory: true,
      multiple: false,
      defaultPath: profileDir || undefined,
    });
    if (typeof picked === "string") profileDir = picked;
  }

  async function passwordAction(action: () => Promise<void>) {
    passwordBusy = true;
    passwordError = null;
    try {
      await action();
      password = "";
    } catch (failure) {
      passwordError = errorMessage(failure);
    } finally {
      passwordBusy = false;
    }
  }

  async function reveal(path: string) {
    try {
      await openPath(path);
    } catch (failure) {
      app.log("error", `Could not open ${path}: ${errorMessage(failure)}`);
    }
  }
</script>

<div class="page">
  <h1>Settings</h1>

  {#if locked}
    <div class="alert info">
      <Icon name="info" />
      <span>Settings can't be changed while a run is in progress.</span>
    </div>
  {/if}

  <section class="card section">
    <div class="about">
      <h2>UMBC account</h2>
      <p>Used to sign in to TRAC and PeopleSoft when Firefox isn't already signed in.</p>
    </div>
    <div class="fields">
      <label class="field">
        <span class="label">Username</span>
        <input
          class="input"
          bind:value={username}
          placeholder="e.g. ab12345"
          autocomplete="off"
          spellcheck="false"
          disabled={locked}
        />
      </label>

      <div class="field">
        <span class="label">Password</span>
        <div class="status">
          {#if passwordSource === undefined}
            <Icon name="spinner" size={14} /> Checking…
          {:else if passwordSource === "keyring"}
            <span class="ok"><Icon name="check" size={14} /></span> Saved in your system keyring
          {:else if passwordSource === "file"}
            <span class="warn"><Icon name="alert" size={14} /></span> Stored as plain text in settings.env
          {:else}
            <span class="muted"><Icon name="minus" size={14} /></span> Not saved. You'll be asked when a sign-in needs it.
          {/if}
        </div>

        {#if passwordSource === "file"}
          <p class="hint">
            To keep it in the keyring instead, delete the <code>UMBC_PAS</code> line from settings.env
            (open the files folder below).
          </p>
        {:else}
          <div class="row">
            <input
              class="input"
              type="password"
              bind:value={password}
              placeholder={passwordSource === "keyring" ? "Replace the saved password" : "Password"}
              autocomplete="off"
              disabled={locked || !usernameSaved}
            />
            <button
              class="btn"
              disabled={locked || !usernameSaved || !password || passwordBusy}
              onclick={() => passwordAction(() => app.setPassword(password))}
            >
              Save to keyring
            </button>
          </div>
          {#if !usernameSaved}
            <p class="hint">Save your username first. The password is stored under it.</p>
          {/if}
          {#if passwordSource === "keyring"}
            <div>
              <button
                class="btn quiet small danger forget"
                disabled={locked || passwordBusy}
                onclick={() => passwordAction(() => app.forgetPassword())}
              >
                Forget saved password
              </button>
            </div>
          {/if}
        {/if}
        {#if passwordError}
          <div class="alert error"><Icon name="alert" /><span>{passwordError}</span></div>
        {/if}
      </div>
    </div>
  </section>

  <section class="card section">
    <div class="about">
      <h2>Firefox</h2>
      <p>A profile used only by this app keeps you signed in, Duo included, between runs.</p>
    </div>
    <div class="fields">
      <div class="field">
        <span class="label">Profile folder</span>
        <div class="file">
          <Icon name="folder" />
          <span class="path" class:empty={!profileDir} title={profileDir}>
            {profileDir || "None: a fresh, signed-out profile every run"}
          </span>
          {#if profileDir}
            <button class="btn quiet small" disabled={locked} onclick={() => (profileDir = "")}>Clear</button>
          {/if}
          <button class="btn small" disabled={locked} onclick={chooseProfile}>Choose…</button>
        </div>
        <p class="hint">
          Create one in Firefox at <code>about:profiles</code>, then choose its folder here. It can't be
          open in another Firefox window while a run uses it.
        </p>
      </div>
    </div>
  </section>

  <section class="card section">
    <div class="about">
      <h2>Pay</h2>
      <p>Only used for the pay estimates shown before you enter a timesheet.</p>
    </div>
    <div class="fields">
      <label class="field">
        <span class="label">Hourly rate</span>
        <span class="rate">
          <span class="unit">$</span>
          <input class="input num" type="number" min="0.01" step="0.01" bind:value={payRate} disabled={locked} />
          <span class="unit">per hour</span>
        </span>
      </label>
      {#if !validRate}<p class="hint invalid">Enter an hourly rate above zero.</p>{/if}
    </div>
  </section>

  <section class="card section">
    <div class="about">
      <h2>Files</h2>
      <p>Settings, the pay-period list, and every CSV this app saves.</p>
    </div>
    <div class="fields">
      <div class="file">
        <Icon name="folder" />
        <span class="path selectable" title={app.configDir}>{app.configDir}</span>
        <button class="btn small" onclick={() => reveal(app.configDir)}>Open</button>
      </div>
    </div>
  </section>

  <div class="savebar">
    {#if error}
      <span class="message error">{error}</span>
    {:else if saved}
      <span class="message ok"><Icon name="check" size={14} /> Saved</span>
    {/if}
    <button class="btn" disabled={!dirty || saving} onclick={discard}>Discard</button>
    <button class="btn primary" disabled={!dirty || !validRate || saving || locked} onclick={save}>
      {#if saving}<Icon name="spinner" />{/if}
      Save changes
    </button>
  </div>
</div>

<style>
  .page {
    display: grid;
    gap: 14px;
    max-width: 820px;
    margin: 0 auto;
  }

  h1 {
    font-size: 19px;
    letter-spacing: -0.01em;
    margin-bottom: 4px;
  }

  .section {
    display: grid;
    grid-template-columns: 220px minmax(0, 1fr);
    gap: 24px;
    padding: 20px 22px;
  }

  .about {
    display: grid;
    gap: 4px;
    align-content: start;
  }

  h2 {
    font-size: 14px;
  }

  .about p {
    font-size: 13px;
    color: var(--text-2);
  }

  .fields {
    display: grid;
    gap: 16px;
    align-content: start;
    min-width: 0;
  }

  .status {
    display: flex;
    align-items: center;
    gap: 7px;
    color: var(--text-2);
  }

  .ok {
    color: var(--ok);
  }

  .warn {
    color: var(--warn);
  }

  .muted {
    color: var(--text-3);
  }

  .row {
    display: flex;
    gap: 8px;
  }

  .forget {
    margin-left: -10px; /* line the text up with the field above */
  }

  .file {
    display: flex;
    align-items: center;
    gap: 9px;
    min-height: 40px;
    padding: 4px 6px 4px 11px;
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
    font-family: var(--mono);
    font-size: 12.5px;
  }

  .path.empty {
    color: var(--text-3);
    font-family: var(--font);
    font-size: 14px;
  }

  .rate {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .rate .input {
    width: 110px;
  }

  .unit {
    color: var(--text-2);
  }

  .invalid {
    color: var(--danger);
  }

  .savebar {
    position: sticky;
    bottom: -24px;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;
    margin: 0 -24px -24px;
    padding: 12px 24px 18px;
    background: linear-gradient(to bottom, transparent, var(--bg) 30%);
  }

  .message {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-right: auto;
    font-size: 13px;
  }

  .message.error {
    color: var(--danger);
  }

  .message.ok {
    color: var(--ok);
  }

  @media (max-width: 760px) {
    .section {
      grid-template-columns: 1fr;
      gap: 14px;
    }
  }
</style>
