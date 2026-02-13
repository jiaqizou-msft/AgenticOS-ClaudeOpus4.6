#!/usr/bin/env python3
"""
AgenticOS Demo — No LLM Required

Demonstrates the core observe pipeline:
  1. Screenshot capture
  2. UIA element grounding
  3. Element display

This lets you see the system's "eyes" without an API key.
"""

import asyncio
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


async def main():
    from agenticos.grounding.accessibility import UIAGrounder
    from agenticos.observation.screenshot import ScreenCapture
    from agenticos.utils.config import AgenticOSConfig

    config = AgenticOSConfig()
    print("=" * 60)
    print("  🖥️  AgenticOS — Observe Pipeline Demo")
    print("=" * 60)
    print()

    # --- Step 1: Screenshot ---
    print("📸 Step 1: Capturing screenshot...")
    t0 = time.perf_counter()
    capture = ScreenCapture(monitor=config.screenshot_monitor, scale=config.screenshot_scale)
    screenshot = capture.grab()
    dt = time.perf_counter() - t0
    print(f"   ✅ Screenshot: {screenshot.width}×{screenshot.height} in {dt*1000:.0f}ms")

    # Save screenshot
    out_dir = Path("recordings")
    out_dir.mkdir(exist_ok=True)
    screenshot_path = out_dir / "demo_screenshot.png"
    screenshot.save(str(screenshot_path))
    print(f"   💾 Saved to {screenshot_path}")
    print()

    # --- Step 2: UIA Grounding ---
    print("🔍 Step 2: UIA element detection...")
    t0 = time.perf_counter()
    grounder = UIAGrounder()
    elements = grounder.detect()
    dt = time.perf_counter() - t0
    print(f"   ✅ Found {len(elements)} UI elements in {dt*1000:.0f}ms")
    print()

    # --- Step 3: Display elements ---
    print("📋 Step 3: Detected UI elements (top 25):")
    print("-" * 60)
    for i, el in enumerate(elements[:25]):
        bbox = el.bbox
        loc = f" @ ({bbox[0]},{bbox[1]})-({bbox[2]},{bbox[3]})" if bbox != (0,0,0,0) else ""
        label = el.name[:50] if el.name else "(no name)"
        print(f"   {i+1:2d}. [{el.control_type:15s}] {label}{loc}")

    if len(elements) > 25:
        print(f"   ... and {len(elements) - 25} more elements")
    print("-" * 60)
    print()

    # --- Step 4: Build element summary (what the LLM would see) ---
    print("🧠 Step 4: Element summary for LLM prompt:")
    print("-" * 60)
    for i, el in enumerate(elements[:15]):
        print(f"  {el.description()}")
    if len(elements) > 15:
        print(f"  ... ({len(elements) - 15} more)")
    print("-" * 60)
    print()

    # --- Summary ---
    print("=" * 60)
    print("  ✅ Observe pipeline working!")
    print(f"  📊 {len(elements)} elements detected")
    print(f"  📸 Screenshot saved to {screenshot_path}")
    print()
    print("  To run the full agent with LLM, set an API key:")
    print("    $env:ANTHROPIC_API_KEY = 'sk-ant-...'")
    print("    python scripts/record_demo.py \"Open Notepad\" --output recordings/demo.gif")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
