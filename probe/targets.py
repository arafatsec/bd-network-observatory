"""Fixed, neutral measurement targets. Changing these changes what the data means."""

DNS_NAMES: tuple[str, ...] = ("example.com", "wikipedia.org", "cloudflare.com")

PUBLIC_RESOLVERS: tuple[str, ...] = ("1.1.1.1", "8.8.8.8", "9.9.9.9")

# Label used in records instead of the system resolver's address, which is often
# a home router or ISP-assigned address and must not be recorded (docs/ETHICS.md).
SYSTEM_RESOLVER = "system"

TCP_TARGETS: tuple[tuple[str, int], ...] = (
    ("1.1.1.1", 443),
    ("8.8.8.8", 443),
    ("9.9.9.9", 443),
)

HTTP_URLS: tuple[str, ...] = (
    "https://cp.cloudflare.com/generate_204",
    "https://www.google.com/generate_204",
)

CHECK_TIMEOUT_S = 4.0

USER_AGENT = "bd-network-observatory-probe/0.1"
