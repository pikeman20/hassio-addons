from __future__ import annotations

CHECKPOINT_DIR = "./checkpoints"

# Ordered list: (filename, OpenSourceModel constructor arg name)
CHECKPOINT_FILES = [
    ("depth_anything_v2_vits_slim.onnx", "depth_model_path"),
    ("isnet_uint8.onnx",                 "isnet_model_path"),
    ("focus_matting_1.0.0.onnx",         "matting_model_path"),
    ("focus_refiner_1.0.0.onnx",         "refiner_model_path"),
]

CHECKPOINT_PATHS = [f"{CHECKPOINT_DIR}/{name}" for name, _ in CHECKPOINT_FILES]
