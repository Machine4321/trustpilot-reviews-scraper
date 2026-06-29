import asyncio
import json
import random
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests
from apify import Actor


# List of browser-like User-Agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]


async def main() -> None:
    async with Actor:
        # Test matrix to find the winning config to bypass AWS WAF!
        profiles = ["chrome120", "chrome110", "safari15_5", "firefox117"]
        proxy_options = [
            ("Residential US", True, "US"),
            ("Residential GB", True, "GB"),
            ("Residential Anywhere", True, None),
            ("Datacenter", False, None)
        ]
        
        url = "https://www.trustpilot.com/review/apify.com"
        
        for name, use_residential, country in proxy_options:
            for profile in profiles:
                try:
                    # Create proxy config
                    if use_residential:
                        opts = {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]}
                        if country:
                            opts["apifyProxyCountry"] = country
                    else:
                        opts = {"useApifyProxy": True, "apifyProxyGroups": ["SHADER"]}
                    
                    config = await Actor.create_proxy_configuration(actor_proxy_input=opts)
                    p_url = await config.new_url() if config else None
                    proxies = {"http": p_url, "https": p_url} if p_url else None
                    
                    async with curl_requests.AsyncSession(proxies=proxies, timeout=15.0) as client:
                        response = await client.get(url, impersonate=profile)
                        
                    soup = BeautifulSoup(response.text, "html.parser")
                    title = soup.title.string.strip() if soup.title else "No Title"
                    has_data = "__NEXT_DATA__" in response.text
                    
                    Actor.log.info(f"[TEST] Proxy: {name} | Profile: {profile} | Status: {response.status_code} | Title: {title} | HasData: {has_data}")
                except Exception as e:
                    Actor.log.error(f"[TEST] Proxy: {name} | Profile: {profile} | Error: {e}")
                
                await asyncio.sleep(1.0)
