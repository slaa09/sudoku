#!/usr/bin/env python3
"""Vyrenderuje icons/icon.svg do PNG velikostí potřebných pro PWA (Chrome headless)."""
import base64
import os
import sys

from playwright.sync_api import sync_playwright

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "icons")
SVG = open(os.path.join(ROOT, "icon.svg"), "rb").read()
B64 = base64.b64encode(SVG).decode()

TARGETS = {
    "icon-512.png": 512,
    "icon-maskable-512.png": 512,
    "icon-192.png": 192,
    "apple-touch-icon.png": 180,
    "favicon-32.png": 32,
}

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", headless=True, args=["--no-sandbox"])
    for name, size in TARGETS.items():
        page = b.new_page(viewport={"width": size, "height": size}, device_scale_factor=1)
        page.set_content(
            "<style>html,body{margin:0;padding:0;background:#1f5fd6}img{display:block}</style>"
            f'<img width="{size}" height="{size}" src="data:image/svg+xml;base64,{B64}">'
        )
        page.wait_for_function("document.images[0].complete")
        page.screenshot(path=os.path.join(ROOT, name), clip={"x": 0, "y": 0, "width": size, "height": size})
        page.close()
    b.close()
print("hotovo:", ", ".join(TARGETS))
