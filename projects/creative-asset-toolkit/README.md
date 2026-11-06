# creative-asset-toolkit

I built a promotion artwork exporter to learn how the underlying idea works. This is a learning project.

## Run it

I use Inkscape for the editable drawing and rendering, and GIMP 3 for the final image exports. These are open-source alternatives to Illustrator and Photoshop. Python runs the steps without opening either editor's interface.

I use Python 3.11 or newer. On macOS, with [Homebrew](https://brew.sh/) installed:

```sh
brew install python
brew install --cask inkscape gimp
"$(brew --prefix)/bin/python3" -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m toolkit.export
```

On Debian 13, install the graphics tools below. Follow the same clone and environment steps above, using `python3 -m venv .venv` in place of the Homebrew Python command:

```sh
sudo apt-get update
sudo apt-get install inkscape gimp gir1.2-gimp-3.0 python3-gi python3-gi-cairo python3-venv fonts-dejavu-core
```

## Change the promotion

1. Open [assets/game-night.svg](assets/game-night.svg) in Inkscape. Change the headline, teams, date or colours. Keep the six named groups: `brand`, `headline`, `matchup`, `event`, `cta` and `art`.
2. Edit [config/targets.json](config/targets.json) to change the campaign name, revision or output sizes. Safe-area values are pixel insets in left, top, right, bottom order. They are my example delivery rules; check the actual screen owner's requirements.
3. Run a new export into an unused folder:

```sh
python -m toolkit.export --output dist/game-night-v02
```

Change `revision` to `v02` in the configuration too if the filenames should carry that revision. The exporter refuses an existing output folder so I cannot accidentally mix old and new deliveries. To use a different drawing or configuration:

```sh
python -m toolkit.export --master assets/game-night.svg --config config/targets.json --output dist/custom
```

| Delivery preset | Pixels | Example safe insets, L/T/R/B |
| --- | --- | --- |
| Social square | 1080 × 1080 | 60 / 60 / 60 / 60 |
| Social story | 1080 × 1920 | 96 / 250 / 96 / 300 |
| Social landscape | 1200 × 630 | 50 / 40 / 50 / 40 |
| Web banner | 1600 × 600 | 60 / 40 / 60 / 40 |
| Outdoor digital sign | 1080 × 1920 | 90 / 100 / 90 / 100 |
| Arena screen | 1920 × 1080 | 96 / 54 / 96 / 54 |
| Arena ribbon | 3840 × 480 | 100 / 40 / 100 / 40 |

Each preset produces a PNG and a JPEG. For example, `northside-game-night_arena-screen_1920x1080_v01.jpg` tells me the campaign, destination, dimensions and revision without opening the image.

## Tests and limits

There are 1 test source files in this copy. No test pass count is claimed here: I have not re-run the project suite as part of this move. This is a source snapshot, and running it on a new machine may need environment-specific setup.


Project checks run from this directory through the path-filtered hub workflows: (removed workflow).

The relocated workflow did not complete successfully within the migration batch. Local test sources remain available.
