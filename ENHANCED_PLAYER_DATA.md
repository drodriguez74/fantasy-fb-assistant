# Enhanced Player Data System

## Overview
The Enhanced Player Data System provides comprehensive player information with advanced analytics, injury tracking, usage metrics, and AI-powered insights for fantasy football analysis.

## Features

### Advanced Player Model
- **Basic Information**: Name, team, position, age, height, weight, college, experience
- **Fantasy Metrics**: Projections for PPR/Half-PPR/Standard, ADP, ownership percentage
- **Advanced Analytics**: Target share, air yards share, snap count percentage, carries share
- **Performance Tracking**: Season stats, last game stats, games played/started
- **Injury Tracking**: Detailed injury status, body part, notes, practice status
- **AI Analysis**: Enhanced AI insights with ceiling/floor scores, consistency ratings
- **Risk Assessment**: Automated risk level calculation (LOW/MEDIUM/HIGH)
- **Rankings & Tiers**: Position ranks, draft tiers, expert consensus rankings

### Enhanced Endpoints

#### Player Data Sync
```bash
POST /api/v1/players/sync
```
- Syncs player data from external sources (Sleeper API)
- Updates injury status, team changes, and stats
- Calculates advanced metrics automatically
- Requires authentication

#### Enhanced Player Search
```bash
GET /api/v1/players/enhanced/
```
**Parameters:**
- `position`: Filter by position (QB, RB, WR, TE, K, DEF)
- `team`: Filter by team abbreviation
- `injury_status`: Filter by injury status (HEALTHY, QUESTIONABLE, etc.)
- `min_projected_points`: Minimum projected points threshold
- `max_risk_level`: Maximum risk level (LOW, MEDIUM, HIGH)
- `limit`: Number of results (default: 50)

#### Trending Players
```bash
GET /api/v1/players/enhanced/trending/{direction}
```
**Parameters:**
- `direction`: UP or DOWN (trending adds vs drops)
- `limit`: Number of players (default: 20)

#### Injury Report
```bash
GET /api/v1/players/enhanced/injury-report
```
Returns comprehensive injury report with:
- Current injury status and body part
- Practice participation status
- Injury timeline and notes
- Fantasy impact assessment

#### Player Metrics Calculation
```bash
PUT /api/v1/players/enhanced/{player_id}/metrics
```
Calculates advanced metrics for a player:
- Ceiling/floor scores based on consistency
- Risk level based on injury history and age
- Tier assignment based on position rank
- Requires authentication

#### Enhanced AI Analysis
```bash
POST /api/v1/players/enhanced/{player_id}/analysis
```
Generates comprehensive AI analysis using:
- Enhanced player data context
- Recent performance trends
- Usage metrics and target share
- Injury considerations
- Rest of season outlook

#### Player Comparison
```bash
GET /api/v1/players/enhanced/comparison?player_ids=1,2,3
```
**Parameters:**
- `player_ids`: Comma-separated list of player IDs (max 5)

Returns side-by-side comparison with:
- All key metrics and projections
- Risk levels and injury status
- Advanced analytics comparison
- Season performance data

### Data Model Enhancements

#### Player Attributes
```json
{
  "id": 1,
  "name": "Josh Allen",
  "first_name": "Josh",
  "last_name": "Allen", 
  "team": "BUF",
  "position": "QB",
  "age": 28,
  "height": "6'5\"",
  "weight": 237,
  "college": "Wyoming",
  "years_exp": 7,
  "jersey_number": 17,
  
  "projected_points": 285.4,
  "projected_points_half_ppr": 285.4,
  "projected_points_standard": 285.4,
  "adp": 3.2,
  "adp_trend": -0.5,
  "ownership_percentage": 98.5,
  
  "target_share": null,
  "air_yards_share": null,
  "snap_count_percentage": 95.2,
  "carries_share": null,
  
  "injury_status": "HEALTHY",
  "injury_body_part": null,
  "injury_notes": null,
  "practice_status": "Full",
  
  "trending_direction": "STABLE",
  "trending_count": 1250,
  
  "risk_level": "LOW",
  "ceiling_score": 320.5,
  "floor_score": 250.3,
  "consistency_rating": 8.5,
  
  "position_rank": 2,
  "tier": 1,
  "expert_consensus_rank": 3,
  
  "is_rookie": false,
  "is_handcuff": false,
  
  "season_stats": {
    "passing_yards": 4306,
    "passing_tds": 29,
    "rushing_yards": 524,
    "rushing_tds": 15
  },
  
  "last_game_stats": {
    "passing_yards": 263,
    "passing_tds": 2,
    "rushing_yards": 39,
    "rushing_tds": 1
  }
}
```

#### Injury Status Enum
- `HEALTHY`: No injury concerns
- `QUESTIONABLE`: May play, game-time decision
- `DOUBTFUL`: Unlikely to play
- `OUT`: Will not play
- `IR`: Injured Reserve
- `PUP`: Physically Unable to Perform
- `SUSPENDED`: Suspended from play

#### Risk Level Calculation
- **LOW**: Healthy, established player under 30
- **MEDIUM**: Minor injury concerns, age 30-32, or limited experience
- **HIGH**: Major injury concerns, age 33+, or multiple risk factors

### Usage Examples

#### Get High-Value RBs with Low Injury Risk
```bash
curl "http://localhost:8000/api/v1/players/enhanced/?position=RB&min_projected_points=150&max_risk_level=LOW&limit=10"
```

#### Find Trending WRs
```bash
curl "http://localhost:8000/api/v1/players/enhanced/trending/UP?limit=15"
```

#### Compare Top QBs
```bash
curl "http://localhost:8000/api/v1/players/enhanced/comparison?player_ids=1,2,3"
```

#### Get Current Injury Report
```bash
curl "http://localhost:8000/api/v1/players/enhanced/injury-report"
```

### Frontend Integration

The enhanced player data integrates with existing frontend components:

#### Players Page Enhancements
- Advanced filtering options
- Risk level indicators
- Injury status badges
- Trending indicators
- Enhanced player cards

#### Draft Assistant Integration
- Better player recommendations using risk levels
- Injury-aware draft suggestions
- Advanced metrics in player comparisons
- Ceiling/floor projections for picks

#### Real-time Updates
- Live injury status updates
- Trending data refreshes
- Practice report integration
- News and analysis updates

### Data Sources & Accuracy

#### Primary Data Sources
- **Sleeper API**: Player roster data, injury status, trending
- **AI Analysis**: GPT-4 powered insights and projections
- **Calculated Metrics**: Risk levels, tiers, consistency ratings

#### Update Frequency
- **Player Sync**: Manual trigger or scheduled daily
- **Injury Updates**: Real-time when data changes
- **Trending Data**: Updated hourly during season
- **AI Analysis**: Generated on-demand

#### Data Validation
- Enum validation for status fields
- Range validation for numeric metrics
- Cross-reference validation across sources
- Automated data quality checks

### Performance Considerations

#### Database Optimization
- Indexed fields: `team`, `position`, `injury_status`, `sleeper_id`
- JSON fields for flexible stat storage
- Efficient queries with proper filtering
- Pagination for large result sets

#### Caching Strategy
- Player data cached for 1 hour
- Injury reports cached for 15 minutes
- Trending data cached for 30 minutes
- AI analysis cached for 24 hours

#### API Rate Limiting
- Enhanced endpoints respect rate limits
- Batch processing for data sync
- Efficient external API usage
- Fallback mechanisms for data failures

### Future Enhancements

#### Planned Features
- Historical performance tracking
- Advanced stat projections
- Matchup-based analysis
- Trade value calculations
- Waiver wire priority scoring

#### Data Integrations
- ESPN API integration for additional stats
- Yahoo API for ownership data
- FantasyPros consensus rankings
- Advanced metrics providers

#### Machine Learning
- Predictive injury models
- Performance trend analysis
- Breakout player identification
- Bust probability calculations

## Testing

### API Testing
All enhanced endpoints are tested and functional:
- Enhanced player search with filtering ✅
- Injury report generation ✅
- Player comparison system ✅
- Trending player analysis ✅
- Advanced metrics calculation ✅

### Database Migration
Enhanced player model migrated successfully:
- New columns added ✅
- Enum types created ✅
- Indexes optimized ✅
- Data integrity maintained ✅

The Enhanced Player Data System provides a comprehensive foundation for advanced fantasy football analysis with rich player information, intelligent risk assessment, and AI-powered insights.