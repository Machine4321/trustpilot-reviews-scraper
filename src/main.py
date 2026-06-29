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
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]


def clean_domain_name(domain_input: str) -> str:
    """Normalizes raw input or full Trustpilot URL into a clean domain name."""
    clean = domain_input.strip().lower()
    # Strip protocol
    clean = re.sub(r'^(https?://)?(www\.)?', '', clean)
    # Strip Trustpilot review page prefix if pasted full URL
    clean = re.sub(r'^trustpilot\.com/review/', '', clean)
    # Strip trailing paths, queries, or hashes
    clean = re.split(r'[/?#]', clean)[0]
    return clean


def map_review_item(review: dict, company_name: str, company_id: str, company_domain: str) -> dict:
    """Maps raw Trustpilot NEXT_DATA review structure to a clean flat JSON output."""
    dates = review.get("dates", {})
    consumer = review.get("consumer", {})
    reply = review.get("reply") or {}
    
    return {
        "id": review.get("id"),
        "companyName": company_name,
        "companyId": company_id,
        "companyDomain": company_domain,
        "title": review.get("title"),
        "text": review.get("text"),
        "rating": review.get("rating"),
        "likes": review.get("likes", 0),
        "language": review.get("language"),
        "publishedDate": dates.get("publishedDate"),
        "experiencedDate": dates.get("experiencedDate"),
        "updatedDate": dates.get("updatedDate"),
        "authorName": consumer.get("displayName"),
        "authorId": consumer.get("id"),
        "authorCountry": consumer.get("countryCode"),
        "authorReviewsCount": consumer.get("numberOfReviews", 0),
        "authorIsVerified": consumer.get("isVerified", False),
        "isVerified": review.get("labels", {}).get("verification", {}).get("isVerified", False),
        "replyText": reply.get("text"),
        "replyDate": reply.get("publishedDate")
    }


async def main() -> None:
    async with Actor:
        # Get and parse input
        actor_input = await Actor.get_input() or {}
        raw_domain = actor_input.get("domain")
        
        if not raw_domain:
            Actor.log.error("Input parameter 'domain' is missing!")
            await Actor.fail(status_message="Input parameter 'domain' is missing.")
            return

        clean_domain = clean_domain_name(raw_domain)
        max_pages = actor_input.get("maxPages", 5)
        min_rating = int(actor_input.get("minRating", 1))
        proxy_config = actor_input.get("proxyConfiguration")

        Actor.log.info(f"Starting Trustpilot Scraper for domain: '{clean_domain}'")
        Actor.log.info(f"Max Pages: {max_pages} | Min Rating: {min_rating}")

        # Set up proxy URL if configured
        proxy_url = None
        if proxy_config:
            proxy_configuration = await Actor.create_proxy_configuration(actor_proxy_input=proxy_config)
            if proxy_configuration:
                proxy_url = await proxy_configuration.new_url()
                Actor.log.info("Using proxy configuration.")
            else:
                Actor.log.info("Proxy configuration provided but empty. Proceeding without proxy.")
        else:
            Actor.log.info("No proxy configuration provided. Proceeding direct.")

        # Crawl paginated review pages
        page = 1
        total_extracted = 0
        
        # Configure client with optional proxy
        proxies = None
        if proxy_url:
            proxies = {
                "http": proxy_url,
                "https": proxy_url
            }

        async with curl_requests.AsyncSession(proxies=proxies, timeout=15.0) as client:
            while page <= max_pages:
                url = f"https://www.trustpilot.com/review/{clean_domain}?page={page}"
                Actor.log.info(f"Scraping page {page}: {url}")

                # Configure realistic browser headers
                headers = {
                    "User-Agent": random.choice(USER_AGENTS),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Ch-Ua-Platform": '"Windows"',
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                    "Upgrade-Insecure-Requests": "1"
                }

                try:
                    response = await client.get(url, headers=headers, impersonate="chrome110")
                    
                    if response.status_code == 404:
                        Actor.log.warning(f"Page {page} returned 404. Stopping scrape.")
                        break
                    elif response.status_code != 200:
                        Actor.log.error(f"Failed to fetch page {page}. Status Code: {response.status_code}")
                        break

                    soup = BeautifulSoup(response.text, "html.parser")
                    script_tag = soup.find("script", id="__NEXT_DATA__")
                    
                    if not script_tag:
                        Actor.log.error(f"Could not find __NEXT_DATA__ JSON tag on page {page}!")
                        # If we can't find it, we might be blocked by Cloudflare (403 or captcha)
                        if "captcha" in response.text.lower() or "cloudflare" in response.text.lower():
                            Actor.log.error("Scraper seems to be blocked by bot protection. Please use proxies.")
                        break

                    data = json.loads(script_tag.string)
                    page_props = data.get("props", {}).get("pageProps", {})
                    
                    # Extract business unit metadata
                    business_unit = page_props.get("businessUnit", {})
                    company_name = business_unit.get("displayName") or clean_domain
                    company_id = business_unit.get("id") or ""

                    reviews = page_props.get("reviews", [])
                    
                    if not reviews:
                        Actor.log.info(f"No reviews found on page {page}. Scraping complete.")
                        break

                    # Map and filter reviews
                    page_results = []
                    for r in reviews:
                        rating = r.get("rating", 0)
                        if rating >= min_rating:
                            mapped = map_review_item(r, company_name, company_id, clean_domain)
                            page_results.append(mapped)

                    if page_results:
                        await Actor.push_data(page_results)
                        total_extracted += len(page_results)
                        Actor.log.info(f"Successfully extracted {len(page_results)} reviews from page {page}.")
                    else:
                        Actor.log.info(f"No reviews matched the minimum rating filter of {min_rating} on page {page}.")

                    # Sleep briefly between requests to mimic human browsing behavior
                    await asyncio.sleep(random.uniform(1.0, 2.5))
                    page += 1

                except Exception as e:
                    Actor.log.error(f"An error occurred while scraping page {page}: {str(e)}")
                    break

        Actor.log.info(f"Scrape completed. Total reviews extracted: {total_extracted}")

if __name__ == "__main__":
    asyncio.run(main())
