# 🌟 Trustpilot Reviews Scraper (Ultra-Fast & Proxy-Free)

A high-performance, lightweight, and cost-effective tool to extract customer reviews, ratings, and business responses from any domain on **Trustpilot.com**. 

Instead of running a heavy and expensive headless browser (like Chrome or Puppeteer) which consumes a massive amount of RAM and CPU, this Actor extracts the pre-rendered JSON payload directly from the HTML source. It is designed to run perfectly on the minimum **256MB RAM** limit, saving you money and making runs virtually free!

---

## ⚡ Key Features

*   **Ultra-Fast Performance**: Scrapes up to 20 reviews per page in milliseconds.
*   **Zero Extra Platform Costs**: Lightweight footprint runs within Apify's free-tier RAM limits.
*   **Deep Metadata Extraction**: Captures ratings, review titles, full text, dates, likes, and business responses.
*   **Consumer Insights**: Extracts consumer names, IDs, country codes, total reviews written, and verification status.
*   **Built-in Smart Pagination**: Easily crawls multiple pages by setting `maxPages`.
*   **Bypass Blocks**: Designed to utilize Apify's free rotating proxies automatically.

---

## 🔍 Use Cases

*   **Brand Sentiment Analysis**: Track what customers are saying about your brand in real-time.
*   **Competitor Monitoring**: Download your competitors' reviews to identify their weaknesses and user complaints.
*   **Market Research**: Aggregate customer feedback across specific industries (SaaS, E-commerce, Finance).
*   **Lead Generation**: Identify highly active reviewers or businesses replying to reviews.

---

## 📥 Input parameters

The Actor accepts the following input parameters:

| Field | Type | Description | Default |
| :--- | :--- | :--- | :--- |
| `domain` | String | **Required**. The target company domain (e.g. `apify.com`, `amazon.com`). | `apify.com` |
| `maxPages` | Integer | Maximum number of review pages to scrape (20 reviews per page). | `5` |
| `minRating` | Integer | Filter reviews by a minimum star rating (1-5). | `1` |
| `proxyConfiguration` | Object | Apify proxy configuration (recommended to use default Apify Proxy). | `{"useApifyProxy": true}` |

---

## 📤 Output Dataset Example

Each review is extracted into a structured, flat JSON object. Example:

```json
{
  "id": "6a4143f0de4c62b2f3da9f64",
  "companyName": "Apify",
  "companyId": "62ac9c3177fbadc00785d7fe",
  "companyDomain": "apify.com",
  "title": "I love Apify for content scraping and…",
  "text": "I love Apify for content scraping and skip tracing! an incredibly simple user interface with a ton of prebuilt scraping tools to find all the data and content you could ever need. Extremely affordable and great support anytime you need it. Highly recommended to any SaaS builder, vibe coder or small business owner needing quality data.",
  "rating": 5,
  "likes": 0,
  "language": "en",
  "publishedDate": "2026-06-28T17:55:28.000Z",
  "experiencedDate": "2026-06-22T00:00:00.000Z",
  "updatedDate": null,
  "authorName": "Heck",
  "authorId": "62e14ab679b7c7001345ca1c",
  "authorCountry": "US",
  "authorReviewsCount": 5,
  "authorIsVerified": true,
  "isVerified": true,
  "replyText": "Hi Heck, thank you so much for the feedback! We are thrilled to hear you enjoy using Apify.",
  "replyDate": "2026-06-28T18:10:00.000Z"
}
```

---

## 🚀 Get Started

1. Enter the target domain name in the input box (e.g., `apify.com`).
2. Adjust `maxPages` to select how many pages to scrape (each page contains 20 reviews).
3. Toggle proxy configuration (enabled by default) to ensure smooth bypass of rate limits.
4. Click **Start** to run the scraper and download your data in JSON, CSV, or Excel!
