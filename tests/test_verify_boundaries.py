import pytest

from scenelang.verify import VerifySyntaxError, parse


@pytest.mark.parametrize("raw", [
    "max_colors(0)", "max_colors(1.5)", "grid_aligned(32, 1.1)",
    "symmetric(vertical, 1.01)", "palette_match(10, 1.1)",
    "fit_guides(0.6)", "margin(1.5)", "walkable_connected(a, b, 0)",
    "grid_aligned(9000)", "margin(9000)", "walkable_connected(a, b, 101)",
    "palette_match(101)", "max_colors(20000000)",
])
def test_verify_rejects_out_of_domain_arguments(raw):
    with pytest.raises(VerifySyntaxError):
        parse(raw)


@pytest.mark.parametrize("raw", [
    "max_colors(16)", "grid_aligned(32, 0.9)", "symmetric(vertical, 0.8, legs)",
    "fit_guides(0.04)", "palette_match(10, 0.9, pirate)",
    "walkable_connected(start, exit, 18)", "fit_guides(0)", "grid_aligned(32, 0)",
    "symmetric(vertical, 0)", "zone_quiet(title, 0)",
])
def test_verify_accepts_documented_argument_contracts(raw):
    assert parse(raw).name
