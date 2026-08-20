import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
import asyncio
from datetime import datetime, timedelta
import re
from urllib.parse import urljoin, urlparse


class FantasyContentScraper:
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        )
        
        # Fantasy football content sources
        self.sources = {
            "fantasypros": {
                "base_url": "https://www.fantasypros.com",
                "waiver_url": "/nfl/waiver-wire/",
                "rankings_url": "/nfl/rankings/",
                "news_url": "/nfl/news/"
            },
            "espn": {
                "base_url": "https://www.espn.com",
                "fantasy_url": "/fantasy/football/",
                "news_url": "/nfl/news/"
            },
            "nfl": {
                "base_url": "https://www.nfl.com",
                "fantasy_url": "/fantasy/",
                "news_url": "/news/"
            }
        }

    async def scrape_waiver_wire_content(self) -> List[Dict[str, Any]]:
        """Scrape waiver wire content from multiple sources"""
        articles = []
        
        try:
            # FantasyPros waiver wire
            fp_articles = await self._scrape_fantasypros_waiver()
            articles.extend(fp_articles)
            
            # Add delay between requests
            await asyncio.sleep(1)
            
            # ESPN fantasy content
            espn_articles = await self._scrape_espn_fantasy()
            articles.extend(espn_articles)
            
            await asyncio.sleep(1)
            
            # NFL.com fantasy content
            nfl_articles = await self._scrape_nfl_fantasy()
            articles.extend(nfl_articles)
            
        except Exception as e:
            print(f"Error scraping waiver wire content: {str(e)}")
        
        return articles

    async def scrape_player_news(self, player_name: str) -> List[Dict[str, Any]]:
        """Scrape news articles about a specific player"""
        articles = []
        
        try:
            # Search multiple sources for player-specific news
            sources_to_search = ["fantasypros", "espn", "nfl"]
            
            for source in sources_to_search:
                source_articles = await self._search_player_news(source, player_name)
                articles.extend(source_articles)
                await asyncio.sleep(0.5)  # Rate limiting
                
        except Exception as e:
            print(f"Error scraping player news for {player_name}: {str(e)}")
        
        return articles

    async def scrape_trending_topics(self) -> List[Dict[str, Any]]:
        """Scrape trending fantasy football topics"""
        topics = []
        
        try:
            # Get trending content from multiple sources
            fp_topics = await self._scrape_fantasypros_trending()
            topics.extend(fp_topics)
            
            await asyncio.sleep(1)
            
            espn_topics = await self._scrape_espn_trending()
            topics.extend(espn_topics)
            
        except Exception as e:
            print(f"Error scraping trending topics: {str(e)}")
        
        return topics

    async def _scrape_fantasypros_waiver(self) -> List[Dict[str, Any]]:
        """Scrape FantasyPros waiver wire content"""
        articles = []
        try:
            url = self.sources["fantasypros"]["base_url"] + self.sources["fantasypros"]["waiver_url"]
            response = await self.client.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find waiver wire articles
            article_elements = soup.find_all('article', class_='post')
            
            for article in article_elements[:5]:  # Limit to 5 articles
                title_elem = article.find('h2') or article.find('h3')
                content_elem = article.find('div', class_='post-content') or article.find('p')
                
                if title_elem and content_elem:
                    articles.append({
                        "source": "FantasyPros",
                        "title": title_elem.get_text(strip=True),
                        "content": content_elem.get_text(strip=True)[:500],
                        "url": url,
                        "scraped_at": datetime.now().isoformat(),
                        "category": "waiver_wire"
                    })
                    
        except Exception as e:
            print(f"Error scraping FantasyPros: {str(e)}")
        
        return articles

    async def _scrape_espn_fantasy(self) -> List[Dict[str, Any]]:
        """Scrape ESPN fantasy content"""
        articles = []
        try:
            url = self.sources["espn"]["base_url"] + self.sources["espn"]["fantasy_url"]
            response = await self.client.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find fantasy articles
            article_elements = soup.find_all('section', class_='contentItem')
            
            for article in article_elements[:3]:  # Limit to 3 articles
                title_elem = article.find('h1') or article.find('h2')
                content_elem = article.find('p')
                
                if title_elem and content_elem:
                    articles.append({
                        "source": "ESPN Fantasy",
                        "title": title_elem.get_text(strip=True),
                        "content": content_elem.get_text(strip=True)[:500],
                        "url": url,
                        "scraped_at": datetime.now().isoformat(),
                        "category": "fantasy_analysis"
                    })
                    
        except Exception as e:
            print(f"Error scraping ESPN: {str(e)}")
        
        return articles

    async def _scrape_nfl_fantasy(self) -> List[Dict[str, Any]]:
        """Scrape NFL.com fantasy content"""
        articles = []
        try:
            url = self.sources["nfl"]["base_url"] + self.sources["nfl"]["fantasy_url"]
            response = await self.client.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find fantasy articles
            article_elements = soup.find_all('article')
            
            for article in article_elements[:3]:  # Limit to 3 articles
                title_elem = article.find('h3') or article.find('h2')
                content_elem = article.find('p')
                
                if title_elem and content_elem:
                    articles.append({
                        "source": "NFL.com",
                        "title": title_elem.get_text(strip=True),
                        "content": content_elem.get_text(strip=True)[:500],
                        "url": url,
                        "scraped_at": datetime.now().isoformat(),
                        "category": "fantasy_news"
                    })
                    
        except Exception as e:
            print(f"Error scraping NFL.com: {str(e)}")
        
        return articles

    async def _search_player_news(self, source: str, player_name: str) -> List[Dict[str, Any]]:
        """Search for player-specific news from a source"""
        articles = []
        try:
            # This would typically involve using the site's search functionality
            # For now, we'll return mock data structure
            search_query = player_name.replace(" ", "+")
            
            # Mock implementation - in reality, you'd search each site
            articles.append({
                "source": source.title(),
                "title": f"Latest news on {player_name}",
                "content": f"Recent updates and analysis for {player_name}...",
                "url": f"https://example.com/search?q={search_query}",
                "scraped_at": datetime.now().isoformat(),
                "category": "player_news",
                "player": player_name
            })
            
        except Exception as e:
            print(f"Error searching {source} for {player_name}: {str(e)}")
        
        return articles

    async def _scrape_fantasypros_trending(self) -> List[Dict[str, Any]]:
        """Scrape trending topics from FantasyPros"""
        topics = []
        try:
            # Mock implementation for trending topics
            topics.append({
                "source": "FantasyPros",
                "topic": "Waiver Wire Pickups Week 12",
                "description": "Top waiver wire targets for the upcoming week",
                "url": "https://fantasypros.com/trending",
                "scraped_at": datetime.now().isoformat(),
                "trend_score": 85
            })
            
        except Exception as e:
            print(f"Error scraping FantasyPros trending: {str(e)}")
        
        return topics

    async def _scrape_espn_trending(self) -> List[Dict[str, Any]]:
        """Scrape trending topics from ESPN"""
        topics = []
        try:
            # Mock implementation for trending topics
            topics.append({
                "source": "ESPN",
                "topic": "NFL Playoff Race Impact on Fantasy",
                "description": "How playoff implications affect fantasy relevance",
                "url": "https://espn.com/fantasy/trending",
                "scraped_at": datetime.now().isoformat(),
                "trend_score": 78
            })
            
        except Exception as e:
            print(f"Error scraping ESPN trending: {str(e)}")
        
        return topics

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


scraper_service = FantasyContentScraper()