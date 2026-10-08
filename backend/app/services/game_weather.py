"""Pregame weather forecasts for NFL games (the "wind unders" test).

Wind unders (outdoor wind >= 12 mph) returned +15.5% in 2015-24 but used
game-time wind, which isn't knowable before betting, and didn't repeat in
2025-26 (BETTING_GUIDE section 9). To test it honestly this logs the
FORECAST: on each board build (at most every REFRESH), every upcoming game's
forecast for the kickoff hour is stored in game_weather and frozen once the
game starts. Indoor/outdoor, city and ESPN's condition come from ESPN's
scoreboard; wind, gusts, temperature and precipitation chance from
Open-Meteo (free, no key). Network failures skip a game -- never guessed.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.db.base import SessionLocal
from app.models.game_weather import GameWeather
from app.services.odds_service import normalize_team

logger = logging.getLogger(__name__)

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"
REFRESH = timedelta(hours=3)
US_STATES = {
    "AL": "Alabama", "AZ": "Arizona", "CA": "California", "CO": "Colorado", "FL": "Florida", "GA": "Georgia",
    "IL": "Illinois", "IN": "Indiana", "LA": "Louisiana", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MO": "Missouri", "NV": "Nevada", "NJ": "New Jersey", "NY": "New York", "NC": "North Carolina",
    "OH": "Ohio", "PA": "Pennsylvania", "TN": "Tennessee", "TX": "Texas", "WA": "Washington", "WI": "Wisconsin",
    "DC": "District of Columbia",
}
_geo: Dict[Tuple[str, str], Tuple[float, float]] = {}


def nearest_hour(hourly: Dict[str, List[Any]], kickoff: datetime) -> Optional[Dict[str, Any]]:
    """The forecast row for the hour closest to kickoff (Open-Meteo hourly, UTC)."""
    times = hourly.get("time") or []
    if not times:
        return None
    k = kickoff.astimezone(timezone.utc).replace(tzinfo=None)
    i = min(range(len(times)), key=lambda j: abs(datetime.fromisoformat(times[j]) - k))
    if abs(datetime.fromisoformat(times[i]) - k) > timedelta(hours=2):
        return None  # kickoff is outside the forecast window
    pick = lambda key: (hourly.get(key) or [None] * len(times))[i]  # noqa: E731
    return {"wind_mph": pick("wind_speed_10m"), "gust_mph": pick("wind_gusts_10m"),
            "temp_f": pick("temperature_2m"), "precip_prob": pick("precipitation_probability")}


async def _coords(client: httpx.AsyncClient, city: str, state: Optional[str]) -> Optional[Tuple[float, float]]:
    key = (city, state or "")
    if key in _geo:
        return _geo[key]
    r = await client.get(GEOCODE, params={"name": city, "count": 10, **({"countryCode": "US"} if state else {})})
    results = r.json().get("results") or [] if r.status_code == 200 else []
    want = US_STATES.get(state or "")
    hit = next((x for x in results if want and x.get("admin1") == want), results[0] if results else None)
    if not hit:
        return None
    _geo[key] = (hit["latitude"], hit["longitude"])
    return _geo[key]


def _due(season: int, week: int, game: str, now: datetime) -> bool:
    with SessionLocal() as db:
        row = db.query(GameWeather).filter_by(season=season, week=week, game=game).first()
        if row is None:
            return True
        fetched = row.fetched_at if row.fetched_at.tzinfo else row.fetched_at.replace(tzinfo=timezone.utc)
        kickoff = row.kickoff if not row.kickoff or row.kickoff.tzinfo else row.kickoff.replace(tzinfo=timezone.utc)
        return (kickoff is None or kickoff > now) and now - fetched >= REFRESH


def save(season: int, week: int, game: str, values: Dict[str, Any], now: Optional[datetime] = None) -> None:
    now = now or datetime.now(timezone.utc)
    with SessionLocal() as db:
        row = db.query(GameWeather).filter_by(season=season, week=week, game=game).first()
        if row is None:
            row = GameWeather(season=season, week=week, game=game)
            db.add(row)
        kickoff = values.get("kickoff")
        if row.kickoff is not None:
            k = row.kickoff if row.kickoff.tzinfo else row.kickoff.replace(tzinfo=timezone.utc)
            if k <= now:
                return  # frozen at kickoff: keep the last pregame forecast
        for k, v in values.items():
            setattr(row, k, v)
        row.fetched_at = now
        db.commit()


async def record_forecasts(season: int, week: int, now: Optional[datetime] = None) -> int:
    """Store the kickoff-hour forecast for this week's upcoming games. Returns rows written."""
    now = now or datetime.now(timezone.utc)
    written = 0
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(ESPN_SCOREBOARD, params={"seasontype": 2, "week": week, "dates": season})
        events = r.json().get("events", []) if r.status_code == 200 else []
        for ev in events:
            comp = ev["competitions"][0]
            teams = {c["homeAway"]: normalize_team(c["team"].get("abbreviation")) or c["team"].get("abbreviation")
                     for c in comp["competitors"]}
            game = f"{teams.get('away')} @ {teams.get('home')}"
            kickoff = datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
            if kickoff <= now or not await asyncio.to_thread(_due, season, week, game, now):
                continue
            venue = comp.get("venue") or {}
            weather = ev.get("weather") or {}
            values: Dict[str, Any] = {"kickoff": kickoff, "indoor": bool(venue.get("indoor")),
                                      "condition": weather.get("displayValue")}
            try:
                if venue.get("indoor"):
                    values.update(source="indoor", wind_mph=0.0, gust_mph=0.0, temp_f=weather.get("temperature"))
                else:
                    addr = venue.get("address") or {}
                    coords = await _coords(client, addr.get("city") or "", addr.get("state"))
                    if not coords:
                        continue
                    f = await client.get(FORECAST, params={
                        "latitude": coords[0], "longitude": coords[1], "timezone": "UTC", "forecast_days": 16,
                        "hourly": "wind_speed_10m,wind_gusts_10m,temperature_2m,precipitation_probability",
                        "wind_speed_unit": "mph", "temperature_unit": "fahrenheit"})
                    hour = nearest_hour(f.json().get("hourly") or {}, kickoff) if f.status_code == 200 else None
                    if not hour:
                        continue
                    values.update(source="open-meteo", **hour)
            except (httpx.HTTPError, ValueError, KeyError) as e:
                logger.warning("Forecast for %s skipped: %s", game, type(e).__name__)
                continue
            await asyncio.to_thread(save, season, week, game, values, now)
            written += 1
    return written
