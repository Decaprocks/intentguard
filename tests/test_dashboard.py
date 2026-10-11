"""Real Streamlit application run without starting a cloud session."""

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_demo_dashboard_and_stop_request(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(app), default_timeout=60).run()
    assert not at.exception
    assert at.title[0].value == "🛡️ IntentGuard"
    # Resource picker under Optimization: choose the disposable server.
    at.selectbox[2].select("i-00000000000000002").run()
    next(b for b in at.button if b.label == "Evaluate stop request").click().run()
    assert not at.exception
    assert any("ALLOW" in message.value for message in at.success)
    assert at.session_state["last_decision"]["executed"] is False
