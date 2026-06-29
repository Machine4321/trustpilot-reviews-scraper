import asyncio
import json
import random
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from apify import Actor


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

        Actor.log.info(f"Starting Trustpilot Scraper (Playwright) for domain: '{clean_domain}'")
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

        # Subdomains to cycle through to bypass AWS WAF challenge page
        subdomains = ["www", "uk", "de", "nl", "dk", "fr", "it", "es"]
        
        async with async_playwright() as p:
            # Configure browser launch options
            # Set headless to False to run headful Chromium inside Xvfb (to easily pass anti-bot WAF checks!)
            launch_options = {
                "headless": False
            }
            if proxy_url:
                parsed = urlparse(proxy_url)
                launch_options["proxy"] = {
                    "server": f"http://{parsed.hostname}:{parsed.port}",
                    "username": parsed.username,
                    "password": parsed.password
                }
                Actor.log.info(f"Configuring Playwright proxy: {parsed.hostname}:{parsed.port}")
                
            browser = await p.chromium.launch(**launch_options)
            
            # Use realistic browser context options
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="en-US",
                timezone_id="America/New_York"
            )
            
            page = 1
            total_extracted = 0
            
            while page <= max_pages:
                response = None
                success = False
                script_content = None
                
                # Cycle subdomains for each page to bypass WAF
                for attempt in range(1, 9):
                    subdomain = subdomains[(attempt - 1) % len(subdomains)]
                    url = f"https://{subdomain}.trustpilot.com/review/{clean_domain}?page={page}"
                    Actor.log.info(f"Opening page {page} (attempt {attempt}, domain: {subdomain}.trustpilot.com)")
                    
                    web_page = await context.new_page()
                    try:
                        # Navigate and wait for content
                        response = await web_page.goto(url, timeout=30000, wait_until="domcontentloaded")
                        
                        if response.status == 404:
                            Actor.log.warning(f"Page {page} returned 404 on {subdomain}.trustpilot.com. Stopping.")
                            response = 404
                            break
                        
                        # Wait for script tag to be ATTACHED to the DOM (state="attached" is required because script tags are hidden!)
                        # We also increase timeout to 30s to allow headful WAF solving to finish
                        await web_page.wait_for_selector("script#__NEXT_DATA__", state="attached", timeout=30000)
                        
                        script_content = await web_page.eval_on_selector("script#__NEXT_DATA__", "el => el.textContent")
                        if script_content:
                            success = True
                            break
                    except Exception as e:
                        Actor.log.warning(f"Page {page} attempt {attempt} failed: {e}")
                    finally:
                        await web_page.close()
                        
                    await asyncio.sleep(random.uniform(1.0, 2.5))
                
                if not success:
                    if response == 404:
                        break
                    Actor.log.error(f"Failed to fetch page {page} after multiple attempts.")
                    break

                try:
                    data = json.loads(script_content)
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
                    Actor.log.error(f"An error occurred while parsing page {page}: {e}")
                    break
                
                page += 1
                # Small polite delay between requests
                await asyncio.sleep(random.uniform(1.5, 3.0))
                
            await browser.close()
            
        Actor.log.info(f"Scrape completed. Total reviews extracted: {total_extracted}")
