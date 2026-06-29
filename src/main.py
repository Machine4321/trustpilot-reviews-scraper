import asyncio
import json
import random
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests
from apify import Actor

async def main() -> None:
    async with Actor:
        # Create proxy config
        opts = {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"], "apifyProxyCountry": "US"}
        config = await Actor.create_proxy_configuration(actor_proxy_input=opts)
        p_url = await config.new_url() if config else None
        proxies = {"http": p_url, "https": p_url} if p_url else None
        
        # Test 1: find API on www
        url1 = "https://www.trustpilot.com/api/businessunits/find?name=apify.com"
        # Test 2: find API on widget.trustpilot.com
        url2 = "https://widget.trustpilot.com/feedback-api/v1/businesses/find?domain=apify.com"
        # Test 3: feedback reviews API on widget
        url3 = "https://widget.trustpilot.com/feedback-api/v1/businesses/62ac9c3177fbadc00785d7fe/reviews?templateId=54d39f65764ea907c0f34850&locale=en-US&page=1"
        
        tests = [
            ("www find", url1),
            ("widget find", url2),
            ("widget reviews", url3)
        ]
        
        async with curl_requests.AsyncSession(proxies=proxies, timeout=15.0) as client:
            for name, url in tests:
                try:
                    response = await client.get(url, impersonate="chrome120")
                    Actor.log.info(f"[TEST API] Name: {name} | Status: {response.status_code} | Body: {response.text[:300]}")
                except Exception as e:
                    Actor.log.error(f"[TEST API] Name: {name} | Error: {e}")
