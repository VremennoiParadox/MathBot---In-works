# MathBot

**A local AI tool that solves math problems on screen and enters the answers for you — no internet, no API costs.**

`macOS only` · `Ollama required` · `No Python needed` · `Free & open source`

---

## How it works

**Step 1 — Select region (once per session)**  
On launch, you draw a rectangle over the question area in your browser. MathBot remembers it in `config.json`.

**Step 2 — Autonomous loop**  
MathBot repeatedly: captures that region → reads the question → solves with **two AI passes** → clicks **Answer** → enters the result → checks for ✅/❌ → advances to the next question. No hotkey per question.

**Step 3 — You stay in control**  
Press **Q** or **Ctrl+C** to stop. If confidence is low, the loop **pauses** and asks you before submitting.

> All AI runs on your Mac through **Ollama**. Your screen content stays on your machine.

---

## Requirements

- **macOS 13 (Ventura)** or later  
- **Apple Silicon (M1 or newer)** recommended — Intel Macs work but are slower  
- **[Ollama](https://ollama.com)** installed and running (menu-bar app)  
- **At least 8 GB RAM** — 16 GB recommended for faster, more accurate models  
- **No Python, no pip, no terminal experience** required if you use the pre-built `MathBot.app`

### RAM guide (quick reference)

| Your Mac RAM | Vision model (reads screen) | Solver model (does maths) | Typical solve time |
|--------------|----------------------------|---------------------------|--------------------|
| 8 GB | moondream:v2 | qwen2.5:7b | 10–20 sec |
| 16 GB | qwen2.5vl:7b | qwen2.5:7b | 5–12 sec |
| 16 GB (accuracy focus) | qwen2.5vl:7b | deepseek-r1:14b | 10–20 sec |
| 32 GB+ | qwen2.5vl:7b | deepseek-r1:14b | 3–8 sec |

*Times include read + solve + double-check. First question after a restart can take longer while models load.*

---

## Installation

1. **Install Ollama** from [https://ollama.com](https://ollama.com) and open it once (it stays in your menu bar).  
2. **Download** `MathBot.app.zip` from the [Releases](../../releases) page.  
3. **Unzip** the file and drag **MathBot.app** into your **Applications** folder.  
4. **First open (important):** macOS may block the app because it is not from the App Store.  
   - **Right-click** `MathBot.app` → **Open** → click **Open** in the dialog.  
   - You only need to do this **once**.  
5. **Terminal opens** and the **setup wizard** runs: pick your AI models, then follow the prompts to grant permissions.  
6. The wizard downloads the models you chose (often **5–15 minutes** on first run, depending on your internet speed).

---

## Permissions (important)

MathBot needs two macOS permissions. Both are **only used on your Mac** — no data leaves your computer.

### Screen Recording

**Why:** MathBot must see your screen to read the question.

**How to enable:**  
**System Settings** → **Privacy & Security** → **Screen Recording** → turn **on** for **MathBot** (or **Terminal** if you run from source).

### Accessibility

**Why:** MathBot moves the mouse and types on the keyboard to enter answers.

**How to enable:**  
**System Settings** → **Privacy & Security** → **Accessibility** → turn **on** for **MathBot**.

After changing permissions, **quit and reopen** MathBot.

---

## Choosing your AI models

MathBot uses **two AI models** (both free, both local):

1. **Vision model** — looks at the screenshot and reads the question.  
2. **Solver model** — does the maths and checks its work.

On first launch, the **setup wizard** lists models you already have in Ollama and lets you pick the best pair for your Mac. It can download missing models for you.

**To change models later:** while MathBot is running, press **`M`** to open the model switcher.

Your choices are saved in:

`~/Library/Application Support/MathBot/config.json`

---

## Controls

| Key | Action |
|-----|--------|
| **Q** | Stop the autonomous solver loop |
| **Ctrl+C** | Stop and print session summary |

Graph questions are detected **automatically** (OpenCV heuristics + vision `contains_graph` field) — no separate graph hotkey needed.

Set `"dry_run": true` in `config.json` to solve and print answers **without** clicking.

---

## How the double-check works

MathBot **never submits its first guess straight away**.

1. It **solves** the problem and shows its working.  
2. It **solves again a different way** to check the first answer.  
3. Only if both passes agree (and confidence is high enough) does it type into the website.  
4. If it is **not sure**, it stops and asks you: **[S]ubmit / [E]dit / [S]kip?**

That is why solving takes a few seconds longer than a single quick guess — **accuracy comes first**.

### Turning off the double-check (`think_mode`)

In `~/Library/Application Support/MathBot/config.json`, set `"think_mode": false` to **skip Pass 2** (faster, more wrong answers). **Recommended: leave `true`.**

On startup, MathBot prints whether recheck is ON or OFF.

---

## Graph questions

Graphs are harder for AI to read than plain sums.

- Use **Cmd+Shift+G** for graph-style questions.  
- MathBot uses a **graph-specific** prompt and reads the chart twice before submitting.  
- If confidence is **below 75%**, it shows its working and asks **[S]ubmit / [E]dit / [S]kip?** before clicking anything.

**Known limitation:** simple bar and line charts work best. Complex curves (trigonometry, logarithms, etc.) may need you to type the answer yourself — MathBot will tell you when it is not confident.

---

## Troubleshooting

### `pip install` fails on `pyobjc-core` / `clang` errors

**Cause:** `requirements.txt` includes **pyautogui** (Phase 3 clicking). That pulls **pyobjc**, which must compile C code. Old **Python 3.9** (often from Xcode) plus a new Xcode/clang often fails with `simd_*` / `Wdefault-const-init-var-unsafe` errors.

**Fix (Phase 1–2 — recommended now):**

1. Install a modern Python: `brew install python@3.12`
2. Recreate the venv with that Python:
   ```bash
   cd MathBot
   rm -rf .venv
   python3.12 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   pip install -r requirements-phase12.txt
   ```
3. Run: `python main.py`

Install full `requirements.txt` later when you start **Phase 3** (UI automation).

---

### “MathBot can’t see my screen”

**Cause:** Screen Recording permission is off.

**Fix:**  
**System Settings** → **Privacy & Security** → **Screen Recording** → enable **MathBot** → quit and reopen MathBot.

---

### “MathBot won’t click anything”

**Cause:** Accessibility permission is off.

**Fix:**  
**System Settings** → **Privacy & Security** → **Accessibility** → enable **MathBot** → quit and reopen MathBot.

---

### Phase 4 — Memory & verification

MathBot saves every verified answer in:

`~/Library/Application Support/MathBot/db/mathbot.sqlite`

When you see the **same question again** (e.g. “check your work”), it **skips Ollama** and re-uses your stored answer.

On quit (**Q**), a CSV export is written to:

`~/Library/Application Support/MathBot/exports/`

---

### UI templates (required for clicking)

```bash
pip install -r requirements-phase3.txt
python capture_templates.py
```

This walks you through screenshotting each button from **your** tutoring site. Files are saved to:

`~/Library/Application Support/MathBot/templates/`

See also [assets/templates/README.md](assets/templates/README.md).

Enable **Accessibility** for Terminal, then run:

```bash
python main.py
```

Use `"dry_run": true` in config.json for a first test without mouse clicks.

---

### Hotkey does nothing after screenshot (or only a screenshot appears)

**Cause:** The first solve can take **1–3 minutes** while Ollama loads vision + solver models. Older builds also ran the solve on a background thread so Terminal output could look frozen.

**Fix:**

1. Watch the **same Terminal window** where `python main.py` is running — you should see `▶ Hotkey received` then `Reading question…`.
2. Run a test without the hotkey:
   ```bash
   python main.py --solve-once
   ```
3. Grant **Accessibility** for Terminal: System Settings → Privacy & Security → **Accessibility** → enable **Terminal** (needed for global hotkeys).
4. Keep **Ollama running** (`ollama serve` or menu-bar app).

---

### “Ollama is not running”

MathBot tries to start Ollama automatically. If that fails:

1. Open **Ollama** from your Applications folder (or menu bar).  
2. Wait until it is running, then use MathBot again.

---

### “The model is taking forever to load”

**Normal** the first time after a Mac restart. The model is loading into memory. Later questions in the same session are usually much faster.

---

### “MathBot entered the wrong answer”

1. Turn on **dry-run mode** (**Cmd+Shift+D**) to preview answers before they are typed.  
2. When confidence is low, use **[E]dit** to type the correct value yourself.  
3. Report issues on GitHub with the **question type** and a **screenshot** (blur personal info).

---

### “Model not found” error

**Fix:**

1. Open **Terminal** and run: `ollama list`  
2. If your models are missing, run the wizard again: delete  
   `~/Library/Application Support/MathBot/config.json`  
   and restart MathBot.

---

## Resetting MathBot

| What you want | What to delete |
|---------------|----------------|
| Run setup wizard again | `~/Library/Application Support/MathBot/config.json` |
| Clear answer history | `~/Library/Application Support/MathBot/db/mathbot.sqlite` |
| **Full uninstall** | Delete **MathBot.app** from Applications **and** delete the whole folder `~/Library/Application Support/MathBot/` |

---

## Developers (build from source)

**macOS only** for running and packaging. On a Mac:

```bash
./setup.sh
source .venv/bin/activate
python main.py
```

| Command | Purpose |
|---------|---------|
| `python main.py` | Select region → autonomous loop |
| `python main.py --self-test` | Smoke test (Ollama + imports + optional fixture vision) |
| `python main.py --loop-once` | Single loop iteration (testing) |
| `python capture_templates.py` | Guided UI template capture |
| `pytest tests/` | Unit tests (needs `requirements-phase3.txt` for full suite) |
| `./build.sh` | Build `dist/MathBot.app` with PyInstaller |
| `./verify_build.sh` | Run `--self-test` on the built app |

After you quit with **Q**, average solve time is saved in `config.json` under `session_stats.avg_solve_time_ms`.

Generate the self-test screenshot fixture:

```bash
python scripts/make_sample_fixture.py
```

---

## Footer

**Built with:** Ollama · PyInstaller · pyautogui · mss · Pillow · OpenCV · imagehash · pynput

**License:** MIT

**Contributing:** Issues and pull requests are welcome. When reporting a wrong answer, include the **question type** and a **screenshot** if you can.
