# Color Extraction — Notes & Pitfalls

Notes distilled from a real session extracting red-highlighted text from Chinese
business PPTs (压力容器制造质量体系 / 特种设备法规体系介绍).

## The Core Pattern

`page.get_text()` returns plain text — color is lost. To get per-span color:

```python
d = page.get_text("dict")          # {'blocks': [{'lines': [{'spans': [{'text':..., 'color':...}]}]}]}
color = span["color"]              # 24-bit int: 0xRRGGBB
r, g, b = (color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF
```

Filter by RGB and you're done. The script `scripts/extract_colored_text.py`
ships ready-made presets (red, yellow, green, blue) plus custom RGB.

## Real-World Threshold Table

Encountered in two NCNIC PPTs from June 2026:

| RGB                  | Where seen                            | Default preset catches? |
|----------------------|---------------------------------------|-------------------------|
| `255, 0, 0`          | Body-text emphasis ("加红")           | ✅ yes                  |
| `192, 0, 0`          | "日 管控 / 周排查 / 月调度" subheads  | ❌ no (need --loose)    |
| `205, 10, 32`        | Brand footer "谢谢 ncic.sinopec.com"  | ❌ no (need --loose)    |

**Lesson**: When the user reports the output is empty, immediately try `--loose`
before assuming the PDF has no color. Brand reds and dark reds are common.

## Pitfalls

### 1. False "backgrounding" warnings on terminal with Chinese heredoc

`terminal(pty=false)` triggers `Foreground command uses '&' backgrounding` if the
shell command line contains certain byte sequences (seems sensitive to certain
Chinese punctuation). **Fix**: write the script to disk with `write_file`, then
run it with `terminal`. Don't paste multi-line Python with `<<PY` and CJK into
`terminal` — stage via `write_file`.

### 2. Wrong python interpreter

On macOS with Hermes Agent, `pip install pymupdf` lands in
`~/.hermes/hermes-agent/venv/`, but `/usr/bin/python3` (system, 3.9 from CLT)
does **not** see it. Always use:

```bash
~/.hermes/hermes-agent/venv/bin/python scripts/extract_colored_text.py file.pdf
```

Check with `~/.hermes/hermes-agent/venv/bin/python -c "import pymupdf"`.

### 3. execute_code blocked in cron contexts

`execute_code` runs arbitrary Python and is blocked when the session is a cron
run. For cron-friendly PDF processing, always use the script + `terminal` path.

### 4. Spans split mid-word

A red phrase like "质量永远领先一步" may come back as 4 separate spans
because PowerPoint splits runs on font/style changes. Concatenate by **line**,
not by span, before printing:

```python
line_text.append(span.get("text", ""))
# after the inner loop:
if line_text:
    page_hits.append("".join(line_text))
```

### 5. Don't trust `page.search_for()` for color

`page.search_for("质量")` finds text regardless of color. To filter by color
**and** search term, do the color filter first, then substring-match on the
concatenated line.

## Worked Recipe Used

```python
import pymupdf
doc = pymupdf.open("input.pdf")
all_red = []
for page_idx, page in enumerate(doc):
    hits = []
    d = page.get_text("dict")
    for block in d.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                c = span.get("color", 0)
                r, g, b = (c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF
                if r >= 180 and g < 120 and b < 120 and (r - g) > 60:
                    hits.append(span.get("text", "").strip())
    if hits:
        all_red.append((page_idx + 1, hits))
doc.close()
```

Output for these two PPTs:
- doc1 (质量体系): 35 pages with red text, ~120 distinct red spans
- doc2 (法规体系): 30 pages with red text, ~80 distinct red spans

## Variations the user might ask for

| Phrasing                          | What to do                          |
|-----------------------------------|-------------------------------------|
| "提取加红部分"                      | Red filter, present as structured Markdown |
| "把所有红色字整理成知识总结"        | Extract red → group by section → write MD |
| "提取黄色高亮"                     | Switch preset to `yellow`            |
| "加红的和加黄的都要"              | Run twice, merge                    |
| "把 PDF 里所有红色加粗字导出"      | Combine color filter + `flags & 16` (bold) on span |