"""Pytest configuration.

© Reuben Thomas <rrt@sc3d.org> 2024.

Released under the GPL version 3, or (at your option) any later version.
"""

from pytest import FixtureRequest, Parser, fixture


def pytest_addoption(parser: Parser) -> None:
    parser.addoption(
        "--regenerate-expected",
        action="store_true",
        help="regenerate the expected outputs",
    )


@fixture
def regenerate_expected(request: FixtureRequest) -> bool:  # pragma: no cover
    opt = request.config.getoption("--regenerate-expected")
    assert isinstance(opt, bool)
    return opt
