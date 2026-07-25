# Changelog

All notable changes to this project are documented here. The format loosely
follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Fixed
- `num_usable` for IPv6 blocks shorter than `/127` no longer counts the
  all-zeros interface identifier, which is reserved as the Subnet-Router
  anycast address (RFC 4291 §2.6.1) and was already excluded from the
  `first_host`..`last_host` range reported next to it. A `/64` now reports
  `2^64 - 1` usable hosts instead of `2^64`. IPv4, IPv6 `/127` (RFC 6164)
  and `/128` counts are unchanged.
- `contains` now honours `strict` for its second argument. Previously host
  bits were rejected in the containing network but silently accepted in a
  network passed as the address to test.
- `summarize` with `strict=True` now reports "has host bits set" for an input
  like `10.1.2.3/24` instead of a misleading "does not appear to be an IPv4
  or IPv6 address".
- `python_requires` raised to `>=3.7`: `contains` uses
  `ipaddress.IPv4Network.subnet_of`, which does not exist on 3.6.

### Added
- `tests/test_reference.py`: differential tests that check every command
  against the standard library `ipaddress` module across all 33 IPv4 and 129
  IPv6 prefix lengths, plus structural invariants (splits tile their parent
  exactly, summaries preserve the input address set, ranges are contiguous
  and exact).

### Changed
- Dev dependencies unpinned from `pytest==6.2.4`, which could not collect the
  test suite at all on Python 3.12+ (its assertion rewriter uses the removed
  `ast.Str`), to `pytest>=7.4,<9`; `flake8` added.
- CI runs on Python 3.9 through 3.13 instead of 3.9 only, runs the `flake8`
  configuration the repo already shipped, and uses current action versions.

## [0.1.0]

### Added
- `info` command: network/broadcast/netmask/wildcard, host range, usable host
  count, prefix, and classification flags (private, global, multicast,
  reserved, loopback, link-local) for IPv4 and IPv6.
- `split` command: subdivide a block by target `--prefix` or into `--count`
  equal parts.
- `contains` command: address/network membership test with a result-driven
  exit code.
- `overlaps` command: report whether two networks intersect.
- `summarize` command: collapse addresses/networks into a minimal CIDR set.
- `range` command: smallest CIDR set covering an inclusive address range.
- `--json` output for every command, accepted before or after the subcommand.
- Pure, I/O-free `subnetcalc.core` API for library use.
