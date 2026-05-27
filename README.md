# MathBot

**A local AI tool that solves math problems on screen and enters the answers for you — no internet, no API costs.**

`macOS only` · `Ollama required` · `No Python needed` · `Free & open source`

---

## How it works

**Step 1 — Capture**  
Press a hotkey. MathBot takes a screenshot of the question on your screen (Sparx, Corbettmaths, and similar sites).

**Step 2 — Solve (locally)**  
A local AI model reads the question. A second model solves it and **double-checks** its own answer using a different method. Nothing is sent to the internet.

**Step 3 — Enter**  
MathBot clicks **Answer** and types the verified result into the website for you.

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
| 8 GB | moondream2 | qwen2.5-math:7b | 10–20 sec |
| 16 GB | qwen2.5vl:7b | qwen2.5-math:7b | 5–12 sec |
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

## Hotkeys

| Hotkey | Action |
|--------|--------|
| **Cmd+Shift+S** | Solve the current question and enter the answer |
| **Cmd+Shift+G** | **Graph mode** — specialised graph solve (slower; may ask you to confirm) |
| **M** | Open the **model switcher** |
| **Cmd+Shift+D** | Toggle **dry-run mode** (shows what would be entered without clicking) |
| **Q** | Quit MathBot |

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

## Footer

**Built with:** Ollama · PyInstaller · pyautogui · mss · Pillow · OpenCV · imagehash · pynput

**License:** MIT

**Contributing:** Issues and pull requests are welcome. When reporting a wrong answer, include the **question type** and a **screenshot** if you can.
