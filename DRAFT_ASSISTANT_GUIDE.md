# Live Draft Assistant Guide

## Overview

The Fantasy Football Assistant now includes real-time draft assistance that works with **ESPN**, **Yahoo**, and **Sleeper** fantasy platforms. Get AI-powered recommendations, tier-based rankings, and live draft monitoring during your draft.

## Features

### 🎯 **Real-Time Draft Assistance**
- Live pick recommendations based on your roster needs
- Multi-perspective AI analysis for each pick
- Value pick identification and sleeper alerts
- Positional tier rankings with real-time updates

### 🏈 **Platform Integration**
- **ESPN Fantasy Football**: Full draft room monitoring
- **Yahoo Fantasy Sports**: OAuth authentication + live drafts
- **Sleeper**: Player data and trending analysis

### 📊 **Advanced Analytics**
- Team construction analysis
- Positional need identification  
- Draft strategy recommendations by round
- Player value calculations and tier drops

### ⚡ **Live Updates**
- WebSocket connections for real-time updates
- Automatic draft progress monitoring
- Instant recommendation refreshing
- Pick timer awareness

## Getting Started

### 1. Start a Draft Session

```bash
curl -X POST "http://localhost:8000/api/v1/live-draft/start-session" \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "espn",
    "league_id": "123456",
    "user_team_id": "1",
    "scoring_format": "PPR",
    "league_size": 12
  }'
```

**Response:**
```json
{
  "session_id": "espn_123456_1234567890",
  "draft_state": {
    "status": "in_progress",
    "current_pick": 15,
    "available_players": [...],
    "recent_picks": [...]
  },
  "initial_recommendations": {
    "top_recommendations": [...],
    "value_picks": [...],
    "sleeper_picks": [...]
  }
}
```

### 2. Get Live Recommendations

```bash
curl "http://localhost:8000/api/v1/live-draft/recommendations/{session_id}"
```

**Response:**
```json
{
  "top_recommendations": [
    {
      "player_name": "Saquon Barkley",
      "position": "RB",
      "reasoning": "Elite RB1 upside with improved offensive line",
      "confidence": 89
    }
  ],
  "value_picks": [
    {
      "player": {...},
      "value_score": 18.5,
      "reason": "High projection (12.8) with low ownership (45%)"
    }
  ],
  "position_needs": ["RB", "WR"],
  "draft_strategy": "Focus on RB depth - thin position in later rounds",
  "confidence_score": 8
}
```

### 3. WebSocket Connection for Real-Time Updates

```javascript
const ws = new WebSocket('ws://localhost:8000/api/v1/live-draft/ws/{session_id}');

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    
    if (data.type === 'recommendations_update') {
        updateDraftBoard(data.data);
    } else if (data.type === 'pick_update') {
        refreshUserRoster(data.data);
    }
};
```

## Platform-Specific Setup

### ESPN Fantasy Football

ESPN leagues are **publicly accessible** - no authentication required!

```bash
# Get league info
curl "http://localhost:8000/api/v1/live-draft/espn/leagues/123456/info"

# Get teams
curl "http://localhost:8000/api/v1/live-draft/espn/leagues/123456/teams"

# Monitor draft
curl "http://localhost:8000/api/v1/live-draft/espn/leagues/123456/draft"
```

### Yahoo Fantasy Sports

Yahoo requires **OAuth authentication**:

1. **Get Authorization URL:**
   ```
   https://api.login.yahoo.com/oauth2/request_auth?
   client_id=YOUR_CLIENT_ID&
   redirect_uri=YOUR_REDIRECT_URI&
   response_type=code&
   scope=fspt-r
   ```

2. **Exchange Code for Token:**
   ```bash
   curl -X POST "http://localhost:8000/api/v1/live-draft/yahoo/authenticate" \
     -H "Content-Type: application/json" \
     -d '{
       "authorization_code": "AUTH_CODE_FROM_STEP_1",
       "redirect_uri": "YOUR_REDIRECT_URI"
     }'
   ```

3. **Get Your Leagues:**
   ```bash
   curl "http://localhost:8000/api/v1/live-draft/yahoo/leagues"
   ```

### Sleeper

Sleeper uses **public APIs** - no authentication needed:

```bash
# Start session with Sleeper
curl -X POST "http://localhost:8000/api/v1/live-draft/start-session" \
  -d '{"platform": "sleeper", "league_id": "123456789"}'
```

## Draft Assistant Features

### 1. **Multi-Perspective Recommendations**

The AI analyzes each pick from 5 different angles:
- **Conservative**: Safe, proven players
- **Aggressive**: High-upside boom/bust candidates  
- **Data-Driven**: Advanced metrics and projections
- **Situational**: Matchup and game script analysis
- **Dynasty**: Long-term value assessment

### 2. **Tier-Based Draft Board**

```bash
curl "http://localhost:8000/api/v1/live-draft/draft-board/{session_id}"
```

**Response:**
```json
{
  "draft_board": {
    "RB": {
      "tiers": {
        "tier_1": [{"name": "Christian McCaffrey", ...}],
        "tier_2": [{"name": "Derrick Henry", ...}],
        "tier_3": [...]
      },
      "available_count": 45
    }
  }
}
```

### 3. **Team Analysis & Roster Building**

```bash
curl "http://localhost:8000/api/v1/live-draft/team-analysis/{session_id}"
```

**Response:**
```json
{
  "roster": [
    {
      "player": {"name": "Josh Allen", "position": "QB"},
      "pick_number": 3,
      "round": 1
    }
  ],
  "position_counts": {"QB": 1, "RB": 0, "WR": 0},
  "positional_needs": ["RB", "WR", "TE"],
  "team_analysis": "Strong QB foundation, need skill position depth",
  "roster_strength": {"grade": "B+", "score": 12.3},
  "next_pick_suggestions": ["RB", "WR"]
}
```

### 4. **Update Your Picks**

```bash
curl -X POST "http://localhost:8000/api/v1/live-draft/update-pick" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "espn_123456_1234567890",
    "player_picked": {
      "name": "Saquon Barkley",
      "position": "RB",
      "team": "NYG"
    }
  }'
```

## Draft Strategy Intelligence

### Round-by-Round Strategy

- **Rounds 1-3**: Elite RBs and WRs, avoid QB/TE early
- **Rounds 4-6**: Fill positional needs, consider tier 1 QB/TE
- **Rounds 7-10**: Depth and high-upside players
- **Rounds 11-16**: Handcuffs, lottery tickets, streaming options

### Position Prioritization

The assistant automatically adjusts recommendations based on:
- **Positional scarcity** (RB depth falls off faster)
- **Your roster construction** (balanced vs. zero-RB strategies)
- **League scoring** (PPR vs. Standard adjustments)
- **Draft position** (early vs. late round strategies)

### Value Identification

- **Value Picks**: High projected points with lower ownership
- **Sleepers**: Late-round players with breakout potential
- **Handcuffs**: Backup RBs for your starters
- **Streaming Options**: Week-to-week starters (K, DEF)

## Error Handling & Troubleshooting

### Common Issues

1. **"Session not found"**: Session expired or invalid ID
2. **"Platform authentication required"**: Yahoo needs OAuth token
3. **"League not found"**: Invalid league ID or private league
4. **"Draft not active"**: Draft hasn't started or already finished

### Debug Endpoints

```bash
# Check session status
curl "http://localhost:8000/api/v1/live-draft/session/{session_id}/status"

# End session
curl -X DELETE "http://localhost:8000/api/v1/live-draft/session/{session_id}"
```

## Frontend Integration

### React Component Example

```jsx
import { useEffect, useState } from 'react';

function DraftAssistant({ sessionId }) {
  const [recommendations, setRecommendations] = useState(null);
  const [ws, setWs] = useState(null);

  useEffect(() => {
    // Connect to WebSocket
    const websocket = new WebSocket(`ws://localhost:8000/api/v1/live-draft/ws/${sessionId}`);
    
    websocket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'recommendations_update') {
        setRecommendations(data.data);
      }
    };

    setWs(websocket);
    
    return () => websocket.close();
  }, [sessionId]);

  const updatePick = async (player) => {
    await fetch('/api/v1/live-draft/update-pick', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        player_picked: player
      })
    });
  };

  return (
    <div className="draft-assistant">
      {recommendations?.top_recommendations?.map(rec => (
        <div key={rec.player_name} className="recommendation">
          <h3>{rec.player_name} - {rec.position}</h3>
          <p>{rec.reasoning}</p>
          <span>Confidence: {rec.confidence}%</span>
          <button onClick={() => updatePick(rec)}>
            Select Player
          </button>
        </div>
      ))}
    </div>
  );
}
```

## Advanced Features

### Custom Scoring Settings

The assistant adapts to your league's scoring:
- **PPR vs. Standard**: Adjusts WR/RB valuations
- **Superflex**: QB prioritization changes
- **IDP Leagues**: Defensive player recommendations
- **Custom Positions**: TE premium, extra flex spots

### League-Specific Analysis

- **Roster Requirements**: Adapts to league starting lineups
- **Bench Size**: Affects handcuff/lottery ticket strategy  
- **Trade Analysis**: Post-draft trade recommendations
- **Waiver Priority**: Considers your draft position for waivers

## API Rate Limits

- **ESPN**: No authentication required, respect rate limits
- **Yahoo**: OAuth token required, 1000 requests/hour
- **Sleeper**: Public API, built-in rate limiting
- **AI Services**: Cached responses to minimize API calls

## Next Steps

1. **Start a draft session** with your platform
2. **Connect via WebSocket** for real-time updates  
3. **Monitor recommendations** throughout your draft
4. **Update picks** as you draft players
5. **Get post-draft analysis** and waiver recommendations

Your Fantasy Football Assistant is now ready to help you dominate your draft! 🏆