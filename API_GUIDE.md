# Fantasy Football Assistant API Guide

## Overview

The Fantasy Football Assistant API provides AI-powered fantasy football analysis, multi-perspective content generation, and platform integration capabilities.

**Base URL:** `http://localhost:8000/api/v1`

## Authentication

Currently, the API is open for development. Authentication will be added in future versions.

## Core Features

### 1. AI-Powered Content Generation

#### Generate Waiver Wire Post
```http
GET /blog/waiver-wire/{week}?league_id={optional_sleeper_league_id}
```

**Example:**
```bash
curl "http://localhost:8000/api/v1/blog/waiver-wire/12?league_id=123456789"
```

**Response:**
```json
{
  "title": "Week 12 Waiver Wire: Multi-Perspective Analysis",
  "content": "# Week 12 Waiver Wire Analysis...",
  "perspectives": [
    {
      "perspective": "Conservative/Risk-Averse",
      "analysis": "Analysis from conservative viewpoint..."
    }
  ],
  "consensus": {
    "consensus_recommendation": "Main recommendation",
    "confidence_score": 8,
    "key_agreements": ["point 1", "point 2"],
    "risk_factors": ["risk 1", "risk 2"]
  }
}
```

#### Generate Player Spotlight
```http
GET /blog/player-spotlight/{player_name}
```

**Example:**
```bash
curl "http://localhost:8000/api/v1/blog/player-spotlight/Christian McCaffrey"
```

#### Generate Position Rankings
```http
GET /blog/rankings/{position}/week/{week}
```

**Example:**
```bash
curl "http://localhost:8000/api/v1/blog/rankings/RB/week/12"
```

### 2. Player Data & Analysis

#### Get All Players
```http
GET /players?position={optional}&limit={number}
```

**Parameters:**
- `position`: Filter by position (QB, RB, WR, TE, K, DEF)
- `limit`: Number of players to return (default: 50)

#### Get Trending Players
```http
GET /players/trending?trend_type={add|drop}&hours={24}&limit={25}
```

#### Get Player Details
```http
GET /players/{sleeper_player_id}
```

**Response includes:**
- Player data from Sleeper
- Season stats
- AI-generated analysis
- Recent news articles

#### Search Players
```http
GET /players/search/{player_name}
```

### 3. Draft Assistant

#### Get Draft Recommendations
```http
POST /draft/recommendations
```

**Request Body:**
```json
{
  "available_players": [
    {"name": "Player Name", "position": "RB", "team": "SF"}
  ],
  "team_needs": ["RB", "WR"],
  "draft_position": 5,
  "scoring_format": "PPR",
  "league_size": 12
}
```

#### Get Trending Draft Candidates
```http
GET /draft/trending-candidates?hours={48}&limit={50}
```

#### Get Positional Rankings
```http
GET /draft/positional-rankings/{position}?limit={30}
```

#### Analyze League for Draft
```http
GET /draft/league-analysis/{sleeper_league_id}
```

### 4. Content Sources

#### Get Trending Topics
```http
GET /blog/trending-topics
```

#### Get Content Sources
```http
GET /blog/content-sources
```

## Multi-Perspective Analysis

The system generates content from 5 different perspectives:

1. **Conservative/Risk-Averse**: Safe picks with proven track records
2. **Aggressive/High-Upside**: High-risk, high-reward players
3. **Data-Driven/Analytics**: Statistical analysis and advanced metrics
4. **Situational/Matchup-Based**: Game script and matchup considerations
5. **Long-term/Dynasty**: Future value and career trajectory

## Consensus Algorithm

The AI combines all perspectives to generate:
- **Consensus Recommendation**: Balanced advice synthesis
- **Confidence Score**: 1-10 rating of recommendation strength
- **Key Agreements**: Points where all perspectives align
- **Key Disagreements**: Areas of analytical conflict
- **Risk Factors**: Potential concerns to monitor
- **Action Items**: Specific steps to take

## Platform Integration

### Sleeper API Integration

The system integrates with Sleeper for:
- Player data and stats
- League analysis
- Trending player data
- Waiver wire candidates
- Real-time projections

## AI Services

Supports both OpenAI and Anthropic APIs:
- **OpenAI GPT-4**: Primary content generation
- **Anthropic Claude**: Alternative AI provider
- Automatic fallback between providers

## Error Handling

All endpoints return structured error responses:

```json
{
  "detail": "Error description",
  "status_code": 400
}
```

Common status codes:
- `400`: Bad Request (invalid parameters)
- `404`: Not Found (player/league not found)
- `500`: Internal Server Error (API failures, processing errors)

## Rate Limiting

- AI API calls are rate limited to prevent quota exhaustion
- Sleeper API calls include delays to respect rate limits
- Web scraping includes delays between requests

## Development Setup

1. **Start Services:**
   ```bash
   docker-compose up -d
   ```

2. **Access API:**
   - API: http://localhost:8000
   - Docs: http://localhost:8000/docs
   - Frontend: http://localhost:3000

3. **Environment Variables:**
   Set API keys in `backend/.env`:
   ```
   OPENAI_API_KEY=your_key
   ANTHROPIC_API_KEY=your_key
   ```

## Background Tasks

Celery tasks for automated content generation:
- Weekly waiver wire posts
- Player spotlight articles
- Content source scraping
- Data synchronization

## Future Enhancements

- ESPN and Yahoo API integration
- Real-time draft room functionality
- User authentication and personalization
- Mobile app API endpoints
- Webhook support for league updates