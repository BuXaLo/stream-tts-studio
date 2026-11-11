import importlib

import pytest


STUDIO_MODULES = [
    "studio.core.env",
    "studio.core.config",
    "studio.core.storage",
    "studio.core.validation",
    "studio.core.ws",
    "studio.services.text",
    "studio.services.donations",
    "studio.services.streamerbot",
    "studio.services.da_worker",
    "studio.services.audio_tools",
    "studio.services.tts_engine",
    "studio.routes.pages",
    "studio.routes.system",
    "studio.routes.donations",
    "studio.routes.characters",
    "studio.routes.fonts",
    "studio.routes.tools",
    "studio.routes.speak",
]


@pytest.mark.parametrize("module_name", STUDIO_MODULES)
def test_studio_package_modules_import_without_loading_ml_runtime(module_name):
    assert importlib.import_module(module_name) is not None
