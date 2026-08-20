# Live Draft Assistant Testing Guide

## Overview
The Live Draft Assistant provides real-time AI-powered draft recommendations with WebSocket-based live updates during fantasy football drafts.

## Features
- **Real-time Draft Recommendations**: AI-powered player suggestions based on team needs and draft position
- **Live Updates**: WebSocket connection for real-time data updates
- **Multi-Platform Support**: Works with Sleeper, ESPN, and Yahoo Fantasy leagues
- **Draft Board**: Available players with tiers, projections, and ADP
- **Team Analysis**: Roster needs analysis and positional recommendations
- **Interactive UI**: Click-to-draft functionality with live updates

## Testing the Live Draft Assistant

### 1. Access the Application
- Frontend: http://localhost:3001
- Backend API: http://localhost:8000
- Live Draft Page: http://localhost:3001/live-draft

### 2. Start a Draft Session

#### Required Information:
- **Platform**: Choose from Sleeper, ESPN, or Yahoo
- **League ID**: Your actual league ID or test ID (e.g., "test123")
- **Scoring Format**: PPR, Half PPR, or Standard
- **League Size**: 8, 10, 12, or 14 teams

#### Steps:
1. Navigate to the Live Draft page
2. Fill in draft settings
3. Click "Start Live Draft"
4. Wait for session initialization

### 3. Test Live Features

#### WebSocket Connection:
- Look for "Live" indicator in top right (green dot)
- Recommendations update every 10 seconds automatically
- Real-time updates when picks are made

#### Draft Recommendations:
- Top 5 AI-recommended picks displayed
- Each recommendation includes:
  - Player name, position, team
  - AI reasoning for the pick
  - Confidence score
  - Tier information
  - Projected points

#### Available Players Board:
- Shows top available players
- Sortable by position, projected points, ADP
- Click any player to make a pick

#### Your Roster:
- Shows drafted players in order
- Updates automatically when picks are made

#### Team Analysis:
- Roster needs (positions to prioritize)
- Next best pick recommendation
- Positional strength analysis

### 4. Test Draft Actions

#### Making a Pick:
1. Click on any recommended player or available player
2. Player is added to your roster
3. New recommendations are generated
4. Draft board is updated

#### WebSocket Updates:
- Recommendations refresh automatically
- Pick updates sent in real-time
- Error handling for connection issues

### 5. API Testing

#### Start Session:
```bash
curl -X POST http://localhost:8000/api/v1/live-draft/start-session \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "sleeper",
    "league_id": "test123",
    "scoring_format": "PPR",
    "league_size": 12
  }'
```

#### Get Recommendations:
```bash
curl -X GET http://localhost:8000/api/v1/live-draft/recommendations/SESSION_ID
```

#### Make a Pick:
```bash
curl -X POST http://localhost:8000/api/v1/live-draft/update-pick \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "SESSION_ID",
    "player_picked": {
      "player_id": "123",
      "full_name": "Test Player",
      "position": "RB",
      "team": "TB"
    }
  }'
```

#### WebSocket Connection:
```
ws://localhost:8000/api/v1/live-draft/ws/SESSION_ID
```

### 6. Expected Behavior

#### Successful Session:
- Session ID generated in format: `platform_leagueId_timestamp`
- Initial recommendations provided
- WebSocket connection established
- "Live" indicator shows green

#### Real-time Updates:
- Recommendations refresh every 10 seconds
- Immediate updates when picks are made
- Draft board reflects current availability

#### AI Recommendations:
- Context-aware suggestions based on roster needs
- Confidence scoring (1-100%)
- Tier-based rankings
- Strategic reasoning provided

#### Error Handling:
- Invalid league IDs handled gracefully
- WebSocket reconnection attempts
- API error messages displayed

### 7. Test Scenarios

#### Valid League (Sleeper):
- Use an actual Sleeper league ID
- Should pull real draft data
- Live updates based on actual draft state

#### Simulated Mode:
- Use test league ID like "test123"
- Falls back to trending players
- AI recommendations still functional

#### Multi-User Testing:
- Multiple users can connect to same league
- Updates propagate to all connected users
- Each user sees personalized recommendations

### 8. Troubleshooting

#### Common Issues:
1. **WebSocket Connection Failed**
   - Check backend is running
   - Verify CORS settings
   - Try refreshing the page

2. **No Recommendations**
   - Verify session was created successfully
   - Check AI service is configured
   - Look for errors in browser console

3. **League Not Found**
   - Verify league ID is correct
   - Check platform selection matches
   - Use test ID for simulation

#### Debug Information:
- Browser console shows WebSocket messages
- Network tab shows API calls
- Backend logs show session activity

## Architecture

### Frontend Components:
- `LiveDraftPage.tsx`: Main draft interface
- WebSocket connection management
- Real-time state updates
- Interactive draft board

### Backend Services:
- `live_draft.py`: WebSocket and HTTP endpoints
- `draft_assistant_service.py`: Core draft logic
- `ai_service.py`: AI-powered recommendations
- Platform services (Sleeper, ESPN, Yahoo)

### WebSocket Messages:
- `recommendations_update`: New AI recommendations
- `pick_update`: Draft pick made
- `error`: Error message

### Session Management:
- Active sessions stored in memory
- Automatic cleanup on disconnect
- Session status tracking

## Future Enhancements
- Draft room chat functionality
- Multi-league draft tracking
- Advanced analytics and insights
- Mobile-responsive design improvements
- Push notifications for draft picks