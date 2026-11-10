#!/usr/bin/env python3
"""
Extract color-styled text from a PDF (typically red-highlighted "加红" parts
in Chinese business/academic PPTs).

Usage:
    python extract_colored_text.py file.pdf                # default: red
    python extract_colored_text.py file.pdf --color yellow
    python extract_colored_text.py file.pdf --rgb 255,0,0
    python extract_colored_text.py file.pdf --loose         # widen thresholds
    python extract_colored_text.py file.pdf --pages 5-12     # 1-indexed inclusive
    python extract_colored_text.py file.pdf --out hits.txt   # save to file
"""
import argparse
import sys

try:
    import pymupdf
except ImportError:
    sys.exit("pymupdf not installed. Run: pip install pymupdf")


PRESETS = {
    # (r_min, r_minus_g_min, r_minus_b_min, g_max, b_max)
    "red":    (180, 60,  60,  120, 120),
    "yellow": (200, 0,   50,  255, 150),
    "green":  (150, -50, 0,   255, 150),
    "blue":   (150, -50, -50, 150, 255),
}


def make_filter(name, loose=False, custom_rgb=None):
    if custom_rgb:
        r0, g0, b0 = custom_rgb
        # Match within ±40 of each channel — catches tinted variants
        def f(r, g, b, r0=r0, g0=g0, b0=b0):
            return abs(r - r0) <= 40 and abs(g - g0) <= 40 and abs(b - b0) <= 40
        return f
    r_min, rg, rb, g_max, b_max = PRESETS[name]
    if loose:
        r_min, rg, rb = max(0, r_min - 40), max(0, rg - 20), max(0, rb - 20)
        g_max += 30
        b_max += 30
    def f(r, g, b, r_min=r_min, rg=rg, rb=rb, g_max=g_max, b_max=b_max):
        return r >= r_min and g <= g_max and b <= b_max and (r - g) >= rg and (r - b) >= rb
    return f


def extract(pdf_path, color_filter, page_range=None):
    doc = pymupdf.open(pdf_path)
    total = len(doc)
    start = (page_range[0] - 1) if page_range else 0
    stop  = min(page_range[1], total) if page_range else total
    results = []
    for i in range(start, stop):
        page = doc[i]
        d = page.get_text("dict")
        page_hits = []
        for block in d.get("blocks", []):
            for line in block.get("lines", []):
                line_text = []
                for span in line.get("spans", []):
                    color = span.get("color", 0)
                    r = (color >> 16) & 0xFF
                    g = (color >> 8)  & 0xFF
                    b = color         & 0xFF
                    if color_filter(r, g, b):
                        line_text.append(span.get("text", ""))
                if line_text:
                    page_hits.append("".join(line_text))
        if page_hits:
            results.append((i + 1, page_hits))
    doc.close()
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("--color", choices=list(PRESETS), default="red")
    ap.add_argument("--rgb", help="custom RGB 'r,g,b' (within ±40 match)")
    ap.add_argument("--loose", action="store_true", help="widen thresholds")
    ap.add_argument("--pages", help="1-indexed inclusive, e.g. 5-12")
    ap.add_argument("--out", help="output file (default stdout)")
    args = ap.parse_args()

    custom = None
    if args.rgb:
        try:
            custom = tuple(int(x) for x in args.rgb.split(","))
            assert len(custom) == 3 and all(0 <= v <= 255 for v in custom)
        except Exception:
            sys.exit("--rgb must be 'r,g,b' with 0-255 values")
    cf = make_filter(args.color, loose=args.loose, custom_rgb=custom)

    pr = None
    if args.pages:
        try:
            a, b = args.pages.split("-")
            pr = (int(a), int(b))
        except Exception:
            sys.exit("--pages must be 'start-end', e.g. 5-12")

    results = extract(args.pdf, cf, pr)
    lines = []
    if not results:
        lines.append(f"(no {args.color} text matched)")
    for page, hits in results:
        lines.append(f"--- Page {page} ---")
        for t in hits:
            lines.append(t.strip())
    output = "\n".join(lines)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output + "\n")
        print(f"Wrote {args.out} ({len(results)} pages with matches)")
    else:
        print(output)


if __name__ == "__main__":
    main()