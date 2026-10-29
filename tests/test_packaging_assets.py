from pathlib import Path

from app import __file__ as app_init
from app.config import Settings


def test_web_assets_live_inside_the_package() -> None:
    settings = Settings(_env_file=None)
    assert (settings.web_dir / "index.html").is_file()
    assert (settings.web_dir / "app.js").is_file()


def test_seed_problems_live_inside_the_package() -> None:
    seed = Path(app_init).resolve().parent / "seed_problems"
    assert (seed / "c-sum-two-integers" / "problem.json").is_file()
    assert (seed / "pset-vote-tally" / "problem.json").is_file()
