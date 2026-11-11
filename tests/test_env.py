import logging
import os
import sys

from studio.core.env import configure_environment


def test_environment_bootstrap_sets_paths_and_offline_mode(tmp_path, monkeypatch):
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    for key in ("TEMP", "TMP", "TORCH_HOME", "MODELSCOPE_CACHE", "HF_HOME", "MODELSCOPE_OFFLINE", "MODELSCOPE_ENVIRONMENT", "HF_HUB_OFFLINE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(sys, "path", list(sys.path))
    logger = logging.getLogger("studio")
    original_handlers = list(logger.handlers)
    original_propagate = logger.propagate
    paths = configure_environment(str(server_dir))
    try:
        assert paths["SERVER_DIR"] == str(server_dir)
        assert paths["COSY_DIR"] == str(tmp_path / "cosyvoice3")
        assert paths["COSY_DIR"] in sys.path
        assert os.environ["TEMP"] == paths["TEMP_DIR"]
        assert os.environ["MODELSCOPE_OFFLINE"] == "1"
        assert os.environ["HF_HUB_OFFLINE"] == "1"
        assert os.path.isdir(paths["CHARACTERS_DIR"])
        assert os.path.isdir(paths["CUSTOM_FONTS_DIR"])
        assert logger.propagate is False
    finally:
        logger.propagate = original_propagate
        for handler in list(logger.handlers):
            if handler not in original_handlers:
                logger.removeHandler(handler)
                handler.close()
