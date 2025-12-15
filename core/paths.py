from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def macros_saved_dir() -> Path:
    return project_root() / "macros" / "saved"


def macros_examples_dir() -> Path:
    return project_root() / "macros" / "examples"
