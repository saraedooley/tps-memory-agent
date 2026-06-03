#!/usr/bin/env python3
"""
Render Mermaid diagrams to PNG using Chrome headless mode.
"""
import os
import sys
import time
import subprocess
import tempfile
import shutil

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

def render_mermaid_to_png(mmd_content: str, output_png: str, width: int = 1600, height: int = 3000):
    """Render a Mermaid diagram to PNG via Chrome headless."""

    # Create a temp directory
    tmpdir = tempfile.mkdtemp(prefix="mermaid_render_")

    try:
        # Write an HTML file with mermaid via CDN
        html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      background: white;
      width: {width}px;
    }}
    body {{
      padding: 60px;
      box-sizing: border-box;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }}
    #diagram {{
      width: 100%;
    }}
    .mermaid {{
      display: block;
      width: 100%;
    }}
    /* Make SVG responsive to container */
    .mermaid svg {{
      width: 100% !important;
      height: auto !important;
      max-width: 100%;
    }}
  </style>
</head>
<body>
  <div id="diagram">
    <div class="mermaid">
{mmd_content}
    </div>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
  <script>
    mermaid.initialize({{
      startOnLoad: true,
      theme: 'default',
      themeVariables: {{
        primaryColor: '#4A90D9',
        primaryTextColor: '#1a1a2e',
        primaryBorderColor: '#2E6DA4',
        lineColor: '#444444',
        secondaryColor: '#E8F4FD',
        tertiaryColor: '#FFF9E6',
        background: '#ffffff',
        mainBkg: '#E8F4FD',
        nodeBorder: '#2E6DA4',
        clusterBkg: '#EFF5FF',
        clusterBorder: '#3A6EA8',
        titleColor: '#1a1a2e',
        edgeLabelBackground: '#ffffff',
        fontFamily: '-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
        fontSize: '18px'
      }},
      flowchart: {{
        curve: 'basis',
        padding: 30,
        htmlLabels: true,
        nodeSpacing: 50,
        rankSpacing: 60
      }},
      sequence: {{
        mirrorActors: false
      }}
    }});
  </script>
</body>
</html>"""

        html_file = os.path.join(tmpdir, "diagram.html")
        with open(html_file, "w") as f:
            f.write(html_content)

        # Use Chrome headless to screenshot
        chrome_args = [
            CHROME,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            f"--window-size={width},{height}",
            "--hide-scrollbars",
            "--disable-extensions",
            "--force-device-scale-factor=2",
            f"--screenshot={output_png}",
            f"--virtual-time-budget=10000",
            f"file://{html_file}"
        ]

        print(f"  Rendering to {output_png}...")
        result = subprocess.run(chrome_args, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            print(f"  Chrome stderr: {result.stderr[:500]}")
            return False

        if os.path.exists(output_png):
            size = os.path.getsize(output_png)
            print(f"  Output: {output_png} ({size:,} bytes)")
            return True
        else:
            print(f"  ERROR: Output file not created")
            return False

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def crop_to_content_and_pad(png_path: str, padding: int = 60):
    """Crop PNG to diagram content and add white padding."""
    try:
        from PIL import Image, ImageChops
        import numpy as np

        img = Image.open(png_path).convert("RGB")
        # Find non-white area
        arr = np.array(img)
        # Mask of non-white pixels (any channel < 250)
        mask = (arr < 250).any(axis=2)
        rows = np.any(mask, axis=1)
        cols = np.any(mask, axis=0)

        if not rows.any():
            print(f"  Warning: Could not find content to crop in {png_path}")
            return

        rmin, rmax = np.where(rows)[0][[0, -1]]
        cmin, cmax = np.where(cols)[0][[0, -1]]

        # Add padding
        rmin = max(0, rmin - padding)
        rmax = min(arr.shape[0], rmax + padding)
        cmin = max(0, cmin - padding)
        cmax = min(arr.shape[1], cmax + padding)

        cropped = img.crop((cmin, rmin, cmax, rmax))

        # Create white background and paste
        final = Image.new("RGB", cropped.size, (255, 255, 255))
        final.paste(cropped, (0, 0))
        final.save(png_path, "PNG", dpi=(144, 144))

        print(f"  Cropped to {final.size[0]}x{final.size[1]} px")

    except Exception as e:
        print(f"  Warning: Could not crop image: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: render_mermaid.py <input.mmd> <output.png>")
        sys.exit(1)

    mmd_file = sys.argv[1]
    output_png = sys.argv[2]

    with open(mmd_file) as f:
        mmd_content = f.read()

    success = render_mermaid_to_png(mmd_content, output_png)
    if success:
        crop_to_content_and_pad(output_png)
        print("Done!")
    else:
        print("FAILED")
        sys.exit(1)
