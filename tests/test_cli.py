from __future__ import annotations

import struct

import pytest

from git_radial_history.cli import main
from git_radial_history.config import load_config
from git_radial_history.model import RadialHistoryError


def test_svg_output(sample_repo, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code = main([str(sample_repo), "--format", "svg", "--output", "poster"])
    assert code == 0
    assert (tmp_path / "output" / "poster.svg").exists()


def test_png_signature_and_size(sample_repo, tmp_path, monkeypatch):
    from git_radial_history.config import PosterConfig

    monkeypatch.chdir(tmp_path)
    code = main([str(sample_repo), "--format", "png", "--output", "p"])
    assert code == 0
    data = (tmp_path / "output" / "p.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    defaults = PosterConfig()
    assert (width, height) == (defaults.width, defaults.height)


def test_invalid_date_range(sample_repo, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code = main([str(sample_repo), "--from", "2023-01-01", "--until", "2020-01-01"])
    assert code == 1


def test_bad_source_returns_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["/no/such/repo"]) == 1


def test_title_override(sample_repo, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main([str(sample_repo), "--format", "svg", "--output", "t", "--title", "Custom"])
    assert "Custom" in (tmp_path / "output" / "t.svg").read_text()


def test_config_unknown_key_rejected(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text("[poster]\nwidth = 100\nbogus = 5\n")
    with pytest.raises(RadialHistoryError):
        load_config(cfg)


def test_config_unknown_section_rejected(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text("[nonsense]\nx = 1\n")
    with pytest.raises(RadialHistoryError):
        load_config(cfg)


def test_config_invalid_tag_levels_rejected(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('[tags]\nlevels = ["major", "bogus"]\n')
    with pytest.raises(RadialHistoryError):
        load_config(cfg)


def test_config_valid_tag_levels(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('[tags]\nlevels = ["major", "minor"]\n')
    config = load_config(cfg)
    assert config.tags.levels == ("major", "minor")


def test_tags_threshold_default_minor():
    from git_radial_history.cli import _apply_tag_threshold
    from git_radial_history.config import Config

    config = _apply_tag_threshold(Config(), None, from_config=False)
    assert config.tags.levels == ("major", "minor")


def test_tags_threshold_major_only():
    from git_radial_history.cli import _apply_tag_threshold
    from git_radial_history.config import Config

    config = _apply_tag_threshold(Config(), "major", from_config=False)
    assert config.tags.levels == ("major",)


def test_tags_threshold_patch_shows_all():
    from git_radial_history.cli import _apply_tag_threshold
    from git_radial_history.config import Config

    config = _apply_tag_threshold(Config(), "patch", from_config=False)
    assert config.tags.levels == ("major", "minor", "patch")


def test_tags_flag_overrides_config():
    from git_radial_history.cli import _apply_tag_threshold
    from git_radial_history.config import Config, TagsConfig

    base = Config(tags=TagsConfig(levels=("patch",)))
    result = _apply_tag_threshold(base, "major", from_config=True)
    assert result.tags.levels == ("major",)


def test_config_levels_kept_without_flag():
    from git_radial_history.cli import _apply_tag_threshold
    from git_radial_history.config import Config, TagsConfig

    base = Config(tags=TagsConfig(levels=("major",)))
    result = _apply_tag_threshold(base, None, from_config=True)
    assert result.tags.levels == ("major",)


def test_config_applies(sample_repo, tmp_path, monkeypatch):
    cfg = tmp_path / "c.toml"
    cfg.write_text("[poster]\nwidth = 1000\nheight = 1200\n")
    monkeypatch.chdir(tmp_path)
    main([str(sample_repo), "--format", "svg", "--output", "s", "--config", str(cfg)])
    content = (tmp_path / "output" / "s.svg").read_text()
    assert 'width="1000"' in content
