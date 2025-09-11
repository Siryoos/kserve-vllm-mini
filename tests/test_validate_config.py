def import_validator():
    import importlib.util
    import pathlib

    path = pathlib.Path("scripts/validate_config.py")
    spec = importlib.util.spec_from_file_location("validate_config", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def test_quantization_compatibility_error():
    validate_mod = import_validator()
    v = validate_mod.ConfigValidator()
    cfg = {
        "vllm_features": {"quantization": "awq"},
        "model_requirements": {"compatible_formats": ["gptq"]},
    }
    ok = v.validate_profile(cfg)
    assert not ok
    assert any("not compatible" in e for e in v.errors)


def test_gpu_memory_heuristic_insufficient():
    validate_mod = import_validator()
    v = validate_mod.ConfigValidator()
    cfg = {
        "validation_hints": {"model_size_hint": "70b"},
        "_gpu_memory_gb": 24,
        "vllm_features": {"quantization": None},
    }
    ok = v.validate_profile(cfg)
    assert not ok
    assert any("insufficient" in e.lower() for e in v.errors)


def test_warnings_contain_suggestions():
    validate_mod = import_validator()
    v = validate_mod.ConfigValidator()
    cfg = {
        "requests": 10,
        "concurrency": 1,
        "max_tokens": 4096,
        "vllm_features": {"quantization": "gptq"},
    }
    ok = v.validate_profile(cfg)
    assert ok  # only warnings
    text = "\n".join(v.warnings)
    assert "Suggestion" in text or "Docs" in text
