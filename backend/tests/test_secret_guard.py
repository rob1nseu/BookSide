import subprocess
from pathlib import Path

from scripts import check_secrets


def test_guard_reads_staged_blob_not_clean_worktree(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)
    secret = "sk-" + "a" * 32
    Path("config.py").write_text(secret)
    subprocess.run(["git", "add", "config.py"], check=True)
    Path("config.py").write_text("clean working copy")
    assert check_secrets.check(staged=True) == 1
    output = capsys.readouterr().out
    assert "config.py" in output and secret not in output


def test_guard_blocks_local_config_and_allows_empty_example(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)
    Path(".env.example").write_text("DEEPSEEK_API_KEY=\n")
    subprocess.run(["git", "add", ".env.example"], check=True)
    assert check_secrets.check(staged=True) == 0
    Path("model.local.json").write_text("{}")
    subprocess.run(["git", "add", "model.local.json"], check=True)
    assert check_secrets.check(staged=True) == 1
