import json

import pytest

from subnetcalc import cli


def run(capsys, argv):
    """Invoke the CLI and return (exit_code, stdout, stderr)."""
    code = cli.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_info_text(capsys):
    code, out, _ = run(capsys, ["info", "192.168.1.0/24"])
    assert code == 0
    assert "192.168.1.0" in out
    assert "Usable hosts: 254" in out


def test_info_json(capsys):
    code, out, _ = run(capsys, ["info", "192.168.1.0/24", "--json"])
    assert code == 0
    data = json.loads(out)
    assert data["network_address"] == "192.168.1.0"
    assert data["num_usable"] == 254


def test_info_json_before_subcommand(capsys):
    code, out, _ = run(capsys, ["--json", "info", "10.0.0.0/8"])
    assert code == 0
    data = json.loads(out)
    assert data["prefixlen"] == 8


def test_info_ipv6(capsys):
    code, out, _ = run(capsys, ["info", "2001:db8::/64", "--json"])
    assert code == 0
    data = json.loads(out)
    assert data["version"] == 6


def test_info_invalid_returns_error(capsys):
    code, _, err = run(capsys, ["info", "bogus"])
    assert code == 2
    assert "error:" in err


def test_split_count(capsys):
    code, out, _ = run(capsys, ["split", "10.0.0.0/24", "--count", "4"])
    assert code == 0
    lines = out.strip().splitlines()
    assert lines == [
        "10.0.0.0/26",
        "10.0.0.64/26",
        "10.0.0.128/26",
        "10.0.0.192/26",
    ]


def test_split_prefix_json(capsys):
    code, out, _ = run(capsys, ["split", "10.0.0.0/24", "--prefix", "26", "--json"])
    assert code == 0
    data = json.loads(out)
    assert data["count"] == 4
    assert data["subnets"][0] == "10.0.0.0/26"


def test_split_requires_selector(capsys):
    with pytest.raises(SystemExit):
        cli.main(["split", "10.0.0.0/24"])


def test_split_bad_count_error(capsys):
    code, _, err = run(capsys, ["split", "10.0.0.0/24", "--count", "3"])
    assert code == 2
    assert "power of two" in err


def test_contains_true_exit_zero(capsys):
    code, out, _ = run(capsys, ["contains", "10.0.0.0/24", "10.0.0.9"])
    assert code == 0
    assert out.strip() == "true"


def test_contains_false_exit_one(capsys):
    code, out, _ = run(capsys, ["contains", "10.0.0.0/24", "10.0.1.9"])
    assert code == 1
    assert out.strip() == "false"


def test_contains_json(capsys):
    code, out, _ = run(capsys, ["contains", "10.0.0.0/24", "10.0.0.9", "--json"])
    assert code == 0
    data = json.loads(out)
    assert data["contains"] is True


def test_overlaps_true(capsys):
    code, out, _ = run(capsys, ["overlaps", "10.0.0.0/16", "10.0.1.0/24"])
    assert code == 0
    assert out.strip() == "true"


def test_overlaps_false_exit_one(capsys):
    code, out, _ = run(capsys, ["overlaps", "10.0.0.0/24", "10.0.1.0/24"])
    assert code == 1
    assert out.strip() == "false"


def test_summarize(capsys):
    code, out, _ = run(capsys, ["summarize", "192.168.0.0/25", "192.168.0.128/25"])
    assert code == 0
    assert out.strip() == "192.168.0.0/24"


def test_summarize_json(capsys):
    code, out, _ = run(
        capsys, ["summarize", "10.0.0.0/24", "10.0.1.0/24", "--json"]
    )
    assert code == 0
    data = json.loads(out)
    assert data["summary"] == ["10.0.0.0/23"]


def test_range(capsys):
    code, out, _ = run(capsys, ["range", "192.168.0.0", "192.168.0.255"])
    assert code == 0
    assert out.strip() == "192.168.0.0/24"


def test_range_json_ipv6(capsys):
    code, out, _ = run(capsys, ["range", "2001:db8::", "2001:db8::ff", "--json"])
    assert code == 0
    data = json.loads(out)
    assert data["cidrs"] == ["2001:db8::/120"]


def test_range_invalid_order_error(capsys):
    code, _, err = run(capsys, ["range", "192.168.0.10", "192.168.0.1"])
    assert code == 2
    assert "error:" in err


def test_no_command_prints_help(capsys):
    code, out, _ = run(capsys, [])
    assert code == 2
    assert "usage:" in out


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
