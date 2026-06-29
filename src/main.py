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
        proxy_configuration = None
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

        # Subdomains to cycle through to bypass AWS WAF challenge page
        subdomains = ["www", "uk", "de", "nl", "dk", "fr", "it", "es"]

        while page <= max_pages:
            response = None
            success = False
            
            for attempt in range(1, 17):  # 16 attempts
                subdomain = subdomains[(attempt - 1) % len(subdomains)]
                url = f"https://{subdomain}.trustpilot.com/review/{clean_domain}?page={page}"
                Actor.log.info(f"Scraping page {page} (attempt {attempt}, domain: {subdomain}.trustpilot.com): {url}")
                
                try:
                    current_proxies = None
                    if proxy_config and proxy_configuration:
                        # Re-request a new proxy URL to force rotation
                        current_proxy_url = await proxy_configuration.new_url()
                        current_proxies = {
                            "http": current_proxy_url,
                            "https": current_proxy_url
                        }
                    
                    # Pass proxies to AsyncSession constructor (correct plural dict param)
                    # Let curl_cffi auto-impersonate chrome110 which works very well
                    async with curl_requests.AsyncSession(proxies=current_proxies, timeout=15.0) as client:
                        response = await client.get(url, impersonate="chrome110")
                    
                    if response.status_code == 200:
                        if "__NEXT_DATA__" in response.text:
                            success = True
                            break
                        else:
                            Actor.log.warning(f"Page {page} attempt {attempt} returned 200 but did not contain __NEXT_DATA__. Might be blocked. Retrying...")
                    elif response.status_code == 404:
                        Actor.log.warning(f"Page {page} returned 404. Stopping scrape.")
                        break
                    else:
                        Actor.log.warning(f"Page {page} attempt {attempt} failed with status {response.status_code}. Retrying...")
                    
                    await asyncio.sleep(random.uniform(1.0, 3.0))
                except Exception as e:
                    Actor.log.warning(f"Page {page} attempt {attempt} raised exception: {e}. Retrying...")
                    await asyncio.sleep(random.uniform(1.0, 3.0))

            if not success:
                if response and response.status_code == 404:
                    break
                Actor.log.error(f"Failed to fetch page {page} after multiple attempts.")
                if response:
                    Actor.log.error(f"Last status code: {response.status_code}")
                    Actor.log.error(f"Response headers: {response.headers}")
                    Actor.log.error(f"Response body (first 500 chars): {response.text[:500]}")
                break

            try:
                soup = BeautifulSoup(response.text, "html.parser")
                script_tag = soup.find("script", id="__NEXT_DATA__")
                
                if not script_tag:
                    Actor.log.error(f"Could not find __NEXT_DATA__ JSON tag on page {page}!")
                    break

                data = json.loads(script_tag.string)
                props = data.get("props", {})
                page_props = props.get("pageProps", {})
                
                # Extract business unit details
                biz_unit = page_props.get("businessUnit", {})
                company_name = biz_unit.get("displayName", "Unknown")
                company_id = biz_unit.get("id", "")
                
                # Extract reviews array
                reviews = page_props.get("reviews", [])
                if not reviews:
                    Actor.log.info(f"No reviews found on page {page}. Stopping.")
                    break
                
                valid_reviews = []
                for review in reviews:
                    rating = review.get("rating", 0)
                    if rating >= min_rating:
                        mapped = map_review_item(review, company_name, company_id, clean_domain)
                        valid_reviews.append(mapped)
                
                if valid_reviews:
                    await Actor.push_data(valid_reviews)
                    total_extracted += len(valid_reviews)
                    Actor.log.info(f"Successfully extracted {len(valid_reviews)} reviews from page {page}")
                else:
                    Actor.log.info(f"No reviews matching rating >= {min_rating} on page {page}")
                
                # Check if we have reached the last page
                pagination = page_props.get("filters", {}).get("pagination", {})
                next_page = pagination.get("nextPage")
                if not next_page:
                    Actor.log.info("Reached the last page of reviews.")
                    break
                    
            except Exception as e:
                Actor.log.error(f"An error occurred while scraping page {page}: {e}")
                break
            
            page += 1
            # Small polite delay between requests
            await asyncio.sleep(random.uniform(1.0, 2.5))
        
        Actor.log.info(f"Scrape completed. Total reviews extracted: {total_extracted}")
