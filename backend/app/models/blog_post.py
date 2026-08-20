from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base


class BlogPost(Base):
    __tablename__ = "blog_posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    content = Column(Text, nullable=False)
    summary = Column(Text)
    
    # AI-generated content metadata
    source_urls = Column(Text)  # JSON array of source URLs
    perspectives_count = Column(Integer, default=5)
    consensus_score = Column(Integer)  # 1-10 confidence in consensus
    
    # SEO and categorization
    tags = Column(String)  # Comma-separated tags
    category = Column(String)  # waiver_wire, draft, rankings, news
    
    # Publication status
    is_published = Column(Boolean, default=False)
    featured = Column(Boolean, default=False)
    publish_date = Column(DateTime(timezone=True))
    
    # Authorship (for AI tracking)
    author = Column(String, default="AI Assistant")
    created_by_ai = Column(Boolean, default=True)
    ai_model_used = Column(String)  # e.g., "gpt-4", "claude-3"
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())