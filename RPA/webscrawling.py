import requests
from bs4 import BeautifulSoup
import csv
import time
import re
from urllib.parse import urljoin, urlparse
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BBCNewsScraper:
    def __init__(self):
        self.base_url = "https://www.bbc.com"
        self.news_url = "https://www.bbc.com/news"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def get_page(self, url):
        """Fetch a web page with error handling"""
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def extract_top_stories(self):
        """Extract top news stories from BBC News homepage"""
        logger.info("Fetching BBC News homepage...")
        response = self.get_page(self.news_url)
        
        if not response:
            return []

        soup = BeautifulSoup(response.content, 'html.parser')
        articles = []

        # Look for various article selectors (BBC structure may vary)
        selectors = [
            'article[data-testid="card"]',
            'div[data-testid="card"]',
            '.nw-c-promo',
            '.gs-c-promo',
            'article'
        ]

        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                logger.info(f"Found {len(elements)} articles using selector: {selector}")
                break

        count = 0
        for element in elements[:15]:  # Get a few extra in case some fail
            if count >= 10:
                break

            article_data = self.extract_article_info(element)
            if article_data:
                articles.append(article_data)
                count += 1
                logger.info(f"Extracted article {count}: {article_data['title'][:50]}...")

        return articles

    def extract_article_info(self, element):
        """Extract article information from a card element"""
        try:
            # Try different selectors for title
            title_selectors = ['h2', 'h3', 'h1', '.gs-c-promo-heading__title', '[data-testid="card-headline"]']
            title = None
            
            for selector in title_selectors:
                title_elem = element.select_one(selector)
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    break

            if not title:
                return None

            # Try different selectors for link
            link_selectors = ['a[href]', 'h2 a', 'h3 a']
            link = None
            
            for selector in link_selectors:
                link_elem = element.select_one(selector)
                if link_elem and link_elem.get('href'):
                    link = link_elem['href']
                    if link.startswith('/'):
                        link = urljoin(self.base_url, link)
                    break

            if not link:
                return None

            # Try to get summary/description
            summary_selectors = ['p', '.gs-c-promo-summary', '[data-testid="card-description"]']
            summary = ""
            
            for selector in summary_selectors:
                summary_elem = element.select_one(selector)
                if summary_elem:
                    summary = summary_elem.get_text(strip=True)
                    break

            return {
                'title': title,
                'link': link,
                'summary': summary[:200] + "..." if len(summary) > 200 else summary,
                'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

        except Exception as e:
            logger.error(f"Error extracting article info: {e}")
            return None

    def get_full_article_content(self, url):
        """Fetch full article content for better summarization"""
        try:
            response = self.get_page(url)
            if not response:
                return ""

            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Common BBC article content selectors
            content_selectors = [
                '[data-component="text-block"]',
                '.story-body__inner p',
                'article p',
                '.ssrcss-7uxr49-RichTextContainer p'
            ]

            content_paragraphs = []
            
            for selector in content_selectors:
                paragraphs = soup.select(selector)
                if paragraphs:
                    content_paragraphs = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
                    break

            return " ".join(content_paragraphs[:5])  # First 5 paragraphs for summary
            
        except Exception as e:
            logger.error(f"Error getting full article content from {url}: {e}")
            return ""

    def generate_summary(self, title, existing_summary, full_content=""):
        """Generate a concise summary from available text"""
        # If we have a good existing summary, use it
        if existing_summary and len(existing_summary.strip()) > 50:
            return existing_summary

        # Otherwise, try to create summary from full content
        if full_content:
            sentences = re.split(r'[.!?]+', full_content)
            sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
            
            if sentences:
                # Take first 2-3 sentences as summary
                summary_sentences = sentences[:2] if len(sentences) >= 2 else sentences[:1]
                summary = ". ".join(summary_sentences)
                if summary and not summary.endswith('.'):
                    summary += "."
                return summary

        # Fallback to title-based summary
        return f"News article: {title}"

    def scrape_and_summarize(self):
        """Main method to scrape articles and generate summaries"""
        logger.info("Starting BBC News scraping...")
        
        articles = self.extract_top_stories()
        
        if not articles:
            logger.error("No articles found. The website structure may have changed.")
            return []

        logger.info(f"Processing {len(articles)} articles...")
        
        processed_articles = []
        
        for i, article in enumerate(articles, 1):
            logger.info(f"Processing article {i}/{len(articles)}: {article['title'][:50]}...")
            
            # Get full content for better summarization
            full_content = self.get_full_article_content(article['link'])
            
            # Generate enhanced summary
            enhanced_summary = self.generate_summary(
                article['title'], 
                article['summary'], 
                full_content
            )
            
            processed_article = {
                'rank': i,
                'title': article['title'],
                'summary': enhanced_summary,
                'link': article['link'],
                'scraped_at': article['scraped_at']
            }
            
            processed_articles.append(processed_article)
            
            # Be respectful to the server
            time.sleep(1)

        return processed_articles

    def save_to_csv(self, articles, filename="bbc_news_summary.csv"):
        """Save articles to CSV file"""
        if not articles:
            logger.warning("No articles to save.")
            return

        logger.info(f"Saving {len(articles)} articles to {filename}...")
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['rank', 'title', 'summary', 'link', 'scraped_at']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for article in articles:
                writer.writerow(article)
        
        logger.info(f"Successfully saved articles to {filename}")


def main():
    """Main function to run the scraper"""
    scraper = BBCNewsScraper()
    
    try:
        # Scrape and process articles
        articles = scraper.scrape_and_summarize()
        
        if articles:
            # Save to CSV
            filename = f"bbc_news_top10_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            scraper.save_to_csv(articles, filename)
            
            print(f"\n✅ Successfully scraped {len(articles)} articles!")
            print(f"📄 Results saved to: {filename}")
            print("\n📋 Summary:")
            print("-" * 60)
            
            for article in articles[:5]:  # Show first 5 articles
                print(f"{article['rank']}. {article['title']}")
                print(f"   Summary: {article['summary'][:100]}...")
                print(f"   Link: {article['link']}")
                print()
                
        else:
            print("❌ No articles were successfully scraped.")
            print("This might be due to changes in the BBC website structure.")
            
    except Exception as e:
        logger.error(f"An error occurred during scraping: {e}")
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
