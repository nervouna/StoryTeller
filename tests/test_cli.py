"""Tests for CLI --until flag and auto-extend loop."""
from click.testing import CliRunner


class TestRunUntilFlag:
    def test_run_help_shows_until_flag(self):
        from storyteller.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "--until" in result.output

    def test_run_help_mentions_chapter_limit(self):
        from storyteller.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])
        assert "chapter" in result.output.lower() or "章" in result.output
