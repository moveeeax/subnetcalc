# Changelog

All notable changes to this project are documented here. The format loosely
follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- `free` command and `core.free_space` / `core.next_free`: list the
  unallocated blocks of a CIDR after subtracting `--used` / `--used-file`
  entries, with a total, `--min-prefix` to hide small fragments and
  `--next /N` for the lowest free block of one size (#8).
- `plan` command and `core.plan_subnets`: allocate named subnets from a
  supernet by prefix length or host count, largest first and without
  overlaps, from a JSON spec or `--subnet` flags. Supports groups, pinned
  CIDRs, `--used` collision checks, `--previous` for stable allocation, a
  free-space and fragmentation report, and table, JSON, YAML or Terraform
  `locals` output (#3, from the archived `cidr-plan` idea).

## [0.2.0] - unreleased

### Fixed
- `split` refuses requests that would produce more than 1,000,000 subnets
  (for example `10.0.0.0/8 --prefix 32`) with a clear error instead of
  hanging and exhausting memory.
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

### Added
- `tests/test_reference.py`: differential tests that check every command
  against the standard library `ipaddress` module across all 33 IPv4 and 129
  IPv6 prefix lengths, plus structural invariants (splits tile their parent
  exactly, summaries preserve the input address set, ranges are contiguous
  and exact).

### Changed
- `python_requires` raised to `>=3.11`; Python 3.7-3.10 are end-of-life.
  Classifiers now list 3.11 through 3.15.
- CI matrix is Python 3.11 through 3.15, on `actions/checkout@v7` and
  `actions/setup-python@v7`.
- Dev dependencies unpinned from `pytest==6.2.4`, which could not collect the
  test suite at all on Python 3.12+ (its assertion rewriter uses the removed
  `ast.Str`), to `pytest>=7.4,<10`; `flake8` added.
- CI runs the `flake8` configuration the repo already shipped.

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
