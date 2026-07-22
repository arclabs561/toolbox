# pinglet

Show local/public IP addresses and run bounded, read-only network diagnostics.

## Usage

```sh
pinglet          # local interfaces + public IP
pinglet -v       # add geo info (city, country, org)
pinglet -4       # force IPv4 for public lookup
pinglet -6       # force IPv6 for public lookup
pinglet -c       # copy public IP to clipboard
pinglet -p       # public IP only (skip local)
pinglet diag     # inspect route, DNS, HTTPS, gateway latency, and quality
pinglet link     # show local configuration and addresses
pinglet peers    # show passive neighbor-cache entries
pinglet speed HOST  # bounded TCP probe plus gateway latency before/during load
pinglet diag --json
```

`pingl` is a short PATH shortcut for `pinglet`.

`diag` performs a bounded gateway ping, DNS resolution, and HTTPS request using
stable built-in targets. It reports percentile latency, variance, loss, and
explicitly labeled delay variation. `summary.reachability` answers whether the
path responded; `summary.quality` can be `pass`, `degraded`, or `unknown` when
latency tails or loss indicate a poor path despite successful replies. `link`
identifies the active interface and includes native Wi-Fi telemetry when the
platform provides it. Wi-Fi describes the local radio link, not whether the
upstream connection is a hotspot or an infrastructure access point. `peers`
reads the native neighbor cache; it does not prove that a device is currently
online. The latency statistics are RTT statistics from the gateway ping;
`rtt_ipdv` and `rtt_pdv` must not be read as one-way delay measurements.
Variance is the sample variance (`n - 1`).

`speed HOST` is deliberately not an internet speed test. It requires an iperf3
server on `HOST`, runs a fixed 10-second TCP test, and reports gateway latency
both before and while the link is loaded. It is the only mode that intentionally
moves substantial data. None of these modes scans the LAN, captures traffic, or
changes network state.

For richer passive LAN observation, Bettercap can be used separately with its
read-only `net.recon` module; `pinglet` deliberately does not start it or enable
active probing.
