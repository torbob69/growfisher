# Trains YOLO on dataset/yolo (run prepare_dataset.py first), then exports best.pt to ONNX.
from pathlib import Path

import torch
from ultralytics import YOLO

DATA = "../dataset/yolo/data.yaml"
IMGSZ = 1280  # the splash is tiny; smaller sizes shrink it to a few pixels
# Each dataloader worker on Windows is a full Python+torch process; the default 8 ran out
# of virtual memory (error 1455). 2 is plenty for ~600 images; use 0 if it still happens.
WORKERS = 2


def main():
    if not Path(DATA).exists():
        raise SystemExit(f"{DATA} not found — run: python prepare_dataset.py")
    if torch.cuda.is_available():
        device = 0
        print(f"Training on GPU: {torch.cuda.get_device_name(0)}")
    else:
        device = "cpu"
        print("WARNING: no CUDA GPU found — training on CPU will be very slow. See TRAINING.md step 3.")

    model = YOLO("yolo26n.pt")  # downloads on first run
    model.train(
        data=DATA,
        imgsz=IMGSZ,
        epochs=150,
        patience=40,      # stop early if val doesn't improve for 40 epochs
        fliplr=0.0,       # the game never shows mirrored text
        batch=4,          # ponytail: fits 8GB VRAM at 1280; lower to 4 on "CUDA out of memory"
        workers=WORKERS,
        device=device,
        project="runs/detect",
        name="growfisher",
    )

    best = Path(model.trainer.best)
    print(f"\nBest model: {best}")
    metrics = YOLO(best).val(data=DATA, imgsz=IMGSZ, device=device, batch=4,
                             workers=WORKERS, plots=False)
    print(f"\n{'class':<16}{'precision':>10}{'recall':>8}{'mAP50':>8}{'mAP50-95':>10}")
    for i, c in enumerate(metrics.ap_class_index):
        p, r, m50, m = metrics.box.class_result(i)
        print(f"{metrics.names[int(c)]:<16}{p:>10.3f}{r:>8.3f}{m50:>8.3f}{m:>10.3f}")
    print(f"{'all':<16}{metrics.box.mp:>10.3f}{metrics.box.mr:>8.3f}"
          f"{metrics.box.map50:>8.3f}{metrics.box.map:>10.3f}")

    onnx = YOLO(best).export(format="onnx", imgsz=IMGSZ)
    print(f"\nONNX model: {onnx}")


if __name__ == "__main__":  # required on Windows: dataloader workers re-import this file
    main()