import copy
import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

from PIL import Image
import pytest

from toolkit import export as kit


@pytest.fixture
def config():
    return json.loads((kit.ROOT/"config/targets.json").read_text())


@pytest.mark.parametrize("value", [[], None, {"campaign": "test", "revision": "v01", "targets": []},
                                    {"campaign": "test", "revision": "v01", "targets": ["invalid"]}])
def test_malformed_configuration(value):
    with pytest.raises(kit.ExportError):
        kit.validate(value)


@pytest.mark.parametrize("change", [
    {"width": 0}, {"height": True}, {"width": 16001},
    {"width": 16000, "height": 16000}, {"safe": [-1, 0, 0, 0]},
    {"safe": [540, 0, 540, 0]}, {"safe": [1, 2]},
    {"name": "../escape"}, {"layout": "missing"},
])
def test_reject_invalid_target(config, change):
    config["targets"][0].update(change)
    with pytest.raises(kit.ExportError):
        kit.validate(config)


def test_duplicate_names(config):
    config["targets"].append(copy.deepcopy(config["targets"][0]))
    with pytest.raises(kit.ExportError, match="unique"):
        kit.validate(config)


def test_unsafe_campaign(config):
    config["campaign"] = "../../private"
    with pytest.raises(kit.ExportError, match="campaign"):
        kit.validate(config)


def test_refuse_existing_output(config, tmp_path):
    marker = tmp_path/"keep.txt"
    marker.write_text("original")
    with pytest.raises(kit.ExportError, match="already exists"):
        kit.export(kit.ROOT/"assets/game-night.svg", config, tmp_path)
    assert marker.read_text() == "original"


@pytest.mark.parametrize("bounds", [(-1, 60, 30, 30), (60, 1, 30, 30),
                                    (1000, 60, 30, 30), (60, 1000, 30, 30)])
def test_detect_overflow_each_edge(config, bounds):
    assert kit.check_safe({"headline": bounds}, config["targets"][0]) == ["headline"]


def test_bounds_inside_and_rounding(config):
    assert kit.check_safe({"headline": (59.99, 60, 960, 960)}, config["targets"][0]) == []


def test_dimensions_are_checked(config, tmp_path):
    path = tmp_path/"wrong.png"
    Image.new("RGB", (20, 20)).save(path)
    with pytest.raises(kit.ExportError, match="dimensions"):
        kit.inspect_file(path, config["targets"][0], "png")


def test_format_is_checked(tmp_path):
    path = tmp_path/"disguised.jpg"
    Image.new("RGB", (20, 20)).save(path, format="PNG")
    with pytest.raises(kit.ExportError, match="format"):
        kit.inspect_file(path, {"width": 20, "height": 20}, "jpg")


def test_failed_batch_records_failed_manifest(config, tmp_path, monkeypatch):
    monkeypatch.setattr(kit, "executable", lambda name: name)
    monkeypatch.setattr(kit, "run", lambda args, **kwargs: "GIMP 3.0.4" if args[0] == "gimp" else "Inkscape 1.4")
    def fail(*args):
        raise kit.ExportError("Missing content group")
    monkeypatch.setattr(kit, "query", fail)
    output = tmp_path/"delivery"
    with pytest.raises(kit.ExportError, match="Missing"):
        kit.export(kit.ROOT/"assets/game-night.svg", config, output)
    manifest = json.loads((output/"manifest.json").read_text())
    assert manifest["status"] == "failed"
    assert "Missing" in manifest["error"]


@pytest.fixture(scope="module")
def real_delivery(tmp_path_factory):
    try:
        kit.executable("inkscape")
        kit.executable("gimp")
    except kit.ExportError as exc:
        if os.environ.get("ASSET_REQUIRE_TOOLS") == "1":
            pytest.fail(str(exc))
        pytest.skip(str(exc))
    config = json.loads((kit.ROOT/"config/targets.json").read_text())
    output = tmp_path_factory.mktemp("integration")/"delivery"
    report = kit.export(kit.ROOT/"assets/game-night.svg", config, output)
    return output, report, config


@pytest.mark.parametrize("target_index", range(7))
@pytest.mark.parametrize("fmt", ["png", "jpg"])
def test_real_outputs_dimensions_names_and_pixels(real_delivery, target_index, fmt):
    output, report, config = real_delivery
    target = config["targets"][target_index]
    # Expected naming is deliberately independent of the production helper.
    name = (f"northside-game-night_{target['name']}_{target['width']}x{target['height']}_v01.{fmt}")
    path = output/name
    entry = next(row for row in report["deliverables"] if row["file"] == name)
    assert entry["status"] == "passed"
    assert entry["safe_area"] == "passed"
    with Image.open(path) as image:
        assert image.size == (target["width"], target["height"])
        assert image.format == {"png": "PNG", "jpg": "JPEG"}[fmt]
        # A blank or entirely transparent render must not pass as a delivery.
        assert image.convert("RGB").getextrema()[0][1] - image.convert("RGB").getextrema()[0][0] > 100
        if fmt == "png":
            assert image.getpixel((0, 0))[:3] == (16, 46, 52)
    assert entry["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert entry["bytes"] == path.stat().st_size
    assert kit.check_safe(entry["content_bounds"], target) == []


def test_real_manifest_complete(real_delivery):
    output, report, config = real_delivery
    assert report["status"] == "passed"
    assert len(report["deliverables"]) == 14
    assert len(list(output.iterdir())) == 15
    assert json.loads((output/"manifest.json").read_text()) == json.loads(json.dumps(report))
    assert "Inkscape" in report["tools"]["inkscape"]
    assert "3." in report["tools"]["gimp"]


def test_real_edited_master_reflows(real_delivery, tmp_path):
    _, _, config = real_delivery
    master = tmp_path/"edited.svg"
    tree = ET.parse(kit.ROOT/"assets/game-night.svg")
    text = tree.find(".//{http://www.w3.org/2000/svg}g[@id='matchup']/{http://www.w3.org/2000/svg}text")
    text.text = "NORTHSIDE EXTRA LONG TEAM NAME"
    tree.write(master)
    config = copy.deepcopy(config)
    config["targets"] = [config["targets"][0]]
    result = kit.export(master, config, tmp_path/"edited-delivery")
    assert len(result["deliverables"]) == 2
    assert result["status"] == "passed"
