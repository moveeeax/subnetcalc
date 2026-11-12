import ipaddress
import json
import random

import pytest

from subnetcalc import cli, core


def strs(nets):
    return [str(n) for n in nets]


def test_free_issue_example():
    free = core.free_space("10.0.0.0/16", ["10.0.1.0/24", "10.0.4.0/22"])
    assert strs(free) == [
        "10.0.0.0/24",
        "10.0.2.0/23",
        "10.0.8.0/21",
        "10.0.16.0/20",
        "10.0.32.0/19",
        "10.0.64.0/18",
        "10.0.128.0/17",
    ]


def test_free_nothing_used_is_whole_block():
    assert strs(core.free_space("10.0.0.0/24", [])) == ["10.0.0.0/24"]


def test_free_fully_used():
    assert core.free_space("10.0.0.0/24", ["10.0.0.0/25", "10.0.0.128/25"]) == []


def test_free_used_block_larger_than_cidr():
    assert core.free_space("10.0.0.0/24", ["10.0.0.0/8"]) == []


def test_free_ignores_unrelated_and_other_version():
    free = core.free_space("10.0.0.0/24", ["192.168.0.0/16", "2001:db8::/32"])
    assert strs(free) == ["10.0.0.0/24"]


def test_free_overlapping_used_entries_and_addresses():
    free = core.free_space(
        "10.0.0.0/29", ["10.0.0.0/30", "10.0.0.2/31", "10.0.0.5"]
    )
    assert strs(free) == ["10.0.0.4/32", "10.0.0.6/31"]


def test_free_min_prefix_hides_small_blocks():
    free = core.free_space(
        "10.0.0.0/16", ["10.0.1.0/24", "10.0.4.0/22"], min_prefix=20
    )
    assert strs(free) == ["10.0.16.0/20", "10.0.32.0/19", "10.0.64.0/18", "10.0.128.0/17"]


def test_free_min_prefix_out_of_range():
    with pytest.raises(ValueError):
        core.free_space("10.0.0.0/16", [], min_prefix=33)


def test_free_ipv6():
    free = core.free_space("2001:db8::/62", ["2001:db8:0:1::/64"])
    assert strs(free) == ["2001:db8::/64", "2001:db8:0:2::/63"]


def test_free_strict_rejects_host_bits_in_used():
    with pytest.raises(ValueError):
        core.free_space("10.0.0.0/16", ["10.0.1.5/24"], strict=True)


def test_next_free_lowest_fit():
    block = core.next_free("10.0.0.0/16", ["10.0.0.0/24", "10.0.2.0/24"], 23)
    assert str(block) == "10.0.4.0/23"
    block = core.next_free("10.0.0.0/16", ["10.0.0.0/24", "10.0.2.0/24"], 24)
    assert str(block) == "10.0.1.0/24"


def test_next_free_none_left():
    assert core.next_free("10.0.0.0/24", ["10.0.0.0/25"], 24) is None


def test_next_free_prefix_bounds():
    with pytest.raises(ValueError):
        core.next_free("10.0.0.0/16", [], 8)
    with pytest.raises(ValueError):
        core.next_free("10.0.0.0/16", [], 33)


@pytest.mark.parametrize("seed", range(20))
def test_free_plus_used_tiles_block(seed):
    rng = random.Random(seed)
    net = ipaddress.ip_network("10.0.0.0/20")
    used = []
    for _ in range(rng.randint(0, 12)):
        prefix = rng.randint(20, 30)
        used.append(rng.choice(list(net.subnets(new_prefix=prefix))))
    free = core.free_space(net, used)
    used_set = set()
    for u in used:
        used_set.update(range(int(u.network_address), int(u.broadcast_address) + 1))
    free_set = set()
    for f in free:
        span = set(range(int(f.network_address), int(f.broadcast_address) + 1))
        assert not span & free_set
        free_set |= span
    assert not free_set & used_set
    assert free_set | used_set == set(
        range(int(net.network_address), int(net.broadcast_address) + 1)
    )
    # Minimal form: collapsing does not merge anything further.
    assert list(ipaddress.collapse_addresses(free)) == free


def run(capsys, argv):
    code = cli.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_cli_free_text_with_total(capsys):
    code, out, _ = run(
        capsys, ["free", "10.0.0.0/22", "--used", "10.0.1.0/24"]
    )
    assert code == 0
    assert out.splitlines() == [
        "10.0.0.0/24",
        "10.0.2.0/23",
        "Total: 768 addresses in 2 blocks",
    ]


def test_cli_free_min_prefix_reports_hidden(capsys):
    code, out, _ = run(
        capsys, ["free", "10.0.0.0/22", "--used", "10.0.1.0/24", "--min-prefix", "/23"]
    )
    assert code == 0
    assert out.splitlines() == [
        "10.0.2.0/23",
        "Total: 512 addresses in 1 block (256 more in blocks smaller than /23)",
    ]


def test_cli_free_used_file_and_json(capsys, tmp_path):
    path = tmp_path / "cidrs.txt"
    path.write_text("# in use\n10.0.1.0/24  # vpc a\n\n10.0.2.0/24, 2001:db8::/32\n")
    code, out, _ = run(
        capsys, ["--json", "free", "10.0.0.0/22", "--used-file", str(path)]
    )
    assert code == 0
    data = json.loads(out)
    assert data["free"] == ["10.0.0.0/24", "10.0.3.0/24"]
    assert data["used"] == ["10.0.1.0/24", "10.0.2.0/24"]
    assert data["ignored"] == ["2001:db8::/32"]
    assert data["free_addresses"] == 512
    assert data["count"] == 2


def test_cli_free_next(capsys):
    code, out, _ = run(
        capsys, ["free", "10.0.0.0/16", "--used", "10.0.0.0/24", "--next", "/24"]
    )
    assert code == 0
    assert out.strip() == "10.0.1.0/24"


def test_cli_free_next_none_exit_1(capsys):
    code, out, err = run(
        capsys, ["free", "10.0.0.0/24", "--used", "10.0.0.0/25", "--next", "24"]
    )
    assert code == 1
    assert out == ""
    assert "no free /24" in err


def test_cli_free_next_json_null(capsys):
    code, out, _ = run(
        capsys, ["free", "10.0.0.0/24", "--used", "10.0.0.0/24", "--next", "26", "--json"]
    )
    assert code == 1
    assert json.loads(out)["next"] is None


def test_cli_free_missing_used_file(capsys, tmp_path):
    code, _, err = run(
        capsys, ["free", "10.0.0.0/24", "--used-file", str(tmp_path / "nope")]
    )
    assert code == 2
    assert "cannot read" in err


def test_cli_free_bad_used_entry(capsys):
    code, _, err = run(capsys, ["free", "10.0.0.0/24", "--used", "bogus"])
    assert code == 2
    assert "error:" in err
