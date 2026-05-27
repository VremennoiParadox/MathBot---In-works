# UI templates (Phase 3)

MathBot finds buttons on screen by matching small PNG crops. **You must capture these from your tutoring site** (Sparx, Corbettmaths, etc.) — sizes vary by site.

## Where files live

After first run, copy templates here:

`~/Library/Application Support/MathBot/templates/`

(The repo `templates/` folder is documentation only unless you add PNGs for sharing.)

## Required

| File | What to crop |
|------|----------------|
| `answer_button.png` | The **Answer** button |

## Number pad (for numeric answers)

| File | What to crop |
|------|----------------|
| `digit_0.png` … `digit_9.png` | Each on-screen keypad button |
| `decimal_point.png` | `.` key (if shown) |
| `minus.png` | `-` key (optional) |

## Text / expression

| File | What to crop |
|------|----------------|
| `text_field.png` | The answer input box |

## Multiple choice (optional)

| File | What to crop |
|------|----------------|
| `mcq_a.png` … `mcq_d.png` | Each option row or radio (optional; falls back to typing `A`–`D`) |

## Success / failure (optional)

| File | What to crop |
|------|----------------|
| `tick_green.png` | Green check / correct feedback |
| `error_red.png` | Red error message |
| `submit_button.png` | Separate Submit if different from Answer |

## How to capture

1. Open the site at normal zoom (100%).
2. macOS screenshot: **Cmd+Shift+4**, then **Space**, click the button — or crop tightly in Preview.
3. Save as PNG with the exact names above.
4. Keep crops **small** (only the button, not the whole page).

## Test without clicking

Set `"dry_run": true` in `config.json`, or press **Cmd+Shift+D** while MathBot runs.
