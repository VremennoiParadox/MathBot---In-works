# UI templates

MathBot matches these PNG images inside your selected screen region.

## First-time setup

1. Run the guided capture tool on your Mac:

   ```bash
   python capture_templates.py
   ```

2. Or copy placeholders and replace them with real screenshots from your site:

   ```bash
   python scripts/create_template_placeholders.py
   cp assets/templates/*.png ~/Library/Application\ Support/MathBot/templates/
   ```

## Required files

| File | Purpose |
|------|---------|
| `answer_button.png` | Opens the answer UI |
| `correct_tick.png` | Confirms a correct submission |
| `next_button.png` | Advances to the next question |
| `wrong_highlight.png` | Detects a wrong answer (optional) |
| `submit_button.png` | Confirms number-pad entry |
| `text_field.png` | Text/expression questions |
| `digit_0.png` … `digit_9.png` | Number pad keys (as needed) |

Place final templates in:

`~/Library/Application Support/MathBot/templates/`
