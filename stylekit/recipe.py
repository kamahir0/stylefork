"""Clean Style Preset isolation, prompt-leak sanitization, and workflow assembly (Layer 1)."""

from __future__ import annotations

import re
from typing import Any

def _unwrap_prompt_graph(raw):
    return raw.get("prompt", raw) if isinstance(raw, dict) else {}


class PresetContaminationError(ValueError):
    """Raised when a StylePreset retains scene, prop, beverage, or expression leakage."""


# Scene, prop, beverage, clothing, and expression-drift tokens that must NOT leak
# into pure StylePreset templates unless explicitly whitelisted by the caller.
_LEAK_TOKEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("beverage", re.compile(r"\b(coffee|coffee cup|espresso|latte|cappuccino|tea|teacup|matcha|boba|soda|juice|drink|drinking|mug|cup|bottle|pet bottle|straw)\b", re.I)),
    ("hand_prop_action", re.compile(r"\b(holding|holding a|holding cup|holding phone|holding book|carrying|tray|parfait|smartphone|cellphone|phone)\b", re.I)),
    ("setting_leak", re.compile(r"\b(classroom|school desk|desk|chair|cafe|coffee shop|coffeeshop|kitchen|bedroom|rooftop|gymnasium|stall|counter|hallway|corridor|terrace)\b", re.I)),
    ("costume_leak", re.compile(r"\b(school uniform|serafuku|sailor collar|blazer|maid|apron|waitress|happi|jersey|track jacket|swimsuit|bikini|camisole)\b", re.I)),
    ("expression_drift", re.compile(r"\b(sweat|wet skin|heavy blush|half-closed eyes|parted lips|ahegao|drooling|seductive)\b", re.I)),
    ("subject_lock", re.compile(r"^(solo|1girl|1boy|2girls|multiple girls|couple)$", re.I)),
)


def split_prompt_tokens(prompt_text: str) -> list[str]:
    """Split a tag-based prompt string cleanly into normalized non-empty tokens."""
    if not prompt_text:
        return []
    parts = re.split(r"[,;\n]+", prompt_text)
    tokens: list[str] = []
    seen: set[str] = set()
    for part in parts:
        cleaned = re.sub(r"\s+", " ", part).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            tokens.append(cleaned)
    return tokens


def classify_prompt_token(token: str) -> str | None:
    """Return leak category name if `token` encodes scene/prop/costume/subject drift, else None."""
    norm = re.sub(r"^[\(\[]+|[\)\]]+(?::[0-9.]+)?$", "", token).strip()
    norm = re.sub(r":[0-9.]+$", "", norm).strip()
    for category, pattern in _LEAK_TOKEN_PATTERNS:
        if pattern.search(norm):
            return category
    return None


def find_leaked_tokens(
    tokens_or_text: str | list[str],
    *,
    allow_tokens: set[str] | None = None,
) -> list[dict[str, str]]:
    """Detect any leaked scene, prop, beverage, costume, or subject-lock tokens."""
    allowed = {t.strip().lower() for t in (allow_tokens or set()) if t.strip()}
    tokens = split_prompt_tokens(tokens_or_text) if isinstance(tokens_or_text, str) else list(tokens_or_text)
    leaks: list[dict[str, str]] = []
    for tok in tokens:
        if tok.lower() in allowed:
            continue
        cat = classify_prompt_token(tok)
        if cat is not None:
            leaks.append({"token": tok, "category": cat})
    return leaks


def strip_leaked_tokens(
    tokens_or_text: str | list[str],
    *,
    allow_tokens: set[str] | None = None,
) -> tuple[list[str], list[dict[str, str]]]:
    """Separate pure style/quality tokens from any scene/prop/expression leakage."""
    allowed = {t.strip().lower() for t in (allow_tokens or set()) if t.strip()}
    tokens = split_prompt_tokens(tokens_or_text) if isinstance(tokens_or_text, str) else list(tokens_or_text)
    clean: list[str] = []
    stripped: list[dict[str, str]] = []
    for tok in tokens:
        if tok.lower() in allowed:
            clean.append(tok)
            continue
        cat = classify_prompt_token(tok)
        if cat is not None:
            stripped.append({"token": tok, "category": cat})
        else:
            clean.append(tok)
    return clean, stripped


def validate_clean_preset(
    preset: dict[str, Any],
    *,
    allow_tokens: set[str] | None = None,
) -> None:
    """Validate that a StylePreset contains zero leaked prop/scene/beverage/subject tokens."""
    tmpl = preset.get("prompt_template") or {}
    leaks: list[dict[str, str]] = []
    for field in ("style_prefix", "style_suffix"):
        vals = tmpl.get(field) or []
        for item in find_leaked_tokens(vals, allow_tokens=allow_tokens):
            leaks.append({"field": field, **item})
    detailer_prompt = str(tmpl.get("detailer_positive_template") or "")
    if detailer_prompt:
        for item in find_leaked_tokens(detailer_prompt, allow_tokens=allow_tokens):
            leaks.append({"field": "detailer_positive_template", **item})
    if leaks:
        summary = ", ".join(f"{l['field']}:{l['token']}({l['category']})" for l in leaks)
        raise PresetContaminationError(
            f"StylePreset '{preset.get('preset_id')}' contains non-style prompt leakage: {summary}"
        )


def _scalar_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Extract non-link scalar inputs from a ComfyUI node inputs dictionary."""
    return {
        k: v
        for k, v in (inputs or {}).items()
        if not (isinstance(v, list) and len(v) == 2 and isinstance(v[0], (str, int)))
    }


def _follow_text_origin(graph: dict[str, Any], link_val: Any) -> str | None:
    """Resolve text prompt string connected to `positive`/`negative` inputs of a sampler or detailer."""
    if not (isinstance(link_val, list) and len(link_val) >= 1):
        return None
    nid = str(link_val[0])
    node = graph.get(nid) or {}
    ctype = str(node.get("class_type") or "")
    inputs = node.get("inputs") or {}
    if ctype == "CLIPTextEncode":
        txt = inputs.get("text")
        return str(txt) if isinstance(txt, str) else None
    for upstream_key in ("conditioning", "conditioning_1", "conditioning_to", "positive"):
        if upstream_key in inputs:
            found = _follow_text_origin(graph, inputs.get(upstream_key))
            if found is not None:
                return found
    return None


def extract_style_config_from_workflow(raw_workflow: dict[str, Any]) -> dict[str, Any]:
    """Parse an API ComfyUI workflow JSON into a normalized style-only technical config."""
    graph = _unwrap_prompt_graph(raw_workflow or {})
    checkpoint: str | None = None
    loras: list[dict[str, Any]] = []
    clip_stop_layer: int | None = None
    base_res: list[int] = [832, 1216]
    samplers: list[tuple[str, dict[str, Any]]] = []
    upscale_model: str | None = None
    scale_by: float | None = None
    scale_method: str = "lanczos"
    detailers: list[tuple[str, dict[str, Any]]] = []
    detectors: list[str] = []

    for nid in sorted(graph.keys(), key=lambda x: (len(x), x)):
        node = graph[nid]
        if not isinstance(node, dict):
            continue
        ctype = str(node.get("class_type") or "")
        inputs = node.get("inputs") or {}
        if ctype in {"CheckpointLoaderSimple", "CheckpointLoader"} and not checkpoint:
            checkpoint = str(inputs.get("ckpt_name") or "") or None
        elif ctype in {"LoraLoader", "LoraLoaderModelOnly"}:
            name = inputs.get("lora_name")
            if name:
                loras.append(
                    {
                        "name": str(name),
                        "strength_model": float(inputs.get("strength_model", 1.0)),
                        "strength_clip": float(inputs.get("strength_clip", inputs.get("strength_model", 1.0))),
                    }
                )
        elif ctype == "CLIPSetLastLayer":
            val = inputs.get("stop_at_clip_layer")
            if val is not None:
                clip_stop_layer = int(val)
        elif ctype == "EmptyLatentImage":
            w = int(inputs.get("width", 832))
            h = int(inputs.get("height", 1216))
            base_res = [w, h]
        elif ctype in {"KSampler", "KSamplerAdvanced"}:
            samplers.append((nid, node))
        elif ctype == "UpscaleModelLoader":
            upscale_model = str(inputs.get("model_name") or "") or None
        elif ctype == "ImageScaleBy":
            scale_by = float(inputs.get("scale_by", 0.5))
            scale_method = str(inputs.get("upscale_method", "lanczos"))
        elif ctype == "UltralyticsDetectorProvider":
            m = inputs.get("model_name")
            if m:
                detectors.append(str(m))
        elif "Detailer" in ctype:
            detailers.append((nid, node))

    # Identify base sampler vs hires sampler cleanly via denoise or node id order
    base_sampler_node: tuple[str, dict[str, Any]] | None = None
    hires_sampler_node: tuple[str, dict[str, Any]] | None = None
    if samplers:
        full_samplers = [s for s in samplers if float((s[1].get("inputs") or {}).get("denoise", 1.0)) >= 0.99]
        partial_samplers = [s for s in samplers if float((s[1].get("inputs") or {}).get("denoise", 1.0)) < 0.99]
        base_sampler_node = full_samplers[0] if full_samplers else samplers[0]
        if partial_samplers:
            hires_sampler_node = partial_samplers[-1]

    sampler_cfg: dict[str, Any] = {
        "steps": 28,
        "cfg": 4.5,
        "sampler_name": "euler_ancestral",
        "scheduler": "karras",
        "denoise": 1.0,
    }
    raw_pos = ""
    raw_neg = ""
    if base_sampler_node:
        bs_in = base_sampler_node[1].get("inputs") or {}
        sampler_cfg = {
            "steps": int(bs_in.get("steps", 28)),
            "cfg": float(bs_in.get("cfg", 4.5)),
            "sampler_name": str(bs_in.get("sampler_name", "euler_ancestral")),
            "scheduler": str(bs_in.get("scheduler", "karras")),
            "denoise": float(bs_in.get("denoise", 1.0)),
        }
        raw_pos = _follow_text_origin(graph, bs_in.get("positive")) or ""
        raw_neg = _follow_text_origin(graph, bs_in.get("negative")) or ""

    hires_cfg: dict[str, Any] = {"enabled": False}
    if hires_sampler_node and upscale_model:
        hs_in = hires_sampler_node[1].get("inputs") or {}
        hires_cfg = {
            "enabled": True,
            "upscale_model": upscale_model,
            "scale_by": float(scale_by if scale_by is not None else 0.5),
            "upscale_method": scale_method,
            "steps": int(hs_in.get("steps", 16)),
            "cfg": float(hs_in.get("cfg", sampler_cfg["cfg"])),
            "sampler_name": str(hs_in.get("sampler_name", sampler_cfg["sampler_name"])),
            "scheduler": str(hs_in.get("scheduler", sampler_cfg["scheduler"])),
            "denoise": float(hs_in.get("denoise", 0.3)),
            "seed_offset": 1,
        }

    detailer_cfg: dict[str, Any] = {"enabled": False}
    if detailers and detectors:
        d_node = detailers[-1][1]
        d_in = _scalar_inputs(d_node.get("inputs") or {})
        d_in.pop("seed", None)
        d_in.pop("noise_seed", None)
        d_in["wildcard"] = ""
        detailer_cfg = {
            "enabled": True,
            "class_type": str(d_node.get("class_type") or "FaceDetailer"),
            "detector_model": detectors[-1],
            "seed_offset": 2,
            "params": d_in,
        }

    return {
        "checkpoint": checkpoint,
        "loras": loras,
        "clip_stop_at_clip_layer": clip_stop_layer,
        "base_resolution": base_res,
        "sampler": sampler_cfg,
        "hires": hires_cfg,
        "detailer": detailer_cfg,
        "_source_raw_positive": raw_pos,
        "_source_raw_negative": raw_neg,
    }


def assemble_workflow(
    preset: dict[str, Any],
    *,
    subject_prompt: str,
    negative_extra: str = "",
    seed: int = 123456,
    width: int | None = None,
    height: int | None = None,
    filename_prefix: str = "production/PROD",
    enable_hires: bool | None = None,
    enable_detailer: bool | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build an executable ComfyUI API workflow dict from a pure StylePreset + subject_prompt."""
    cfg = preset.get("style_config") or {}
    tmpl = preset.get("prompt_template") or {}

    ckpt = cfg.get("checkpoint")
    if not ckpt:
        raise ValueError(f"StylePreset '{preset.get('preset_id')}' has no checkpoint.")

    prefix_tokens = [t for t in (tmpl.get("style_prefix") or []) if str(t).strip()]
    suffix_tokens = [t for t in (tmpl.get("style_suffix") or []) if str(t).strip()]
    parts: list[str] = []
    if prefix_tokens:
        parts.append(", ".join(prefix_tokens))
    if subject_prompt.strip():
        parts.append(subject_prompt.strip().strip(","))
    if suffix_tokens:
        parts.append(", ".join(suffix_tokens))
    positive_prompt = ", ".join(p for p in parts if p)

    base_neg = str(tmpl.get("default_negative") or "").strip().strip(",")
    extra_neg = negative_extra.strip().strip(",")
    negative_prompt = ", ".join(p for p in (base_neg, extra_neg) if p)

    base_res = cfg.get("base_resolution") or [832, 1216]
    w = int(width or base_res[0])
    h = int(height or base_res[1])
    samp = cfg.get("sampler") or {}

    graph: dict[str, Any] = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": ckpt},
        }
    }
    model_ref: list[Any] = ["1", 0]
    clip_ref: list[Any] = ["1", 1]
    vae_ref: list[Any] = ["1", 2]

    for idx, lora in enumerate(cfg.get("loras") or [], start=10):
        nid = str(idx)
        graph[nid] = {
            "class_type": "LoraLoader",
            "inputs": {
                "model": model_ref,
                "clip": clip_ref,
                "lora_name": lora["name"],
                "strength_model": float(lora.get("strength_model", 1.0)),
                "strength_clip": float(lora.get("strength_clip", lora.get("strength_model", 1.0))),
            },
        }
        model_ref = [nid, 0]
        clip_ref = [nid, 1]

    clip_stop = cfg.get("clip_stop_at_clip_layer")
    if clip_stop is not None:
        graph["20"] = {
            "class_type": "CLIPSetLastLayer",
            "inputs": {
                "clip": clip_ref,
                "stop_at_clip_layer": int(clip_stop),
            },
        }
        clip_ref = ["20", 0]

    graph["2"] = {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": w, "height": h, "batch_size": 1},
    }
    graph["3"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": positive_prompt, "clip": clip_ref},
    }
    graph["4"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": negative_prompt, "clip": clip_ref},
    }
    graph["5"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": model_ref,
            "positive": ["3", 0],
            "negative": ["4", 0],
            "latent_image": ["2", 0],
            "seed": int(seed),
            "steps": int(samp.get("steps", 28)),
            "cfg": float(samp.get("cfg", 4.5)),
            "sampler_name": str(samp.get("sampler_name", "euler_ancestral")),
            "scheduler": str(samp.get("scheduler", "karras")),
            "denoise": float(samp.get("denoise", 1.0)),
        },
    }
    graph["6"] = {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["5", 0], "vae": vae_ref},
    }
    image_ref: list[Any] = ["6", 0]

    hires_cfg = cfg.get("hires") or {}
    use_hires = bool(hires_cfg.get("enabled")) if enable_hires is None else bool(enable_hires and hires_cfg.get("upscale_model"))
    if use_hires:
        graph["30"] = {
            "class_type": "UpscaleModelLoader",
            "inputs": {"model_name": hires_cfg["upscale_model"]},
        }
        graph["31"] = {
            "class_type": "ImageUpscaleWithModel",
            "inputs": {"upscale_model": ["30", 0], "image": image_ref},
        }
        graph["32"] = {
            "class_type": "ImageScaleBy",
            "inputs": {
                "image": ["31", 0],
                "upscale_method": str(hires_cfg.get("upscale_method", "lanczos")),
                "scale_by": float(hires_cfg.get("scale_by", 0.5)),
            },
        }
        graph["33"] = {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["32", 0], "vae": vae_ref},
        }
        graph["34"] = {
            "class_type": "KSampler",
            "inputs": {
                "model": model_ref,
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["33", 0],
                "seed": int(seed) + int(hires_cfg.get("seed_offset", 1)),
                "steps": int(hires_cfg.get("steps", 16)),
                "cfg": float(hires_cfg.get("cfg", samp.get("cfg", 4.5))),
                "sampler_name": str(hires_cfg.get("sampler_name", samp.get("sampler_name", "euler_ancestral"))),
                "scheduler": str(hires_cfg.get("scheduler", samp.get("scheduler", "karras"))),
                "denoise": float(hires_cfg.get("denoise", 0.3)),
            },
        }
        graph["35"] = {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["34", 0], "vae": vae_ref},
        }
        image_ref = ["35", 0]

    detailer_cfg = cfg.get("detailer") or {}
    use_detailer = (
        bool(detailer_cfg.get("enabled"))
        if enable_detailer is None
        else bool(enable_detailer and detailer_cfg.get("detector_model"))
    )
    if use_detailer:
        d_tmpl = str(tmpl.get("detailer_positive_template") or "").strip()
        d_prompt = d_tmpl or ", ".join(prefix_tokens + ["detailed hands, clean anatomy"])
        graph["40"] = {
            "class_type": "UltralyticsDetectorProvider",
            "inputs": {"model_name": detailer_cfg["detector_model"]},
        }
        graph["41"] = {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": d_prompt, "clip": clip_ref},
        }
        d_params = dict(detailer_cfg.get("params") or {})
        d_params.setdefault("guide_size", 512)
        d_params.setdefault("guide_size_for", True)
        d_params.setdefault("max_size", 768)
        d_params.setdefault("steps", 20)
        d_params.setdefault("cfg", float(samp.get("cfg", 4.5)))
        d_params.setdefault("sampler_name", str(samp.get("sampler_name", "euler_ancestral")))
        d_params.setdefault("scheduler", str(samp.get("scheduler", "karras")))
        d_params.setdefault("denoise", 0.35)
        d_params.setdefault("feather", 5)
        d_params.setdefault("noise_mask", True)
        d_params.setdefault("force_inpaint", True)
        d_params.setdefault("bbox_threshold", 0.4)
        d_params.setdefault("bbox_dilation", 15)
        d_params.setdefault("bbox_crop_factor", 2.5)
        d_params.setdefault("sam_detection_hint", "center-1")
        d_params.setdefault("sam_dilation", 0)
        d_params.setdefault("sam_threshold", 0.93)
        d_params.setdefault("sam_bbox_expansion", 0)
        d_params.setdefault("sam_mask_hint_threshold", 0.7)
        d_params.setdefault("sam_mask_hint_use_negative", "False")
        d_params.setdefault("drop_size", 10)
        d_params.setdefault("wildcard", "")
        d_params.setdefault("cycle", 1)
        d_params["seed"] = int(seed) + int(detailer_cfg.get("seed_offset", 2))
        d_params["image"] = image_ref
        d_params["model"] = model_ref
        d_params["clip"] = clip_ref
        d_params["vae"] = vae_ref
        d_params["positive"] = ["41", 0]
        d_params["negative"] = ["4", 0]
        d_params["bbox_detector"] = ["40", 0]

        graph["42"] = {
            "class_type": str(detailer_cfg.get("class_type") or "FaceDetailer"),
            "inputs": d_params,
        }
        image_ref = ["42", 0]

    graph["99"] = {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": filename_prefix, "images": image_ref},
    }

    meta = {
        "preset_id": preset["preset_id"],
        "seed": int(seed),
        "positive_prompt": positive_prompt,
        "negative_prompt": negative_prompt,
        "resolution": [w, h],
        "hires_enabled": use_hires,
        "detailer_enabled": use_detailer,
    }
    return graph, meta
