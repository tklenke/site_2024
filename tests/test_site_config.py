# ABOUTME: Tests reading the site settings from site.ini and site_local.ini.
# ABOUTME: Uses settings files in a temporary directory, never the real ones.

import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.site_config import read_config

FWWW = Path(__file__).resolve().parent.parent / "fwww"
SETTINGS = "[RAG]\nMAX_DOCUMENTS = 60\n[MODELS]\nLLM_DRAFT = model-a\n"
KEYS = "[KEYS]\nSESSION = session-key\nOPENAI = openai-key\n"


def write_settings(pathDir, strSite, strLocal=None):
    if strSite is not None:
        (pathDir / "site.ini").write_text(strSite)
    if strLocal is not None:
        (pathDir / "site_local.ini").write_text(strLocal)


def test_reads_settings_and_keys(tmp_path):
    write_settings(tmp_path, SETTINGS, KEYS)
    cfg = read_config(tmp_path)
    assert cfg.getint("RAG", "MAX_DOCUMENTS") == 60
    assert cfg.get("KEYS", "SESSION") == "session-key"
    assert cfg.get("KEYS", "OPENAI") == "openai-key"


def test_value_in_site_local_wins(tmp_path):
    write_settings(tmp_path, SETTINGS, KEYS + "[RAG]\nMAX_DOCUMENTS = 10\n")
    cfg = read_config(tmp_path)
    assert cfg.getint("RAG", "MAX_DOCUMENTS") == 10
    assert cfg.get("MODELS", "LLM_DRAFT") == "model-a"


@pytest.mark.parametrize("strLocal, strMissing", [
    (None, "SESSION"),
    ("[RAG]\nMAX_DOCUMENTS = 10\n", "SESSION"),
    ("[KEYS]\nOPENAI = openai-key\n", "SESSION"),
    ("[KEYS]\nSESSION =\nOPENAI = openai-key\n", "SESSION"),
    ("[KEYS]\nSESSION = session-key\n", "OPENAI"),
])
def test_missing_key_stops_startup(tmp_path, strLocal, strMissing):
    write_settings(tmp_path, SETTINGS, strLocal)
    with pytest.raises(RuntimeError, match=f"{strMissing}.*site_local.ini"):
        read_config(tmp_path)


def test_missing_site_ini_stops_startup(tmp_path):
    write_settings(tmp_path, None, KEYS)
    with pytest.raises(RuntimeError, match="site.ini"):
        read_config(tmp_path)


def test_message_holds_no_key(tmp_path):
    write_settings(tmp_path, SETTINGS, "[KEYS]\nOPENAI = openai-key\n")
    with pytest.raises(RuntimeError) as excinfo:
        read_config(tmp_path)
    assert "openai-key" not in str(excinfo.value)


def test_app_does_not_start_without_keys(tmp_path):
    write_settings(tmp_path, SETTINGS)
    result = subprocess.run([sys.executable, "-c", "import site_app"], cwd=tmp_path,
                            env=dict(os.environ, PYTHONPATH=str(FWWW)),
                            capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert "No SESSION in the [KEYS] section of site_local.ini" in result.stderr
