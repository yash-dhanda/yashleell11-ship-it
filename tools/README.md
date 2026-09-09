# tools

Three generators. Only one of them runs in CI.

| script | when | needs |
|---|---|---|
| `portrait.py` | once, locally | rembg, opencv, pillow, numpy |
| `subset_font.py` | when a label or the ramp changes | fonttools[woff] |
| `stats.py` | nightly, in Actions | nothing but the standard library |
| `headings.py` | when a section is added | nothing but the standard library |

## Regenerating the portrait

Needs a Python 3.12 venv; OpenCV has no wheels for 3.13+ yet.

```bash
uv venv --python 3.12 .venv && . .venv/bin/activate
uv pip install rembg onnxruntime opencv-python-headless pillow numpy "fonttools[woff]"
python tools/portrait.py --photo build/yash.jpg --crop 215,25,700,845
```

The first run downloads a ~176 MB segmentation model, then caches it.

`--clip` and `--gamma` are the two dials worth touching. The defaults here
(1.5 and 1.2) are tuned for a low-key photo; a brightly lit one wants a gamma
above 1.0 to stop the face washing out.

## Do not regenerate stats locally

Let the action own `assets/*-{light,dark}.svg`. Your token and the workflow's
token bucket a day near a week boundary differently, so the output is never
byte-identical and you get a merge conflict every night. To preview layout
without a token, use the fixture path:

```bash
python3 tools/stats.py --fixture build/contrib_fixture.json
```
