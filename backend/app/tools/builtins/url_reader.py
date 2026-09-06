import html
import ipaddress
import re
import socket
from typing import Any
import urllib.parse
import urllib.request

from app.tools.base import BaseTool, ToolExecutionContext, ToolPermission, ToolResult


class SSRFValidator:
    """Validates destination URLs to prevent Server-Side Request Forgery (SSRF)."""

    _BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "metadata.google.internal"}
    _BLOCKED_DOMAINS = (".local", ".internal", ".lan", ".arpa", ".corp", ".intranet")

    _PRIVATE_NETWORKS = [
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("169.254.0.0/16"),  # Link-local & cloud metadata
        ipaddress.ip_network("0.0.0.0/8"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("fc00::/7"),
        ipaddress.ip_network("fe80::/10"),
    ]

    @classmethod
    def validate_url(cls, url_str: str) -> str:
        """Validate URL and return cleaned URL string or raise ValueError."""
        if not url_str or not url_str.strip():
            raise ValueError("URL cannot be empty")

        parsed = urllib.parse.urlparse(url_str.strip())
        if parsed.scheme.lower() not in ("http", "https"):
            raise ValueError(f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are allowed.")

        hostname = parsed.hostname
        if not hostname:
            raise ValueError("Invalid URL: missing hostname")

        hostname_lower = hostname.lower()

        # Check blocked hostnames
        if hostname_lower in cls._BLOCKED_HOSTS or any(hostname_lower.endswith(sfx) for sfx in cls._BLOCKED_DOMAINS):
            raise ValueError(f"Access to private/internal destination '{hostname}' is blocked for security.")

        # Resolve IP addresses and check against private networks
        try:
            # Check if host is direct IP
            try:
                ip = ipaddress.ip_address(hostname)
                if any(ip in net for net in cls._PRIVATE_NETWORKS):
                    raise ValueError(f"Access to private IP address '{ip}' is blocked for security.")
            except ValueError:
                # Hostname is a domain name -> resolve via DNS
                addr_info = socket.getaddrinfo(hostname, None)
                for res in addr_info:
                    ip_str = res[4][0]
                    resolved_ip = ipaddress.ip_address(ip_str)
                    if any(resolved_ip in net for net in cls._PRIVATE_NETWORKS):
                        raise ValueError(f"Access to private network IP '{resolved_ip}' (resolved from '{hostname}') is blocked for security.")
        except socket.gaierror:
            # If DNS resolution fails, allow urllib to fail naturally on network lookup
            pass

        return url_str.strip()


class URLReaderTool(BaseTool):
    name = "read_url"
    description = "Fetch, read, and extract clean text content from a public web page URL."
    category = "utility"
    permissions = [ToolPermission.NETWORK]

    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The full HTTP/HTTPS URL of the public web page to read.",
            },
            "max_length": {
                "type": "integer",
                "description": "Maximum character length of content to extract (default: 8000).",
                "default": 8000,
            },
        },
        "required": ["url"],
    }

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        raw_url = str(arguments.get("url", ""))

        # 1. SSRF Validation
        try:
            url = SSRFValidator.validate_url(raw_url)
        except ValueError as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Security rejection: {str(exc)}",
                source="ssrf_shield",
            )

        max_length = int(arguments.get("max_length", 8000))
        max_length = min(max_length, 20000)

        # 2. Fetch with headers and timeout
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,text/plain",
        }

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=6.0) as response:
                # Enforce max 100KB download limit
                raw_bytes = response.read(102400)
                content = raw_bytes.decode("utf-8", errors="ignore")

            title = "Web Page"
            title_match = re.search(r"<title[^>]*>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
            if title_match:
                title = html.unescape(re.sub(r"<[^>]+>", "", title_match.group(1)).strip())

            # Strip non-content tags: script, style, noscript, nav, footer, header
            cleaned = re.sub(r"<(script|style|noscript|nav|footer|header)[^>]*>.*?</\1>", " ", content, flags=re.IGNORECASE | re.DOTALL)
            # Replace paragraph/div/breaks with newlines
            cleaned = re.sub(r"</?(p|div|br|h[1-6]|li)[^>]*>", "\n", cleaned, flags=re.IGNORECASE)
            # Remove remaining tags
            cleaned = re.sub(r"<[^>]+>", " ", cleaned)
            cleaned = html.unescape(cleaned)
            # Collapse whitespace
            cleaned = re.sub(r"[ \t]+", " ", cleaned)
            cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned).strip()

            if len(cleaned) > max_length:
                cleaned = cleaned[:max_length] + "\n\n...[Content truncated]"

            return ToolResult(
                tool_name=self.name,
                success=True,
                data={
                    "url": url,
                    "title": title,
                    "content": cleaned,
                    "content_length": len(cleaned),
                },
                source="url_reader",
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=f"Failed to read URL: {str(exc)}",
                source="url_reader",
            )
