// Freezes the Python bridge into one executable with PyInstaller and puts it
// where tauri.bundle.conf.json's externalBin expects it:
//   src-tauri/binaries/autopayroll-backend-<target triple>[.exe]
// Release builds bundle that file and run it next to the app executable.
import { execFileSync } from "node:child_process";
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const gui = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const root = resolve(gui, "..");
const work = join(gui, "src-tauri", "target", "backend");
const name = "autopayroll-backend";
const ext = process.platform === "win32" ? ".exe" : "";

const rustc = execFileSync("rustc", ["-vV"], { encoding: "utf8" });
const triple = /^host: (\S+)$/m.exec(rustc)?.[1];
if (!triple) throw new Error("Could not read the target triple from `rustc -vV`.");

// `python -m PyInstaller` rather than the `pyinstaller` script, whose shebang
// goes stale if the project folder is ever moved.
execFileSync(
  "uv",
  [
    "run",
    "python",
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--name",
    name,
    "--distpath",
    join(work, "dist"),
    "--workpath",
    join(work, "build"),
    "--specpath",
    work,
    join(gui, "scripts", "backend_entry.py"),
  ],
  { cwd: root, stdio: "inherit" },
);

const target = join(gui, "src-tauri", "binaries", `${name}-${triple}${ext}`);
mkdirSync(dirname(target), { recursive: true });
copyFileSync(join(work, "dist", name + ext), target);
console.log(`Backend ready: ${target}`);
