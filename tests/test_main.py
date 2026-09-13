"""
Unit tests for main pipeline execution.
"""
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from scheme_intel.main import load_config, run
from scheme_intel.exceptions import ConfigurationError, SourceAccessError
from scheme_intel.models import Article, Catalyst, SwingSetup


class TestMainPipeline:
    """Tests for main workflow module."""

    def test_load_config_success(self):
        """Test loading valid configuration."""
        config = load_config()
        assert "scheme" in config
        assert "stocks" in config
        assert len(config["stocks"]) > 0

    def test_load_config_missing_file(self, tmp_path):
        """Test load_config raises ConfigurationError on missing file."""
        with pytest.raises(ConfigurationError):
            load_config(tmp_path / "nonexistent.yaml")

    def test_load_config_invalid_yaml(self, tmp_path):
        """Test load_config raises ConfigurationError on invalid YAML."""
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text(":::invalid:yaml:{{", encoding="utf-8")
        with pytest.raises(ConfigurationError):
            load_config(bad_file)

    @patch('scheme_intel.pipeline.scan_page')
    @patch('scheme_intel.pipeline.classify')
    @patch('scheme_intel.pipeline.make_setup')
    def test_run_pipeline_success(self, mock_setup, mock_classify, mock_scan):
        """Test successful pipeline execution."""
        sample_art = Article("Praj CBG contract awarded", "https://example.com/art1", "PIB", None)
        mock_scan.return_value = [sample_art]
        mock_classify.return_value = Catalyst(sample_art, 90, "contract award", "rationale", ("Praj Industries",))
        mock_setup.return_value = SwingSetup("Praj Industries", "PRAJIND.NS", 450.0, 460.0, 420.0, 500.0, 60.0, 90, "QUALIFIED", "2026-09-08T00:00:00Z")

        report = run(send=False)
        assert len(report["catalysts"]) > 0
        assert len(report["setups"]) > 0
        assert "source_errors" in report

    @patch('scheme_intel.pipeline.scan_page')
    def test_run_source_error_handling(self, mock_scan):
        """Test that individual source failures do not crash the pipeline."""
        mock_scan.side_effect = SourceAccessError("Connection timeout")
        report = run(send=False)
        assert len(report["source_errors"]) > 0