"""Render named SVG groups with Inkscape, finish delivery files in GIMP 3."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
GROUPS = ("brand", "headline", "matchup", "event", "cta", "art")
# Fractions of the usable area: left, top, width, height. All content, including
# the CTA's small demo label, is measured, fitted and checked by Inkscape.
SLOTS = {
    "portrait": [(0, 0, 1, .05), (0, .10, 1, .25), (0, .39, 1, .09),
                 (0, .76, 1, .08), (0, .89, 1, .11), (.23, .50, .54, .23)],
    "square": [(0, 0, 1, .05), (0, .12, .58, .36), (0, .55, .60, .12),
               (0, .72, .64, .10), (0, .87, .65, .13), (.65, .12, .35, .40)],
    "landscape": [(0, 0, .63, .07), (0, .13, .58, .43), (0, .62, .53, .13),
                  (.65, .71, .35, .13), (0, .82, .54, .18), (.65, .10, .35, .55)],
    "ribbon": [(0, .03, .20, .12), (0, .22, .20, .74), (.26, .23, .20, .50),
               (.52, .23, .20, .50), (.79, .27, .21, .50), (.215, .37, .035, .30)],
}
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class ExportError(ValueError):
    pass


def run(args: list[str], *, env=None, timeout=180) -> str:
    """Bound runtime and keep potentially noisy tool logs out of the hand-off."""
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout, env=env)
    if result.returncode:
        raise ExportError(f"{Path(args[0]).name} failed ({result.returncode}): "
                          f"{result.stderr[-1800:]} {result.stdout[-800:]}")
    return result.stdout.strip()


def executable(name: str) -> str:
    override = os.environ.get(name.upper() + "_BIN")
    # The GUI executable may initialize GTK even with --no-interface. Prefer
    # the separately built console executable on machines without a display.
    candidates = [override] if override else {
        "gimp": ["gimp-console", "gimp-console-3.0",
                 "/Applications/GIMP.app/Contents/MacOS/gimp-console", "gimp"],
        "inkscape": ["inkscape", "/Applications/Inkscape.app/Contents/MacOS/inkscape"],
    }[name]
    found = next((path for candidate in candidates if (path := shutil.which(candidate))), None)
    if found:
        return found
    raise ExportError(f"Install {name}; see README. Override with {name.upper()}_BIN.")


def validate(config: dict) -> None:
    if not isinstance(config, dict):
        raise ExportError("Configuration must be a JSON object")
    for key in ("campaign", "revision"):
        if not isinstance(config.get(key), str) or not SLUG.fullmatch(config[key]):
            raise ExportError(f"{key} must be a lowercase name separated by hyphens")
    targets = config.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ExportError("At least one target is required")
    seen = set()
    for target in targets:
        if not isinstance(target, dict):
            raise ExportError("Each target must be a JSON object")
        name = target.get("name", "")
        if not isinstance(name, str) or not SLUG.fullmatch(name) or name in seen:
            raise ExportError("Target names must be unique lowercase names")
        seen.add(name)
        if target.get("layout") not in SLOTS:
            raise ExportError(f"Unknown layout for {name}")
        w, h = target.get("width"), target.get("height")
        if any(type(v) is not int or not 1 <= v <= 16000 for v in (w, h)) or w*h > 40_000_000:
            raise ExportError(f"Invalid or excessive dimensions for {name}")
        safe = target.get("safe")
        if not isinstance(safe, list) or len(safe) != 4 or any(type(v) is not int or v < 0 for v in safe):
            raise ExportError(f"safe must contain left, top, right, bottom pixel insets for {name}")
        if safe[0]+safe[2] >= w or safe[1]+safe[3] >= h:
            raise ExportError(f"Safe area is empty for {name}")


def filename(config: dict, target: dict, fmt: str) -> str:
    return (f"{config['campaign']}_{target['name']}_{target['width']}x{target['height']}_"
            f"{config['revision']}.{fmt}")


def query(inkscape: str, svg: Path) -> dict:
    bounds = {}
    for line in run([inkscape, str(svg), "--query-all"]).splitlines():
        fields = line.split(",")
        if len(fields) == 5 and fields[0] in GROUPS:
            bounds[fields[0]] = tuple(float(n) for n in fields[1:])
    if set(bounds) != set(GROUPS):
        raise ExportError("Master must contain all six named content groups")
    if any(w <= 0 or h <= 0 for _, _, w, h in bounds.values()):
        raise ExportError("Master content groups must have nonempty bounds")
    return bounds


def compose(master: Path, dest: Path, target: dict, bounds: dict) -> None:
    tree = ET.parse(master)
    root = tree.getroot()
    w, h = target["width"], target["height"]
    root.set("width", str(w))
    root.set("height", str(h))
    root.set("viewBox", f"0 0 {w} {h}")
    nodes = {node.get("id"): node for node in root.iter() if node.get("id")}
    nodes["background"].set("width", str(w))
    nodes["background"].set("height", str(h))
    nodes["accent"].set("d", f"M0 {h-8} H{w} V{h} H0 Z")
    left, top, right, bottom = target["safe"]
    usable_w, usable_h = w-left-right, h-top-bottom
    for name, slot in zip(GROUPS, SLOTS[target["layout"]]):
        node = nodes[name]
        if node not in list(root):
            raise ExportError(f"Keep {name} as a top-level group in the master")
        sx, sy, sw, sh = slot
        x, y, bw, bh = bounds[name]
        scale = min(usable_w*sw/bw, usable_h*sh/bh)
        tx = left+sx*usable_w-x*scale
        ty = top+sy*usable_h-y*scale
        # Fit a wrapper around the measured master group, preserving any edits
        # to the group's own transform, paths, text or stroke widths.
        index = list(root).index(node)
        wrapper = ET.Element("{http://www.w3.org/2000/svg}g", {
            "id": name, "transform": f"matrix({scale} 0 0 {scale} {tx} {ty})"})
        node.set("id", name+"-content")
        root.remove(node)
        wrapper.append(node)
        root.insert(index, wrapper)
    tree.write(dest, encoding="utf-8", xml_declaration=True)


def check_safe(bounds: dict, target: dict) -> list[str]:
    left, top, right, bottom = target["safe"]
    # Small rounding tolerance for Inkscape's printed floating point bounds.
    return [name for name, (x, y, w, h) in bounds.items()
            if x < left-.1 or y < top-.1 or x+w > target["width"]-right+.1
            or y+h > target["height"]-bottom+.1]


def inspect_file(path: Path, target: dict, fmt: str) -> dict:
    with Image.open(path) as image:
        image.load()
        if image.size != (target["width"], target["height"]):
            raise ExportError(f"Wrong output dimensions: {path.name}")
        if image.format != {"png": "PNG", "jpg": "JPEG"}[fmt]:
            raise ExportError(f"Wrong output format: {path.name}")
    return {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def export(master: Path, config: dict, output: Path) -> dict:
    validate(config)
    # Never mix a new revision with stale or partially failed deliveries.
    if output.exists():
        raise ExportError(f"Output already exists: {output}. Choose a new folder or remove it explicitly.")
    inkscape, gimp = executable("inkscape"), executable("gimp")
    versions = {"inkscape": run([inkscape, "--version"]), "gimp": run([gimp, "--version"])}
    if not re.search(r"(?:GIMP|GNU Image Manipulation Program).*\b3\.", versions["gimp"], re.IGNORECASE):
        raise ExportError("GIMP 3 is required (Python batch interpreter)")
    output.mkdir(parents=True)
    report = {"campaign": config["campaign"], "revision": config["revision"],
              "master_sha256": hashlib.sha256(master.read_bytes()).hexdigest(),
              "tools": versions, "status": "failed", "deliverables": []}
    try:
        with tempfile.TemporaryDirectory(prefix="asset-toolkit-") as scratch:
            temp = Path(scratch)
            bounds = query(inkscape, master)
            jobs = []
            for target in config["targets"]:
                svg, png = temp/f"{target['name']}.svg", temp/f"{target['name']}.png"
                compose(master, svg, target, bounds)
                measured = query(inkscape, svg)
                unsafe = check_safe(measured, target)
                if unsafe:
                    raise ExportError(f"Unsafe content in {target['name']}: {', '.join(unsafe)}")
                run([inkscape, str(svg), "--export-area-page", f"--export-filename={png}",
                     f"--export-width={target['width']}", f"--export-height={target['height']}"])
                for fmt in ("png", "jpg"):
                    name = filename(config, target, fmt)
                    report["deliverables"].append({"file": name, "target": target["name"],
                        "width": target["width"], "height": target["height"], "format": fmt,
                        "safe_insets_ltrb": target["safe"], "safe_area": "passed",
                        "content_bounds": measured, "status": "pending"})
                    jobs.append({"source": str(png), "destination": str((output/name).resolve()), "format": fmt})
            jobfile = temp/"jobs.json"
            jobfile.write_text(json.dumps(jobs))
            script = ROOT/"toolkit"/"gimp_finish.py"
            # A separate config and --new-instance protect the owner's open GIMP session.
            env = dict(os.environ, GIMP3_DIRECTORY=str(temp/"gimp-profile"),
                       ASSET_TOOLKIT_JOBS=str(jobfile), ASSET_TOOLKIT_RECEIPT=str(temp/"receipt.json"))
            run([gimp, "--no-interface", "--new-instance", "--no-data", "--no-fonts",
                 "--batch-interpreter=python-fu-eval", "--batch",
                 f"exec(compile(open({str(script)!r}).read(), {str(script)!r}, 'exec'))",
                 "--quit"], env=env, timeout=300)
            receipt = temp/"receipt.json"
            if not receipt.exists() or json.loads(receipt.read_text()) != jobs:
                raise ExportError("GIMP did not confirm every export")
            for entry, job in zip(report["deliverables"], jobs):
                entry.update(inspect_file(Path(job["destination"]), entry, job["format"]))
                entry["status"] = "passed"
        report["status"] = "passed"
        return report
    except Exception as exc:
        report["error"] = str(exc)[-2000:]
        for entry in report["deliverables"]:
            entry["status"] = "failed"
        raise
    finally:
        (output/"manifest.json").write_text(json.dumps(report, indent=2)+"\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master", type=Path, default=ROOT/"assets/game-night.svg")
    parser.add_argument("--config", type=Path, default=ROOT/"config/targets.json")
    parser.add_argument("--output", type=Path, default=ROOT/"dist/game-night-v01")
    args = parser.parse_args()
    try:
        report = export(args.master.resolve(), json.loads(args.config.read_text()), args.output.resolve())
    except (ValueError, OSError, subprocess.TimeoutExpired, ET.ParseError) as exc:
        print(f"Export failed: {exc}")
        return 1
    print(f"Exported {len(report['deliverables'])} checked files to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
