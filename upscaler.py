import math
import os
import urllib.request
from pathlib import Path

import cv2
import numpy as np

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
import torch
from PIL import Image


MODELS_DIR = Path(__file__).parent / "models"

_MODEL_REGISTRY = {
    ("general", 2): {
        "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth",
        "filename": "RealESRGAN_x2plus.pth",
        "scale": 2,
        "num_block": 23,
    },
    ("general", 4): {
        "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
        "filename": "RealESRGAN_x4plus.pth",
        "scale": 4,
        "num_block": 23,
    },
    ("anime", 4): {
        "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth",
        "filename": "RealESRGAN_x4plus_anime_6B.pth",
        "scale": 4,
        "num_block": 6,
    },
}

_UPSAMPLER_CACHE = {}


def _force_cpu() -> bool:
    return os.environ.get("UPSCAL_FORCE_CPU", "").strip().lower() in {"1", "true", "yes", "on"}


def _cuda_available() -> bool:
    return not _force_cpu() and torch.cuda.is_available()


def _mps_available() -> bool:
    if _force_cpu():
        return False
    mps = getattr(getattr(torch, "backends", None), "mps", None)
    if mps is None:
        return False
    try:
        return bool(mps.is_available())
    except Exception:
        return False


def _runtime_device() -> torch.device:
    if _cuda_available():
        return torch.device("cuda")
    if _mps_available():
        return torch.device("mps")
    return torch.device("cpu")


def _configure_runtime():
    cv2.setUseOptimized(True)
    if _cuda_available():
        torch.backends.cudnn.benchmark = True
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
    else:
        threads = max(1, min(8, (os.cpu_count() or 2) - 1))
        torch.set_num_threads(threads)


_configure_runtime()


def get_device_info() -> str:
    if _cuda_available():
        name = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
        return f"GPU: {name} | VRAM: {vram:.1f} GB"
    if _mps_available():
        return "GPU: Apple Metal (MPS)"
    return "CPU mode"


def _ensure_model(cfg: dict) -> Path:
    MODELS_DIR.mkdir(exist_ok=True)
    path = MODELS_DIR / cfg["filename"]
    if path.exists():
        return path

    try:
        print(f"[download] {cfg['filename']} ...")
        tmp_path = path.with_suffix(path.suffix + ".download")
        with urllib.request.urlopen(cfg["url"], timeout=30) as response:
            with tmp_path.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
        tmp_path.replace(path)
    except Exception:
        if "tmp_path" in locals() and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise FileNotFoundError(
            f"Model file not found: {cfg['filename']}\n"
            f"Put it in the models folder manually.\n"
            f"URL: {cfg['url']}"
        )
    return path


def count_tiles(img_h: int, img_w: int, tile_size: int) -> int:
    if tile_size <= 0:
        return 1
    return math.ceil(img_h / tile_size) * math.ceil(img_w / tile_size)


def _use_half_precision() -> bool:
    if not _cuda_available():
        return False
    try:
        major, _minor = torch.cuda.get_device_capability(0)
        return major >= 7
    except Exception:
        return True


def _build_upsampler(cfg: dict, tile: int):
    from esrgan_runtime import RRDBNet, RealESRGANer

    path = _ensure_model(cfg)
    use_half = _use_half_precision()
    device = _runtime_device()
    key = (cfg["filename"], int(tile), str(device), use_half)

    cached = _UPSAMPLER_CACHE.get(key)
    if cached is not None:
        return cached

    net = RRDBNet(
        num_in_ch=3,
        num_out_ch=3,
        num_feat=64,
        num_block=cfg["num_block"],
        num_grow_ch=32,
        scale=cfg["scale"],
    )
    upsampler = RealESRGANer(
        scale=cfg["scale"],
        model_path=str(path),
        model=net,
        tile=tile,
        tile_pad=32,
        pre_pad=0,
        half=use_half,
        device=device,
    )
    _UPSAMPLER_CACHE[key] = upsampler
    return upsampler


def _resize_mask(mask: np.ndarray, width: int, height: int) -> np.ndarray:
    if mask.shape[1] == width and mask.shape[0] == height:
        return mask
    return cv2.resize(mask, (width, height), interpolation=cv2.INTER_LINEAR)


def _mask_work_size(width: int, height: int, max_side: int = 1800) -> tuple[int, int]:
    scale = min(1.0, max_side / max(width, height))
    return max(1, int(width * scale)), max(1, int(height * scale))


def _texture_mask(original_bgr: np.ndarray, width: int, height: int) -> np.ndarray:
    work_w, work_h = _mask_work_size(width, height)
    small = cv2.resize(original_bgr, (work_w, work_h), interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)

    local_sq = cv2.GaussianBlur(gray * gray, (9, 9), sigmaX=2.5)
    local_mu = cv2.GaussianBlur(gray, (9, 9), sigmaX=2.5)
    local_var = np.clip(local_sq - local_mu * local_mu, 0, None)
    mask = np.sqrt(local_var)
    mask_max = mask.max()
    if mask_max > 1e-6:
        mask = mask / mask_max
    mask = _resize_mask(mask, width, height)
    return mask[:, :, np.newaxis].astype(np.float32)


def _edge_mask(original_bgr: np.ndarray, width: int, height: int) -> np.ndarray:
    work_w, work_h = _mask_work_size(width, height)
    small = cv2.resize(original_bgr, (work_w, work_h), interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    canny_strong = cv2.Canny(gray, 25, 80).astype(np.float32) / 255.0
    canny_soft = cv2.Canny(gray, 12, 45).astype(np.float32) / 255.0
    canny_d = cv2.dilate(canny_strong, np.ones((3, 3), dtype=np.uint8), iterations=2)
    mask = cv2.GaussianBlur(canny_d * 0.7 + canny_soft * 0.3, (0, 0), sigmaX=1.0)
    mask = _resize_mask(mask, width, height)
    return mask[:, :, np.newaxis].astype(np.float32)


def _restore_details(
    esrgan_bgr: np.ndarray,
    original_bgr: np.ndarray,
    target_h: int,
    target_w: int,
    strength: float,
    model_type: str = "general",
) -> np.ndarray:
    if strength <= 0.0:
        return esrgan_bgr

    strength = float(np.clip(strength, 0.0, 1.0))
    is_anime = model_type == "anime"
    detail_gain = strength * (0.66 if is_anime else 1.0)
    bicubic = cv2.resize(original_bgr, (target_w, target_h), interpolation=cv2.INTER_CUBIC).astype(np.float32)
    esrgan_f = esrgan_bgr.astype(np.float32)

    b0 = cv2.GaussianBlur(bicubic, (0, 0), sigmaX=0.5)
    b1 = cv2.GaussianBlur(bicubic, (0, 0), sigmaX=1.0)
    b2 = cv2.GaussianBlur(bicubic, (0, 0), sigmaX=2.0)
    b3 = cv2.GaussianBlur(bicubic, (0, 0), sigmaX=4.0)

    blended = (
        esrgan_f
        + (bicubic - b0) * (detail_gain * (1.15 if is_anime else 1.6))
        + (b0 - b1) * (detail_gain * (0.90 if is_anime else 1.2))
        + (b1 - b2) * (detail_gain * (0.50 if is_anime else 0.8))
        + (b2 - b3) * (detail_gain * (0.20 if is_anime else 0.4))
    )
    del b0, b1, b2, b3

    tex_mask = _texture_mask(original_bgr, target_w, target_h)
    pull = detail_gain * (0.18 if is_anime else 0.35)
    blended = blended * (1.0 - tex_mask * pull) + bicubic * (tex_mask * pull)
    del tex_mask

    edge_mask = _edge_mask(original_bgr, target_w, target_h)
    blended_u8 = np.clip(blended, 0, 255).astype(np.uint8)
    blur_tight = cv2.GaussianBlur(blended_u8, (0, 0), sigmaX=0.6)
    edge_detail = blended_u8.astype(np.float32) - blur_tight.astype(np.float32)
    blended = blended + edge_detail * edge_mask * (detail_gain * (0.55 if is_anime else 1.3))
    del edge_mask, edge_detail, blur_tight

    result_u8 = np.clip(blended, 0, 255).astype(np.uint8)
    blur_final = cv2.GaussianBlur(result_u8, (0, 0), sigmaX=0.8)
    unsharp = result_u8.astype(np.float32) - blur_final.astype(np.float32)
    final = result_u8.astype(np.float32) + unsharp * (detail_gain * (0.08 if is_anime else 0.2))

    return np.clip(final, 0, 255).astype(np.uint8)


def _enhance_photo_clarity(bgr: np.ndarray, strength: float) -> np.ndarray:
    strength = float(np.clip(strength, 0.0, 1.0))
    if strength <= 0:
        return bgr

    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l, a, bb = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=1.15 + strength * 0.75, tileGridSize=(8, 8))
    l2 = clahe.apply(l)
    contrast = cv2.cvtColor(cv2.merge((l2, a, bb)), cv2.COLOR_LAB2BGR)

    base = cv2.addWeighted(bgr, 1.0 - strength * 0.20, contrast, strength * 0.20, 0)
    blur = cv2.GaussianBlur(base, (0, 0), sigmaX=1.05)
    sharp = cv2.addWeighted(base, 1.0 + strength * 0.34, blur, -strength * 0.34, 0)

    gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    edge = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)
    edge = np.abs(edge)
    edge_max = edge.max()
    if edge_max > 1e-6:
        edge = edge / edge_max
    edge = cv2.GaussianBlur(edge, (0, 0), sigmaX=1.0)[:, :, np.newaxis]

    out = base.astype(np.float32) * (1.0 - edge * 0.45) + sharp.astype(np.float32) * (edge * 0.45)
    return np.clip(out, 0, 255).astype(np.uint8)


def _stabilize_line_art(bgr: np.ndarray, original_bgr: np.ndarray, strength: float) -> np.ndarray:
    strength = float(np.clip(strength, 0.0, 1.0))
    if strength <= 0:
        return bgr

    h, w = bgr.shape[:2]
    edge = _edge_mask(original_bgr, w, h)
    smooth = cv2.bilateralFilter(bgr, d=5, sigmaColor=24, sigmaSpace=3)
    blend = min(0.42, 0.20 + strength * 0.22)
    out = bgr.astype(np.float32) * (1.0 - edge * blend) + smooth.astype(np.float32) * (edge * blend)

    # A very light final crisping keeps line art readable without reintroducing
    # the stair-step edges that stronger unsharp masks tend to create.
    out_u8 = np.clip(out, 0, 255).astype(np.uint8)
    blur = cv2.GaussianBlur(out_u8, (0, 0), sigmaX=0.55)
    final = cv2.addWeighted(out_u8, 1.08, blur, -0.08, 0)
    return np.clip(final, 0, 255).astype(np.uint8)


def _model_label(model_type: str) -> str:
    return "그림" if model_type == "anime" else "사진"


def upscale_image(
    pil_image: Image.Image,
    model_type: str,
    target_scale: int,
    output_dpi: int,
    tile_size: int = 512,
    detail_strength: float = 0.4,
    progress_cb=None,
) -> Image.Image:
    """Return the upscaled PIL image. DPI is embedded in image.info."""

    def step(frac: float, msg: str):
        if progress_cb:
            progress_cb(frac, msg)

    original_bgr = cv2.cvtColor(np.array(pil_image.convert("RGB")), cv2.COLOR_RGB2BGR)
    h, w = original_bgr.shape[:2]
    img_bgr = original_bgr.copy()
    label = _model_label(model_type)

    step(0.03, f"이미지 분석 중 · {w} x {h}")

    if target_scale == 8:
        cfg4 = _MODEL_REGISTRY[(model_type, 4)]
        cfg2 = _MODEL_REGISTRY[("general", 2)]
        tiles = count_tiles(h, w, tile_size)

        step(0.07, f"{label} 모델 준비 중 · 1/2 · 타일 {tiles}")
        up4 = _build_upsampler(cfg4, tile_size)
        step(0.14, "업스케일링 중 · 1/2 · 4x")
        img_bgr, _ = up4.enhance(img_bgr, outscale=4)

        h2, w2 = img_bgr.shape[:2]
        tiles2 = count_tiles(h2, w2, tile_size)
        step(0.58, f"사진 모델 준비 중 · 2/2 · 타일 {tiles2}")
        up2 = _build_upsampler(cfg2, tile_size)
        step(0.66, "업스케일링 중 · 2/2 · 2x")
        img_bgr, _ = up2.enhance(img_bgr, outscale=2)

    elif target_scale == 2 and model_type == "anime":
        cfg = _MODEL_REGISTRY[("anime", 4)]
        tiles = count_tiles(h, w, tile_size)
        step(0.07, f"그림 모델 준비 중 · 타일 {tiles}")
        up = _build_upsampler(cfg, tile_size)
        step(0.18, "업스케일링 중 · 그림 2x")
        img_bgr, _ = up.enhance(img_bgr, outscale=2)

    else:
        cfg = _MODEL_REGISTRY[(model_type, target_scale)]
        tiles = count_tiles(h, w, tile_size)
        step(0.07, f"{label} 모델 준비 중 · 타일 {tiles}")
        up = _build_upsampler(cfg, tile_size)
        step(0.18, f"업스케일링 중 · {target_scale}x")
        img_bgr, _ = up.enhance(img_bgr, outscale=target_scale)

    out_h, out_w = img_bgr.shape[:2]
    step(0.92, f"디테일 복원 중 · 강도 {int(detail_strength * 100)}%")
    img_bgr = _restore_details(img_bgr, original_bgr, out_h, out_w, detail_strength, model_type=model_type)
    if model_type == "anime":
        img_bgr = _stabilize_line_art(img_bgr, original_bgr, detail_strength)
    else:
        img_bgr = _enhance_photo_clarity(img_bgr, detail_strength)

    step(0.98, "결과 변환 중")
    result = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
    result.info["dpi"] = (output_dpi, output_dpi)
    return result
