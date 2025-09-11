import importlib.util
import pathlib
import sys


def import_validator():
    path = pathlib.Path("scripts/validate_config.py")
    spec = importlib.util.spec_from_file_location("validate_config", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def test_autodetect_gpu_memory_triggers_error(tmp_path, monkeypatch):
    validate_mod = import_validator()

    # Stub subprocess.run used by validate_config.main for nvidia-smi call
    class StubProc:
        def __init__(self, stdout: str, returncode: int = 0):
            self.stdout = stdout
            self.stderr = ""
            self.returncode = returncode

    def fake_run(cmd, capture_output=True, text=True, timeout=2):
        # Simulate two GPUs: 40960 MiB and 81920 MiB => min -> 40 GiB
        return StubProc(stdout="40960\n81920\n", returncode=0)

    monkeypatch.setattr(validate_mod.subprocess, "run", fake_run)

    # Create a temporary profile requiring large memory (70B baseline)
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        """
validation_hints:
  model_size_hint: "70b"
vllm_features: {}
"""
    )

    # Run main with the temporary profile; expect non-zero due to insufficient memory
    argv_backup = sys.argv[:]
    try:
        sys.argv = ["validate_config.py", "--profile", str(profile)]
        rc = validate_mod.main()
        assert rc == 1
    finally:
        sys.argv = argv_backup
