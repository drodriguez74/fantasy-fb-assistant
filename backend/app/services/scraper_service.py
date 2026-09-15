from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class FantasyContentScraper:
    """Player-news lookup used by content_generation_service.py's
    player_analysis content type.

    Historical note: this used to also scrape waiver-wire/trending content
    from FantasyPros/ESPN/NFL.com for a `/blog/*` router, and fabricated a
    canned player-news article and a hardcoded "trending" topic when real
    scraping wasn't implemented (fixed in f791d8a, 2026-08-23 -- presenting
    made-up content as real news/trends was worse than admitting we don't
    have it). Removed 2026-09-15: the `/blog/*` router and its
    waiver-wire/trending scrapes were dead code, unreachable from the
    frontend (which only ever called `/content/*`), and the underlying
    scrape targets were confirmed dead too (fantasypros.com/nfl/waiver-wire/
    -> 404, nfl.com/fantasy/ -> permanent redirect) -- kept only the
    still-live `scrape_player_news` path.
    """

    async def scrape_player_news(self, player_name: str) -> List[Dict[str, Any]]:
        """Look up recent news for a specific player.

        NOT IMPLEMENTED: there is no real per-source search integration wired
        up here (no real HTTP call to any source's search functionality).
        Honestly returns no results instead of fabricating a canned article.
        Replace with a real search/RSS integration before re-enabling.
        """
        logger.warning(
            "scrape_player_news(%s): real search is not implemented; "
            "returning no results instead of fabricated data",
            player_name,
        )
        return []


scraper_service = FantasyContentScraper()
