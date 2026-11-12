import ipaddress
import json

import pytest

from subnetcalc import cli, core


def req(name, prefix=None, hosts=None, cidr=None, group=None):
    return {"name": name, "group": group, "prefix": prefix, "hosts": hosts, "cidr": cidr}


def cidrs(plan):
    return {s["name"]: s["cidr"] for s in plan["subnets"]}


def test_prefix_for_hosts_matches_usable_count():
    assert core.prefix_for_hosts(1, 4) == 32
    assert core.prefix_for_hosts(2, 4) == 31
    assert core.prefix_for_hosts(3, 4) == 29
    assert core.prefix_for_hosts(254, 4) == 24
    assert core.prefix_for_hosts(255, 4) == 23
    assert core.prefix_for_hosts(2 ** 64 - 1, 6) == 64
    assert core.prefix_for_hosts(2 ** 64, 6) == 63
    for hosts in (3, 14, 15, 62, 500, 4094):
        prefix = core.prefix_for_hosts(hosts, 4)
        net = ipaddress.ip_network("10.0.0.0/%d" % prefix)
        assert core.network_info(net)["num_usable"] >= hosts
        bigger = ipaddress.ip_network("10.0.0.0/%d" % (prefix + 1))
        assert core.network_info(bigger)["num_usable"] < hosts


def test_prefix_for_hosts_invalid():
    with pytest.raises(ValueError):
        core.prefix_for_hosts(0, 4)
    with pytest.raises(ValueError):
        core.prefix_for_hosts(2 ** 32, 4)


def test_plan_largest_first_no_overlap():
    plan = core.plan_subnets(
        "10.42.0.0/16",
        [req("small", prefix=26), req("app", hosts=500), req("web", prefix=24)],
    )
    assert cidrs(plan) == {
        "app": "10.42.0.0/23",
        "web": "10.42.2.0/24",
        "small": "10.42.3.0/26",
    }
    # Output keeps spec order, not allocation order.
    assert [s["name"] for s in plan["subnets"]] == ["small", "app", "web"]
    assert plan["subnets"][1]["num_usable"] == 510
    assert plan["subnets"][1]["source"] == "allocated"


def test_plan_ties_keep_spec_order():
    plan = core.plan_subnets(
        "10.0.0.0/24", [req("b", prefix=26), req("a", prefix=26), req("c", prefix=26)]
    )
    assert cidrs(plan) == {
        "b": "10.0.0.0/26",
        "a": "10.0.0.64/26",
        "c": "10.0.0.128/26",
    }


def test_plan_avoids_used():
    plan = core.plan_subnets(
        "10.0.0.0/22", [req("a", prefix=24), req("b", prefix=23)], used=["10.0.0.0/24"]
    )
    assert cidrs(plan) == {"b": "10.0.2.0/23", "a": "10.0.1.0/24"}
    assert plan["free"] == []


def test_plan_fixed_cidr_kept_and_others_fit_around():
    plan = core.plan_subnets(
        "10.0.0.0/24", [req("a", prefix=25), req("fixed", cidr="10.0.0.0/26")]
    )
    assert cidrs(plan) == {"fixed": "10.0.0.0/26", "a": "10.0.0.128/25"}
    assert plan["subnets"][1]["source"] == "fixed"


def test_plan_fixed_collides_with_used():
    with pytest.raises(ValueError, match="overlaps used 10.0.0.0/25"):
        core.plan_subnets(
            "10.0.0.0/24", [req("db", cidr="10.0.0.64/26")], used=["10.0.0.0/25"]
        )


def test_plan_fixed_collides_with_fixed():
    with pytest.raises(ValueError, match="overlaps"):
        core.plan_subnets(
            "10.0.0.0/24",
            [req("a", cidr="10.0.0.0/25"), req("b", cidr="10.0.0.64/26")],
        )


def test_plan_fixed_outside_supernet():
    with pytest.raises(ValueError, match="outside"):
        core.plan_subnets("10.0.0.0/24", [req("a", cidr="10.0.1.0/26")])


def test_plan_fixed_host_bits_rejected():
    with pytest.raises(ValueError):
        core.plan_subnets("10.0.0.0/24", [req("a", cidr="10.0.0.5/26")])


def test_plan_fixed_size_mismatch():
    with pytest.raises(ValueError, match="asks for /25"):
        core.plan_subnets("10.0.0.0/24", [req("a", prefix=25, cidr="10.0.0.0/26")])


def test_plan_out_of_space():
    # Both /25s are placed first, so the /26 is the one left without room.
    with pytest.raises(ValueError, match="subnet b: no free /26"):
        core.plan_subnets(
            "10.0.0.0/24", [req("a", prefix=25), req("b", prefix=26), req("c", prefix=25)]
        )


def test_plan_request_bigger_than_supernet():
    with pytest.raises(ValueError, match="does not fit"):
        core.plan_subnets("10.0.0.0/24", [req("a", hosts=1000)])


def test_plan_duplicate_names():
    with pytest.raises(ValueError, match="duplicate"):
        core.plan_subnets("10.0.0.0/24", [req("a", prefix=26), req("a", prefix=26)])


def test_plan_previous_keeps_existing_when_appending():
    spec = [req("web", prefix=24), req("app", prefix=24)]
    first = core.plan_subnets("10.0.0.0/16", spec)
    # Without --previous, a bigger new subnet goes first and renumbers.
    grown = spec + [req("big", prefix=20)]
    renumbered = core.plan_subnets("10.0.0.0/16", grown)
    assert cidrs(renumbered)["web"] != cidrs(first)["web"]
    stable = core.plan_subnets("10.0.0.0/16", grown, previous=cidrs(first))
    assert cidrs(stable)["web"] == cidrs(first)["web"]
    assert cidrs(stable)["app"] == cidrs(first)["app"]
    assert cidrs(stable)["big"] == "10.0.16.0/20"
    assert [s["source"] for s in stable["subnets"]] == ["previous", "previous", "allocated"]


def test_plan_previous_size_change_is_an_error():
    with pytest.raises(ValueError, match="previous"):
        core.plan_subnets(
            "10.0.0.0/16", [req("web", prefix=23)], previous={"web": "10.0.0.0/24"}
        )


def test_plan_previous_released_names():
    plan = core.plan_subnets(
        "10.0.0.0/16",
        [req("web", prefix=24)],
        previous={"web": "10.0.5.0/24", "old": "10.0.0.0/24"},
    )
    assert cidrs(plan) == {"web": "10.0.5.0/24"}
    assert plan["released"] == ["old"]
    assert "10.0.0.0/22" in plan["free"]


def test_plan_free_and_fragmentation():
    plan = core.plan_subnets("10.0.0.0/24", [req("a", prefix=26)])
    assert plan["free"] == ["10.0.0.64/26", "10.0.0.128/25"]
    assert plan["free_addresses"] == 192
    assert plan["largest_free"] == "10.0.0.128/25"
    # 192 free addresses could at best hold a /25: no fragmentation.
    assert plan["fragmentation"] == 0.0

    scattered = core.plan_subnets(
        "10.0.0.0/24", [req("a", cidr="10.0.0.64/26"), req("b", cidr="10.0.0.192/26")]
    )
    # 128 free addresses, but the largest block is a /26 (64).
    assert scattered["fragmentation"] == 0.5

    full = core.plan_subnets("10.0.0.0/25", [req("a", prefix=25)])
    assert full["free"] == [] and full["fragmentation"] == 0.0
    assert full["largest_free"] is None


def test_plan_ipv6():
    plan = core.plan_subnets(
        "2001:db8::/48", [req("a", prefix=64), req("b", prefix=56), req("c", hosts=1000)]
    )
    assert cidrs(plan) == {
        "b": "2001:db8::/56",
        "a": "2001:db8:0:100::/64",
        "c": "2001:db8:0:101::/118",
    }


def test_plan_allocations_never_overlap_many():
    spec = [req("n%d" % i, prefix=20 + i % 9) for i in range(60)]
    plan = core.plan_subnets("10.0.0.0/12", spec, used=["10.1.0.0/16"])
    nets = [ipaddress.ip_network(s["cidr"]) for s in plan["subnets"]]
    nets.append(ipaddress.ip_network("10.1.0.0/16"))
    for i, a in enumerate(nets):
        for b in nets[i + 1:]:
            assert not a.overlaps(b)


def test_parse_plan_spec():
    supernet, requests = core.parse_plan_spec(
        {
            "supernet": "10.0.0.0/16",
            "subnets": [{"name": "a", "prefix": 24, "group": "app"}, {"name": "b", "hosts": 5}],
        }
    )
    assert supernet == "10.0.0.0/16"
    assert requests == [req("a", prefix=24, group="app"), req("b", hosts=5)]


@pytest.mark.parametrize(
    "spec, message",
    [
        ([], "must be an object"),
        ({"subnets": {}}, "must be a list"),
        ({"subnets": [], "extra": 1}, "unknown plan spec keys"),
        ({"subnets": [{"name": "a"}]}, "needs prefix, hosts or cidr"),
        ({"subnets": [{"name": "a", "prefix": 24, "hosts": 3}]}, "not both"),
        ({"subnets": [{"name": "a b", "prefix": 24}]}, "subnet name"),
        ({"subnets": [{"name": "a", "prefix": "24"}]}, "integer"),
        ({"subnets": [{"name": "a", "prefix": True}]}, "integer"),
        ({"subnets": [{"name": "a", "prefix": 24, "zone": "x"}]}, "unknown subnet keys"),
        ({"subnets": [{"name": "a", "prefix": 24, "group": "x y"}]}, "invalid group"),
    ],
)
def test_parse_plan_spec_errors(spec, message):
    with pytest.raises(ValueError, match=message):
        core.parse_plan_spec(spec)


SPEC = {
    "supernet": "10.42.0.0/16",
    "subnets": [
        {"name": "public-a", "prefix": 24, "group": "public"},
        {"name": "app-a", "hosts": 500, "group": "app"},
        {"name": "db", "prefix": 26},
    ],
}


def run(capsys, argv):
    code = cli.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.fixture
def spec_file(tmp_path):
    path = tmp_path / "network.json"
    path.write_text(json.dumps(SPEC))
    return str(path)


def test_cli_plan_table(capsys, spec_file):
    code, out, _ = run(capsys, ["plan", "--spec", spec_file])
    assert code == 0
    lines = out.splitlines()
    assert lines[0].split() == ["NAME", "GROUP", "CIDR", "USABLE"]
    assert lines[1].split() == ["public-a", "public", "10.42.2.0/24", "254"]
    assert lines[2].split() == ["app-a", "app", "10.42.0.0/23", "510"]
    assert lines[3].split() == ["db", "-", "10.42.3.0/26", "62"]
    assert "Supernet: 10.42.0.0/16" in lines
    assert any(line.startswith("Free: ") and "fragmentation 0.0%" in line for line in lines)


def test_cli_plan_hcl(capsys, spec_file):
    code, out, _ = run(capsys, ["plan", "--spec", spec_file, "--format", "hcl"])
    assert code == 0
    assert "locals {\n  subnet_cidrs = {\n" in out
    assert '    "public-a" = "10.42.2.0/24"\n' in out
    assert '    "db"       = "10.42.3.0/26"\n' in out
    assert '    "app" = {\n      "app-a" = "10.42.0.0/23"\n    }\n' in out


def test_cli_plan_hcl_without_groups(capsys):
    code, out, _ = run(capsys, ["plan", "10.0.0.0/24", "--subnet", "a=/26", "--format", "hcl"])
    assert code == 0
    assert "subnet_groups" not in out
    assert out.endswith('  subnet_cidrs = {\n    "a" = "10.0.0.0/26"\n  }\n}\n')


def test_cli_plan_yaml(capsys, spec_file):
    code, out, _ = run(capsys, ["plan", "--spec", spec_file, "--format", "yaml"])
    assert code == 0
    assert out.startswith('supernet: "10.42.0.0/16"\nsubnets:\n  "public-a": "10.42.2.0/24"\n')
    assert 'groups:\n  "public":\n    "public-a": "10.42.2.0/24"\n' in out
    assert '\nfree:\n  - "10.42.3.64/26"\n' in out


def test_cli_plan_json_and_previous_round_trip(capsys, spec_file, tmp_path):
    prev = tmp_path / "plan.json"
    code, _, _ = run(capsys, ["plan", "--spec", spec_file, "--json", "--out", str(prev)])
    assert code == 0
    first = json.loads(prev.read_text())
    assert first["supernet"] == "10.42.0.0/16"

    code, out, _ = run(
        capsys,
        ["plan", "--spec", spec_file, "--subnet", "big=/20", "--previous", str(prev), "--json"],
    )
    assert code == 0
    data = json.loads(out)
    got = {s["name"]: s["cidr"] for s in data["subnets"]}
    for subnet in first["subnets"]:
        assert got[subnet["name"]] == subnet["cidr"]
    assert got["big"] == "10.42.16.0/20"


def test_cli_plan_subnet_flags_hosts_and_prefix(capsys):
    code, out, _ = run(
        capsys, ["plan", "10.0.0.0/24", "--subnet", "a=100", "--subnet", "b=/26", "--json"]
    )
    assert code == 0
    data = json.loads(out)
    assert [(s["name"], s["cidr"]) for s in data["subnets"]] == [
        ("a", "10.0.0.0/25"),
        ("b", "10.0.0.128/26"),
    ]


def test_cli_plan_used_collision(capsys, tmp_path):
    spec = tmp_path / "s.json"
    spec.write_text(json.dumps({"subnets": [{"name": "db", "cidr": "10.0.0.0/26"}]}))
    code, _, err = run(
        capsys, ["plan", "10.0.0.0/24", "--spec", str(spec), "--used", "10.0.0.32/27"]
    )
    assert code == 2
    assert "overlaps used 10.0.0.32/27" in err


def test_cli_plan_supernet_mismatch(capsys, spec_file):
    code, _, err = run(capsys, ["plan", "10.0.0.0/16", "--spec", spec_file])
    assert code == 2
    assert "does not match" in err


def test_cli_plan_needs_supernet_and_subnets(capsys):
    code, _, err = run(capsys, ["plan", "--subnet", "a=/24"])
    assert code == 2 and "no supernet" in err
    code, _, err = run(capsys, ["plan", "10.0.0.0/16"])
    assert code == 2 and "nothing to plan" in err


def test_cli_plan_bad_subnet_flag():
    with pytest.raises(SystemExit):
        cli.main(["plan", "10.0.0.0/16", "--subnet", "a"])


def test_cli_plan_invalid_spec_json(capsys, tmp_path):
    spec = tmp_path / "s.json"
    spec.write_text("{nope")
    code, _, err = run(capsys, ["plan", "10.0.0.0/16", "--spec", str(spec)])
    assert code == 2 and "invalid JSON" in err


def test_cli_plan_bad_previous(capsys, spec_file, tmp_path):
    prev = tmp_path / "p.json"
    prev.write_text('{"cidrs": {}}')
    code, _, err = run(capsys, ["plan", "--spec", spec_file, "--previous", str(prev)])
    assert code == 2 and "not the JSON output" in err
