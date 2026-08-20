from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio
import json
from app.services.ai_service import ai_service
from app.services.scraper_service import scraper_service
from app.services.sleeper_service import sleeper_service
from app.models.blog_post import BlogPost
from app.db.base import SessionLocal
from sqlalchemy.orm import Session
import uuid


class ContentGenerationService:
    def __init__(self):
        self.perspectives = [
            "Conservative/Risk-Averse",
            "Aggressive/High-Upside", 
            "Data-Driven/Analytics",
            "Situational/Matchup-Based",
            "Long-term/Dynasty"
        ]

    async def generate_waiver_wire_post(self, week: int, league_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate a comprehensive waiver wire post with multiple perspectives"""
        try:
            # 1. Gather source data
            source_articles = await scraper_service.scrape_waiver_wire_content()
            
            if league_id:
                waiver_candidates = await sleeper_service.get_waiver_candidates(league_id)
            else:
                trending = await sleeper_service.get_trending_players("add", 24, 15)
                waiver_candidates = trending
            
            # 2. Generate multi-perspective analysis
            topic = f"Week {week} Waiver Wire Pickups"
            
            perspective_analyses = await ai_service.generate_multi_perspective_content(
                topic=topic,
                source_articles=source_articles,
                perspectives=self.perspectives
            )
            
            # 3. Generate consensus recommendation
            consensus = await ai_service.generate_consensus_recommendation(
                topic=topic,
                perspective_analyses=perspective_analyses["perspectives"]
            )
            
            # 4. Create final post content
            post_content = await self._format_waiver_post(
                week=week,
                perspectives=perspective_analyses["perspectives"],
                consensus=consensus,
                candidates=waiver_candidates[:10],  # Top 10 candidates
                sources=source_articles
            )
            
            return {
                "title": f"Week {week} Waiver Wire: Multi-Perspective Analysis",
                "content": post_content,
                "perspectives": perspective_analyses["perspectives"],
                "consensus": consensus,
                "candidates": waiver_candidates[:10],
                "sources": [{"title": a.get("title", ""), "url": a.get("url", "")} for a in source_articles]
            }
            
        except Exception as e:
            return {"error": f"Failed to generate waiver wire post: {str(e)}"}

    async def generate_player_spotlight(self, player_name: str) -> Dict[str, Any]:
        """Generate a multi-perspective player analysis"""
        try:
            # 1. Gather player data
            all_players = await sleeper_service.get_all_players()
            player_data = None
            
            # Find player in Sleeper data
            for player_id, player in all_players.items():
                if isinstance(player, dict) and player.get("full_name", "").lower() == player_name.lower():
                    player_data = player
                    break
            
            if not player_data:
                return {"error": f"Player {player_name} not found"}
            
            # 2. Get player news
            news_articles = await scraper_service.scrape_player_news(player_name)
            
            # 3. Generate multi-perspective analysis
            topic = f"{player_name} Fantasy Analysis"
            
            perspective_analyses = await ai_service.generate_multi_perspective_content(
                topic=topic,
                source_articles=news_articles,
                perspectives=self.perspectives
            )
            
            # 4. Generate consensus
            consensus = await ai_service.generate_consensus_recommendation(
                topic=topic,
                perspective_analyses=perspective_analyses["perspectives"]
            )
            
            # 5. Format final content
            post_content = await self._format_player_spotlight(
                player_name=player_name,
                player_data=player_data,
                perspectives=perspective_analyses["perspectives"],
                consensus=consensus,
                news=news_articles
            )
            
            return {
                "title": f"{player_name}: Multi-Perspective Fantasy Analysis",
                "content": post_content,
                "perspectives": perspective_analyses["perspectives"],
                "consensus": consensus,
                "player_data": player_data,
                "news": news_articles
            }
            
        except Exception as e:
            return {"error": f"Failed to generate player spotlight: {str(e)}"}

    async def generate_weekly_rankings_post(self, position: str, week: int) -> Dict[str, Any]:
        """Generate position-specific rankings with multiple perspectives"""
        try:
            # 1. Get projections and trending data
            projections = await sleeper_service.get_player_projections(week)
            trending = await sleeper_service.get_trending_players("add", 48, 20)
            
            # 2. Scrape rankings content
            source_articles = await scraper_service.scrape_waiver_wire_content()
            
            # 3. Generate perspectives
            topic = f"Week {week} {position} Rankings"
            
            perspective_analyses = await ai_service.generate_multi_perspective_content(
                topic=topic,
                source_articles=source_articles,
                perspectives=self.perspectives
            )
            
            # 4. Generate consensus
            consensus = await ai_service.generate_consensus_recommendation(
                topic=topic,
                perspective_analyses=perspective_analyses["perspectives"]
            )
            
            # 5. Format content
            post_content = await self._format_rankings_post(
                position=position,
                week=week,
                perspectives=perspective_analyses["perspectives"],
                consensus=consensus,
                projections=projections,
                trending=trending
            )
            
            return {
                "title": f"Week {week} {position} Rankings: Consensus Analysis",
                "content": post_content,
                "perspectives": perspective_analyses["perspectives"],
                "consensus": consensus
            }
            
        except Exception as e:
            return {"error": f"Failed to generate rankings post: {str(e)}"}

    async def save_blog_post(self, post_data: Dict[str, Any], category: str = "waiver_wire") -> Optional[BlogPost]:
        """Save generated content as a blog post"""
        try:
            db = SessionLocal()
            
            # Generate slug from title
            slug = post_data["title"].lower().replace(" ", "-").replace(":", "")
            slug = "".join(c for c in slug if c.isalnum() or c == "-")
            
            blog_post = BlogPost(
                title=post_data["title"],
                slug=f"{slug}-{uuid.uuid4().hex[:8]}",
                content=post_data["content"],
                summary=post_data.get("consensus", {}).get("consensus_recommendation", "")[:200],
                source_urls=json.dumps([s["url"] for s in post_data.get("sources", [])]),
                perspectives_count=len(post_data.get("perspectives", [])),
                consensus_score=post_data.get("consensus", {}).get("confidence_score", 5),
                category=category,
                is_published=False,
                created_by_ai=True,
                ai_model_used="gpt-4"
            )
            
            db.add(blog_post)
            db.commit()
            db.refresh(blog_post)
            db.close()
            
            return blog_post
            
        except Exception as e:
            print(f"Error saving blog post: {str(e)}")
            return None

    async def _format_waiver_post(self, week: int, perspectives: List[Dict], 
                                  consensus: Dict, candidates: List[Dict], 
                                  sources: List[Dict]) -> str:
        """Format waiver wire post content"""
        content = f"""# Week {week} Waiver Wire: Multi-Perspective Analysis

## Executive Summary
{consensus.get('consensus_recommendation', 'Analysis in progress...')}

**Confidence Score:** {consensus.get('confidence_score', 'N/A')}/10

## Top Waiver Wire Candidates

"""
        
        # Add top candidates
        for i, candidate in enumerate(candidates[:5], 1):
            if isinstance(candidate, dict):
                player_id = candidate.get('player_id', 'Unknown')
                content += f"{i}. **Player ID {player_id}** - Trending with {candidate.get('count', 0)} adds\n"
        
        content += "\n## Multi-Perspective Analysis\n\n"
        
        # Add each perspective
        for perspective in perspectives:
            content += f"### {perspective['perspective']}\n{perspective['analysis']}\n\n"
        
        content += "## Key Takeaways\n\n"
        
        # Add consensus points
        for agreement in consensus.get('key_agreements', []):
            content += f"✅ {agreement}\n"
        
        content += "\n## Risk Factors\n\n"
        
        for risk in consensus.get('risk_factors', []):
            content += f"⚠️ {risk}\n"
        
        content += f"\n---\n*Analysis generated on {datetime.now().strftime('%Y-%m-%d %H:%M')} using multiple data sources and AI perspectives.*"
        
        return content

    async def _format_player_spotlight(self, player_name: str, player_data: Dict,
                                       perspectives: List[Dict], consensus: Dict,
                                       news: List[Dict]) -> str:
        """Format player spotlight content"""
        content = f"""# {player_name}: Multi-Perspective Fantasy Analysis

## Player Overview
**Position:** {player_data.get('position', 'N/A')}
**Team:** {player_data.get('team', 'N/A')}
**Experience:** {player_data.get('years_exp', 'N/A')} years

## Consensus Recommendation
{consensus.get('consensus_recommendation', 'Analysis in progress...')}

**Confidence Score:** {consensus.get('confidence_score', 'N/A')}/10

## Multi-Perspective Analysis

"""
        
        # Add each perspective
        for perspective in perspectives:
            content += f"### {perspective['perspective']}\n{perspective['analysis']}\n\n"
        
        content += "## Key Insights\n\n"
        
        for agreement in consensus.get('key_agreements', []):
            content += f"✅ {agreement}\n"
        
        content += "\n## Areas of Disagreement\n\n"
        
        for disagreement in consensus.get('key_disagreements', []):
            content += f"🤔 {disagreement}\n"
        
        content += f"\n---\n*Analysis generated on {datetime.now().strftime('%Y-%m-%d %H:%M')} using multiple data sources and AI perspectives.*"
        
        return content

    async def _format_rankings_post(self, position: str, week: int, perspectives: List[Dict],
                                    consensus: Dict, projections: Dict, trending: List[Dict]) -> str:
        """Format rankings post content"""
        content = f"""# Week {week} {position} Rankings: Consensus Analysis

## Executive Summary
{consensus.get('consensus_recommendation', 'Analysis in progress...')}

**Confidence Score:** {consensus.get('confidence_score', 'N/A')}/10

## Multi-Perspective Rankings Analysis

"""
        
        # Add each perspective
        for perspective in perspectives:
            content += f"### {perspective['perspective']}\n{perspective['analysis']}\n\n"
        
        content += "## Trending Players to Watch\n\n"
        
        # Add trending players
        for player in trending[:3]:
            if isinstance(player, dict):
                content += f"📈 Player ID: {player.get('player_id', 'Unknown')} - {player.get('count', 0)} adds\n"
        
        content += "\n## Consensus Recommendations\n\n"
        
        for action in consensus.get('action_items', []):
            content += f"🎯 {action}\n"
        
        content += f"\n---\n*Rankings generated on {datetime.now().strftime('%Y-%m-%d %H:%M')} using multiple data sources and AI perspectives.*"
        
        return content


content_service = ContentGenerationService()