# Training the Growfisher YOLO model (Windows)

Everything below is typed in **PowerShell**, starting in the Growfisher folder:

```powershell
cd C:\growfisher
```

Training uses its **own** virtual environment (`.venv-yolo`), separate from the bot's `venv`.
PyTorch is big (~3 GB) and must not mix with the bot's packages.

## 1. Create the training venv (once)

```powershell
py -3.12 -m venv .venv-yolo
.venv-yolo\Scripts\Activate.ps1
```

Your prompt should now start with `(.venv-yolo)`.

> If you get *"running scripts is disabled on this system"*, run this once, then try again:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## 2. Install PyTorch with CUDA (once)

Install PyTorch **before** Ultralytics. Otherwise Ultralytics installs the CPU-only version.

1. Open <https://pytorch.org/get-started/locally/>.
2. Choose **Stable → Windows → Pip → Python →** the newest **CUDA** version listed.
3. Copy the command it shows and run it. It looks like this (the `cu1xx` number may differ):

```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
```

Then install Ultralytics and the ONNX exporter:

```powershell
pip install ultralytics onnx
```

## 3. Check that the GPU works

```powershell
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

You should see `True NVIDIA GeForce RTX 4060 Laptop GPU`.
If it prints `False` or errors: you probably got the CPU version of PyTorch. Fix it with
`pip uninstall -y torch torchvision`, then do step 2 again. Also update your NVIDIA driver if it's old.

## 4. Build the dataset

```powershell
python prepare_dataset.py
```

This reads every `.json` label next to the images in `dataset/raw` and builds `dataset/yolo/` (it never changes `dataset/raw`).
Check the table it prints:
- **WARNING: unknown label** means a typo in X-AnyLabeling. Fix that label and rerun.
- Each class should have some boxes in **val**. If a class has 0 there, label more of it.

Rerun this every time you label more images.

## 5. Train

```powershell
python train.py
```

- The first run downloads `yolo26n.pt` automatically.
- Training runs for up to 150 epochs. It stops early if the model hasn't improved for 40 epochs. Watch the progress bar for the time remaining.
- If you see **CUDA out of memory**, change `batch=8` to `batch=4` in `train.py` (both places) and rerun.
- Closing the window stops training. Rerunning starts over (as `growfisher2`, `growfisher3`, …).

## 6. Read the results

At the end, `train.py` prints one row per class:

| Column | Meaning |
|---|---|
| precision | of the boxes the model drew, how many were right |
| recall | of the real objects, how many the model found |
| mAP50 | overall score from 0 to 1. Above ~0.9 is good for this kind of fixed-camera game |
| mAP50-95 | the same, but stricter about how tight the boxes are |

A class with low recall needs more labeled examples (likely `bubble_nothing` and `bubble_emptier` at first).

Files produced, in `runs/detect/growfisher/`:
- `weights/best.pt`: the best model
- `weights/best.onnx`: the same model for the bot. It runs with `onnxruntime`, which the bot already has through RapidOCR.
- `results.png`, `confusion_matrix.png`, `val_batch0_pred.jpg`: charts, and val images with the model's boxes drawn on them. Open these.

## Next time

```powershell
cd C:\growfisher
.venv-yolo\Scripts\Activate.ps1
python prepare_dataset.py
python train.py
```
