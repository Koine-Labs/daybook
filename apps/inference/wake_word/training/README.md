# Training "Hey Regis" as a custom wake word

Goal: produce `hey_regis.onnx` and drop it into `../models/` so Daybook's wake-word detector triggers on **"Hey Regis"** (or just **"Regis"**) instead of the placeholder **"Hey Jarvis"**.

You have three paths. Pick one. Output of any of them is a `.onnx` file you save to `apps/inference/wake_word/models/hey_regis.onnx`.

> **Note:** The Hugging Face Space (`huggingface.co/spaces/davidscripka/openWakeWord-Training`) referenced in older docs is no longer reachable as of 2026-05-17. Use the official Colab notebook below instead.

---

## Path A — Official Colab notebook (easiest, no install, ~30-60 min)  ⭐ recommended

The openWakeWord maintainer's official simplified training notebook. Synthesizes positive samples via Piper TTS, augments with noise, trains a classifier, exports `.onnx`. Runs on Colab's free T4 GPU.

1. Open the official Colab notebook: **<https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb?usp=sharing>**
2. Runtime → Change runtime type → **T4 GPU** (free tier)
3. In the first cell, set: `target_word = "hey regis"`
4. Run all cells (Runtime → Run all). Takes ~30-60 min total — most of it is sample synthesis + training.
5. The final cell downloads the resulting `hey_regis.onnx` to your machine.
6. Copy it to: `apps/inference/wake_word/models/hey_regis.onnx`
7. Run Daybook with: `DAYBOOK_WAKE_WORD=hey_regis python -m daybook`

The Colab notebook is the canonical path right now — it's what the openWakeWord README itself recommends.

---

## Path B — Local training on your 4080 desktop (best privacy, ~15-30 min)

If you'd rather train locally (everything stays on your machine).

Requirements:
- NVIDIA GPU with CUDA (your 4080 Super qualifies)
- Python 3.10+ with `torch` (CUDA build), `openwakeword`, `piper-tts`, `audiomentations`

```bash
# On your 4080 desktop, NOT the Mac (slow on CPU):
git clone https://github.com/dscripka/openWakeWord.git
cd openWakeWord
pip install -r requirements.txt
pip install piper-tts audiomentations
```

Then download the same Colab notebook (`https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb`) as `.ipynb` (File → Download → `.ipynb`) and run it locally:

```bash
jupyter notebook automatic_model_training.ipynb
# Set target_word = "hey regis" in cell 1, then Run All
```

Output `.onnx` lands in the notebook's working directory. Copy to `apps/inference/wake_word/models/hey_regis.onnx`.

---

## Path C — Picovoice Porcupine (alternative library, ~30 seconds for the model itself)

If openWakeWord training proves finicky, **Picovoice Porcupine** is a commercial-grade wake-word library with a console UI that generates custom wake words in ~30 seconds. Free for personal use.

Trade-off: requires switching from openWakeWord to `pvporcupine`, which means swapping out `apps/inference/wake_word/detector.py`. Output files (`.ppn`) are platform-specific (one for Mac, one for Linux/Pi).

1. Sign up at <https://console.picovoice.ai/> (free)
2. Console → Wake Word → New → enter "Hey Regis" + select platforms (macOS arm64 + Linux arm64 for Pi)
3. Get your AccessKey from the console
4. Generated `.ppn` files download in ~30 seconds
5. `pip install pvporcupine` and use their SDK

Defer this path unless openWakeWord training repeatedly fails. The openWakeWord path is more aligned with our current architecture.

---

## After training — drop in + activate

Once the `.onnx` file is at `apps/inference/wake_word/models/hey_regis.onnx`:

```bash
# Use it temporarily
DAYBOOK_WAKE_WORD=hey_regis python -m daybook

# Or set it permanently in your shell rc:
export DAYBOOK_WAKE_WORD=hey_regis

# Or use an arbitrary path via env var (overrides the models/ lookup):
DAYBOOK_WAKE_WORD_MODEL_PATH=/path/to/custom.onnx python -m daybook
```

The detector auto-discovers anything under `models/<name>.onnx` when you pass `--wake-word <name>` or set `DAYBOOK_WAKE_WORD=<name>`.

---

## Quality notes

- **First-try accuracy** with synthetic data only is decent (~85-90% recall, low false positives for an uncommon-sounding phrase like "Hey Regis"). If you find it under-triggers or over-triggers, the fix is to fine-tune with a few hundred samples of your actual voice saying it — see openWakeWord's repo for the fine-tuning workflow.
- **"Hey Regis" is a good wake phrase** — two syllables, distinct vowels, uncommon in normal speech. Compare to "Hey Siri" or "Alexa" which were specifically chosen for the same properties.
- **Just "Regis"** alone is harder — single short word means higher false positive risk. Recommend `Hey Regis` as primary, `Regis` only as a secondary variant during training.
- Threshold default is `0.5`. If your trained model fires too often, raise to `0.6` via `--threshold 0.6`. If it misses, lower to `0.4`.

---

## What I'd recommend you do tonight

1. **Use the placeholder for now**: `python -m daybook` (defaults to `hey_jarvis` wake_word mode).
2. **Open the Hugging Face Space tab in a browser**: <https://huggingface.co/spaces/davidscripka/openWakeWord-Training>. Type "Hey Regis", click train. Let it run in the background while you do other things.
3. **In ~30 min, download** the `.onnx`, drop into `models/`, re-launch with `DAYBOOK_WAKE_WORD=hey_regis python -m daybook`.

Then Regis answers to his actual name.
