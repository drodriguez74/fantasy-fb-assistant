from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from app.api.deps import get_db, get_current_active_user
from app.models.user import User
from app.models.blog_post import BlogPost
from app.services.content_generation_service import ContentGenerationService, ContentType
import json

router = APIRouter()


class ContentGenerationRequest(BaseModel):
    content_type: str
    topic: str
    parameters: Optional[Dict[str, Any]] = {}


class ContentPublishRequest(BaseModel):
    blog_post_id: int
    is_published: bool = True
    featured: bool = False


@router.post("/generate")
async def generate_content(
    request: ContentGenerationRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Generate AI-powered fantasy content with multi-perspective analysis"""
    try:
        content_service = ContentGenerationService(db)
        
        # Validate content type (validate against the values, not the class attributes)
        valid_types = [
            "weekly_rankings",
            "player_analysis", 
            "waiver_wire",
            "start_sit",
            "trade_analysis",
            "injury_report",
            "breakout_candidates",
            "draft_strategy",
            "matchup_analysis",
            "season_recap"
        ]
        
        if request.content_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid content type. Must be one of: {', '.join(valid_types)}"
            )
        
        # Generate content
        result = await content_service.generate_content(
            content_type=request.content_type,
            topic=request.topic,
            parameters=request.parameters
        )
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Content generation failed: {str(e)}")


@router.post("/generate-and-save")
async def generate_and_save_content(
    request: ContentGenerationRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Generate content and automatically save as blog post"""
    try:
        content_service = ContentGenerationService(db)
        
        # Generate content
        result = await content_service.generate_content(
            content_type=request.content_type,
            topic=request.topic,
            parameters=request.parameters
        )
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        # Save content as blog post
        save_result = await content_service.save_generated_content(result)
        
        if "error" in save_result:
            raise HTTPException(status_code=500, detail=save_result["error"])
        
        return {
            "content_generated": True,
            "content_saved": True,
            "blog_post_id": save_result["blog_post_id"],
            "title": result["title"],
            "content_type": result["content_type"],
            "metadata": result.get("metadata", {})
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Content generation and save failed: {str(e)}")


@router.get("/templates")
async def get_content_templates():
    """Get available content generation templates"""
    templates = {
        ContentType.WEEKLY_RANKINGS: {
            "name": "Weekly Rankings",
            "description": "Position-specific weekly fantasy rankings with expert analysis",
            "parameters": {
                "week": {"type": "integer", "description": "NFL week number", "default": 1},
                "position": {"type": "string", "description": "Position (QB, RB, WR, TE, ALL)", "default": "ALL"}
            }
        },
        ContentType.PLAYER_ANALYSIS: {
            "name": "Player Deep Dive",
            "description": "Comprehensive individual player analysis with multi-angle insights",
            "parameters": {
                "player_name": {"type": "string", "description": "Player full name"},
                "player_id": {"type": "integer", "description": "Player database ID (alternative to name)"}
            }
        },
        ContentType.WAIVER_WIRE: {
            "name": "Waiver Wire Targets",
            "description": "Weekly waiver wire pickup recommendations with priority rankings",
            "parameters": {
                "week": {"type": "integer", "description": "NFL week number", "default": 1}
            }
        },
        ContentType.INJURY_REPORT: {
            "name": "Injury Report",
            "description": "Comprehensive injury analysis with fantasy impact assessment",
            "parameters": {}
        },
        ContentType.START_SIT: {
            "name": "Start/Sit Recommendations", 
            "description": "Weekly start/sit advice for lineup decisions",
            "parameters": {
                "week": {"type": "integer", "description": "NFL week number", "default": 1},
                "position": {"type": "string", "description": "Position focus", "default": "ALL"}
            }
        },
        ContentType.BREAKOUT_CANDIDATES: {
            "name": "Breakout Candidates",
            "description": "Players positioned for breakout performances",
            "parameters": {
                "timeframe": {"type": "string", "description": "Analysis timeframe (weekly, rest_of_season)", "default": "weekly"}
            }
        },
        ContentType.DRAFT_STRATEGY: {
            "name": "Draft Strategy Guide",
            "description": "Strategic draft guidance and player value analysis", 
            "parameters": {
                "draft_type": {"type": "string", "description": "Draft type (redraft, dynasty, keeper)", "default": "redraft"},
                "league_size": {"type": "integer", "description": "League size", "default": 12}
            }
        }
    }
    
    return {
        "templates": templates,
        "total_templates": len(templates)
    }


@router.get("/blog-posts/")
async def get_generated_blog_posts(
    limit: int = Query(20, description="Number of posts to return"),
    category: Optional[str] = Query(None, description="Filter by category"),
    published_only: bool = Query(True, description="Show only published posts"),
    db: Session = Depends(get_db)
):
    """Get generated blog posts"""
    try:
        from sqlalchemy.exc import OperationalError
        
        # Check if the blog_posts table exists
        try:
            query = db.query(BlogPost)
            
            if published_only:
                query = query.filter(BlogPost.is_published == True)
                
            if category:
                query = query.filter(BlogPost.category == category)
            
            posts = query.order_by(BlogPost.created_at.desc()).limit(limit).all()
        except OperationalError:
            # Table doesn't exist yet, return empty result
            return {
                "blog_posts": [],
                "total": 0,
                "message": "Blog posts table not created yet"
            }
        
        posts_data = []
        for post in posts:
            post_dict = {
                "id": post.id,
                "title": post.title,
                "content": post.content[:500] + "..." if len(post.content) > 500 else post.content,
                "author": getattr(post, 'author', 'AI Assistant'),  # Default author if field missing
                "category": post.category or "general",
                "is_published": post.is_published,
                "featured": getattr(post, 'featured', False),  # Default featured if field missing
                "created_at": post.created_at.isoformat() if post.created_at else None,
                "updated_at": post.updated_at.isoformat() if post.updated_at else None,
                "tags": json.loads(post.tags) if post.tags and post.tags.startswith('{') else (post.tags.split(',') if post.tags else [])
            }
            posts_data.append(post_dict)
        
        return {
            "blog_posts": posts_data,
            "total": len(posts_data)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get blog posts: {str(e)}")


@router.get("/blog-posts/{post_id}")
async def get_blog_post(
    post_id: int,
    db: Session = Depends(get_db)
):
    """Get specific blog post by ID"""
    try:
        post = db.query(BlogPost).filter(BlogPost.id == post_id).first()
        
        if not post:
            raise HTTPException(status_code=404, detail="Blog post not found")
        
        return {
            "id": post.id,
            "title": post.title,
            "content": post.content,
            "author": post.author,
            "category": post.category,
            "is_published": post.is_published,
            "featured": post.featured,
            "created_at": post.created_at.isoformat(),
            "updated_at": post.updated_at.isoformat() if post.updated_at else None,
            "tags": json.loads(post.tags) if post.tags else {}
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get blog post: {str(e)}")


@router.put("/blog-posts/{post_id}/publish")
async def publish_blog_post(
    post_id: int,
    request: ContentPublishRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Publish or unpublish a blog post"""
    try:
        post = db.query(BlogPost).filter(BlogPost.id == post_id).first()
        
        if not post:
            raise HTTPException(status_code=404, detail="Blog post not found")
        
        post.is_published = request.is_published
        post.featured = request.featured
        post.updated_at = datetime.utcnow()
        
        db.commit()
        
        return {
            "success": True,
            "blog_post_id": post.id,
            "is_published": post.is_published,
            "featured": post.featured,
            "updated_at": post.updated_at.isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update blog post: {str(e)}")


@router.delete("/blog-posts/{post_id}")
async def delete_blog_post(
    post_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a blog post"""
    try:
        post = db.query(BlogPost).filter(BlogPost.id == post_id).first()
        
        if not post:
            raise HTTPException(status_code=404, detail="Blog post not found")
        
        db.delete(post)
        db.commit()
        
        return {
            "success": True,
            "message": f"Blog post '{post.title}' deleted successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete blog post: {str(e)}")


@router.post("/weekly-rankings")
async def generate_weekly_rankings(
    week: int = Query(..., description="NFL week number"),
    position: str = Query("ALL", description="Position (QB, RB, WR, TE, ALL)"),
    save_as_post: bool = Query(True, description="Save as blog post"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Quick endpoint for generating weekly rankings"""
    try:
        content_service = ContentGenerationService(db)
        
        result = await content_service.generate_content(
            content_type=ContentType.WEEKLY_RANKINGS,
            topic=f"Week {week} {position} Rankings",
            parameters={"week": week, "position": position}
        )
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        if save_as_post:
            save_result = await content_service.save_generated_content(result)
            result["blog_post_id"] = save_result.get("blog_post_id")
            result["saved"] = save_result.get("success", False)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate weekly rankings: {str(e)}")


@router.post("/waiver-wire")
async def generate_waiver_wire_content(
    week: int = Query(..., description="NFL week number"),
    save_as_post: bool = Query(True, description="Save as blog post"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Quick endpoint for generating waiver wire content"""
    try:
        content_service = ContentGenerationService(db)
        
        result = await content_service.generate_content(
            content_type=ContentType.WAIVER_WIRE,
            topic=f"Week {week} Waiver Wire",
            parameters={"week": week}
        )
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        if save_as_post:
            save_result = await content_service.save_generated_content(result)
            result["blog_post_id"] = save_result.get("blog_post_id")
            result["saved"] = save_result.get("success", False)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate waiver wire content: {str(e)}")


@router.post("/injury-report")
async def generate_injury_report(
    save_as_post: bool = Query(True, description="Save as blog post"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Quick endpoint for generating injury report"""
    try:
        content_service = ContentGenerationService(db)
        
        result = await content_service.generate_content(
            content_type=ContentType.INJURY_REPORT,
            topic="Weekly Fantasy Injury Report",
            parameters={}
        )
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        if save_as_post:
            save_result = await content_service.save_generated_content(result)
            result["blog_post_id"] = save_result.get("blog_post_id")
            result["saved"] = save_result.get("success", False)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate injury report: {str(e)}")


@router.get("/content-stats")
async def get_content_statistics(
    days: int = Query(30, description="Days to look back for stats"),
    db: Session = Depends(get_db)
):
    """Get content generation statistics"""
    try:
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Total posts
        total_posts = db.query(BlogPost).filter(BlogPost.created_at >= cutoff_date).count()
        
        # Published posts
        published_posts = db.query(BlogPost).filter(
            BlogPost.created_at >= cutoff_date,
            BlogPost.is_published == True
        ).count()
        
        # Posts by category
        category_stats = {}
        posts_by_category = db.query(BlogPost.category, db.func.count(BlogPost.id)).filter(
            BlogPost.created_at >= cutoff_date
        ).group_by(BlogPost.category).all()
        
        for category, count in posts_by_category:
            category_stats[category] = count
        
        # Recent posts
        recent_posts = db.query(BlogPost).filter(
            BlogPost.created_at >= cutoff_date
        ).order_by(BlogPost.created_at.desc()).limit(5).all()
        
        recent_posts_data = []
        for post in recent_posts:
            recent_posts_data.append({
                "id": post.id,
                "title": post.title,
                "category": post.category,
                "is_published": post.is_published,
                "created_at": post.created_at.isoformat()
            })
        
        return {
            "period_days": days,
            "total_posts": total_posts,
            "published_posts": published_posts,
            "draft_posts": total_posts - published_posts,
            "category_breakdown": category_stats,
            "recent_posts": recent_posts_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get content statistics: {str(e)}")