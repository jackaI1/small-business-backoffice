"""Executed by GIMP 3's python-fu-eval, not by the system Python."""
import json
import os
from pathlib import Path

from gi.repository import Gimp, Gio

jobs = json.loads(Path(os.environ["ASSET_TOOLKIT_JOBS"]).read_text())
for job in jobs:
    image = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(job["source"]))
    if image is None:
        raise RuntimeError("GIMP could not load the Inkscape render")
    try:
        # Explicit RGB, screen resolution, and export options make the hand-off
        # predictable. The master has an opaque background; JPEG cannot carry alpha.
        if image.get_base_type() != Gimp.ImageBaseType.RGB:
            image.convert_rgb()
        image.flatten()
        image.set_resolution(96.0, 96.0)
        procedure = Gimp.get_pdb().lookup_procedure(
            "file-png-export" if job["format"] == "png" else "file-jpeg-export")
        config = procedure.create_config()
        config.set_property("run-mode", Gimp.RunMode.NONINTERACTIVE)
        config.set_property("image", image)
        config.set_property("file", Gio.File.new_for_path(job["destination"]))
        if job["format"] == "jpg":
            config.set_property("quality", .92)
            config.set_property("optimize", True)
            config.set_property("progressive", True)
        else:
            config.set_property("compression", 9)
        # Strip source metadata instead of passing private workstation details on.
        for prop in ("include-exif", "include-iptc", "include-xmp", "include-thumbnail", "include-comment"):
            if config.find_property(prop):
                config.set_property(prop, False)
        result = procedure.run(config)
        if result.index(0) != Gimp.PDBStatusType.SUCCESS:
            raise RuntimeError(f"GIMP export failed: {job['destination']}")
    finally:
        image.delete()
# The orchestrator requires this receipt because some batch failures do not
# propagate through GIMP's process exit code.
Path(os.environ["ASSET_TOOLKIT_RECEIPT"]).write_text(json.dumps(jobs))
