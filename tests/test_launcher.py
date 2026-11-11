from pathlib import Path


def test_hidden_launcher_captures_startup_output_before_loading_app():
    launcher = Path(__file__).resolve().parents[1] / "server" / "launcher.pyw"
    source = launcher.read_text(encoding="utf-8")
    compile(source, str(launcher), "exec")
    assert "sys.stdout = log_stream" in source
    assert "sys.stderr = log_stream" in source
    assert source.index("sys.stderr = log_stream") < source.index("runpy.run_path(APP_FILE")
    assert "TTS Studio — ошибка запуска" in source
