from typing import List, Dict, Optional, Any
from enum import Enum
import openai
import anthropic
from app.core.config import settings
import json
import asyncio


class AIProvider(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class AIService:
    def __init__(self):
        self.openai_client = None
        self.anthropic_client = None
        
        if settings.OPENAI_API_KEY:
            self.openai_client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        
        if settings.ANTHROPIC_API_KEY:
            self.anthropic_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def generate_player_analysis(
        self, 
        player_name: str, 
        player_data: Dict[str, Any],
        historical_data: Optional[Dict[str, Any]] = None,
        provider: AIProvider = AIProvider.OPENAI
    ) -> str:
        # Build enhanced prompt with historical context
        historical_context = ""
        if historical_data:
            historical_context = f"""
        
        HISTORICAL PERFORMANCE DATA:
        {json.dumps(historical_data, indent=2)}
        
        Consider the player's historical trends, consistency patterns, and performance trajectory when making your analysis.
        """
        
        prompt = f"""
        Analyze the fantasy football player {player_name} based on the following data:
        
        CURRENT SEASON DATA:
        {json.dumps(player_data, indent=2)}
        {historical_context}
        
        Provide a comprehensive analysis including:
        1. Strengths and weaknesses (considering historical performance)
        2. Injury concerns and risk factors (using historical health patterns)
        3. Target share and usage trends (with historical context)
        4. Performance consistency and reliability (based on historical data)
        5. Rest of season outlook (informed by historical trends)
        6. PPR-specific value assessment
        
        If historical data is available, specifically comment on:
        - Performance trends (improving, declining, stable)
        - Consistency patterns and reliability
        - Historical performance in similar situations
        - Seasonal patterns and splits
        
        Keep the analysis concise but informative, around 200-250 words.
        """
        
        # Try OpenAI first, fallback to Anthropic if it fails
        if provider == AIProvider.OPENAI and self.openai_client:
            try:
                result = await self._generate_openai(prompt)
                # Check if OpenAI returned an error message
                if result.startswith("OpenAI API error:"):
                    raise Exception(result)
                return result
            except Exception as e:
                # If OpenAI fails and we have Anthropic available, try it
                if self.anthropic_client:
                    print(f"OpenAI failed ({str(e)}), falling back to Anthropic")
                    try:
                        return await self._generate_anthropic(prompt)
                    except Exception as anthropic_error:
                        return f"AI analysis failed: OpenAI error ({str(e)}), Anthropic error ({str(anthropic_error)})"
                else:
                    return f"AI analysis failed: {str(e)}"
        elif provider == AIProvider.ANTHROPIC and self.anthropic_client:
            try:
                result = await self._generate_anthropic(prompt)
                # Check if Anthropic returned an error message
                if result.startswith("Anthropic API error:"):
                    raise Exception(result)
                return result
            except Exception as e:
                # If Anthropic fails and we have OpenAI available, try it
                if self.openai_client:
                    print(f"Anthropic failed ({str(e)}), falling back to OpenAI")
                    try:
                        return await self._generate_openai(prompt)
                    except Exception as openai_error:
                        return f"AI analysis failed: Anthropic error ({str(e)}), OpenAI error ({str(openai_error)})"
                else:
                    return f"AI analysis failed: {str(e)}"
        else:
            return "AI analysis unavailable - no API key configured"

    async def generate_draft_recommendation(
        self,
        available_players: List[Dict[str, Any]],
        team_needs: List[str],
        draft_position: int,
        scoring_format: str = "PPR",
        points_per_reception: Optional[float] = None
    ) -> Dict[str, Any]:
        # scoring_format alone used to be the only signal handed to the
        # model, and callers frequently passed a platform's coarse label
        # (e.g. ESPN's scoring_type: STANDARD/H2H_POINTS/H2H_CATEGORIES) as
        # if it were the PPR/Half-PPR/Standard reception-scoring rule. Those
        # are different axes -- a H2H_POINTS league can be full-PPR,
        # half-PPR, or standard depending on its actual per-stat scoring --
        # so that label alone can't tell the model how receptions are
        # scored. When the caller has a real, connected-league
        # points_per_reception value (see draft_assistant_service's
        # _get_league_settings / FALLBACK_ROSTER_REQUIREMENTS), state the
        # real numeric rule explicitly instead.
        if points_per_reception is None:
            scoring_description = f"{scoring_format} scoring"
        elif points_per_reception == 0:
            scoring_description = "Standard (0 points per reception) scoring"
        elif points_per_reception == 1:
            scoring_description = "PPR (1 point per reception) scoring"
        elif points_per_reception == 0.5:
            scoring_description = "Half-PPR (0.5 points per reception) scoring"
        else:
            scoring_description = f"Custom PPR ({points_per_reception} points per reception) scoring"

        prompt = f"""
        Draft Assistant for {scoring_description}:

        Current draft position: {draft_position}
        Team needs: {', '.join(team_needs)}
        
        Available players:
        {json.dumps(available_players[:10], indent=2)}
        
        Recommend the top 3 draft picks with reasoning. Format as JSON:
        {{
            "recommendations": [
                {{
                    "player_name": "Player Name",
                    "position": "RB",
                    "reasoning": "Why this pick makes sense",
                    "confidence": 85
                }}
            ]
        }}
        """
        
        # Try OpenAI first, fallback to Anthropic if it fails
        response = None
        try:
            if self.openai_client:
                response = await self._generate_openai(prompt)
                if response.startswith("OpenAI API error:"):
                    raise Exception(response)
            elif self.anthropic_client:
                response = await self._generate_anthropic(prompt)
                if response.startswith("Anthropic API error:"):
                    raise Exception(response)
            else:
                return {"recommendations": [], "error": "No AI provider available"}
        except Exception as e:
            # Try the other provider as fallback
            try:
                if self.anthropic_client and not response:
                    print(f"OpenAI failed for draft recommendation, trying Anthropic")
                    response = await self._generate_anthropic(prompt)
                elif self.openai_client and not response:
                    print(f"Anthropic failed for draft recommendation, trying OpenAI")
                    response = await self._generate_openai(prompt)
                else:
                    return {"recommendations": [], "error": f"AI generation failed: {str(e)}"}
            except Exception as fallback_error:
                return {"recommendations": [], "error": f"All AI providers failed: {str(e)}, {str(fallback_error)}"}
        
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return {"recommendations": [], "error": "Failed to parse AI response"}

    async def generate_waiver_analysis(
        self,
        waiver_candidates: List[Dict[str, Any]],
        league_context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        prompt = f"""
        Analyze these waiver wire candidates for fantasy football:
        
        League context: {json.dumps(league_context)}
        
        Candidates:
        {json.dumps(waiver_candidates, indent=2)}
        
        For each player, provide:
        1. Priority level (HIGH/MEDIUM/LOW)
        2. Reasoning for pickup
        3. Expected role/usage
        4. Rest of season outlook
        
        Format as JSON array of player analyses.
        """
        
        # Try OpenAI first, fallback to Anthropic if it fails
        response = None
        try:
            if self.openai_client:
                response = await self._generate_openai(prompt)
                if response.startswith("OpenAI API error:"):
                    raise Exception(response)
            elif self.anthropic_client:
                response = await self._generate_anthropic(prompt)
                if response.startswith("Anthropic API error:"):
                    raise Exception(response)
            else:
                return []
        except Exception as e:
            # Try the other provider as fallback
            try:
                if self.anthropic_client and not response:
                    print(f"OpenAI failed for waiver analysis, trying Anthropic")
                    response = await self._generate_anthropic(prompt)
                elif self.openai_client and not response:
                    print(f"Anthropic failed for waiver analysis, trying OpenAI")
                    response = await self._generate_openai(prompt)
                else:
                    print(f"Waiver analysis failed: {str(e)}")
                    return []
            except Exception as fallback_error:
                print(f"All AI providers failed for waiver analysis: {str(e)}, {str(fallback_error)}")
                return []
        
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return []

    async def generate_multi_perspective_content(
        self,
        topic: str,
        source_articles: List[Dict[str, str]],
        perspectives: List[str] = None
    ) -> Dict[str, Any]:
        if perspectives is None:
            perspectives = [
                "Conservative/Risk-Averse",
                "Aggressive/High-Upside", 
                "Data-Driven/Analytics",
                "Situational/Matchup-Based",
                "Long-term/Dynasty"
            ]
        
        perspective_analyses = []
        
        for perspective in perspectives:
            prompt = f"""
            Topic: {topic}
            
            Source articles:
            {json.dumps(source_articles, indent=2)}
            
            Analyze this topic from a {perspective} perspective for fantasy football.
            
            Provide:
            1. Key takeaways from this viewpoint
            2. Recommended actions
            3. Risk assessment
            4. Confidence level (1-10)
            
            Keep response focused and actionable, around 100-150 words.
            """
            
            analysis = await self._generate_openai(prompt)
            perspective_analyses.append({
                "perspective": perspective,
                "analysis": analysis
            })
            
            # Add small delay to avoid rate limits
            await asyncio.sleep(0.1)
        
        return {
            "topic": topic,
            "perspectives": perspective_analyses,
            "generated_at": "now"
        }

    async def generate_consensus_recommendation(
        self,
        topic: str,
        perspective_analyses: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        prompt = f"""
        Topic: {topic}
        
        Multiple perspective analyses:
        {json.dumps(perspective_analyses, indent=2)}
        
        Create a consensus recommendation that:
        1. Synthesizes the different viewpoints
        2. Identifies areas of agreement and disagreement
        3. Provides a balanced, actionable recommendation
        4. Assigns a confidence score (1-10)
        5. Highlights key risk factors
        
        Format as JSON:
        {{
            "consensus_recommendation": "Main recommendation text",
            "confidence_score": 8,
            "key_agreements": ["point 1", "point 2"],
            "key_disagreements": ["point 1", "point 2"],
            "risk_factors": ["risk 1", "risk 2"],
            "action_items": ["action 1", "action 2"]
        }}
        """
        
        response = await self._generate_openai(prompt)
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return {"error": "Failed to generate consensus"}

    async def _generate_openai(self, prompt: str, model: str = "gpt-4") -> str:
        if not self.openai_client:
            return "OpenAI client not configured"

        try:
            response = await self.openai_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are an expert fantasy football analyst."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            return response.choices[0].message.content
        # Most-specific-first: every branch below is a subclass of
        # openai.APIStatusError (itself a subclass of openai.APIError), so
        # order matters -- a broader except above a narrower one would
        # swallow it and produce a less useful message.
        except openai.AuthenticationError as e:
            return f"OpenAI API error: authentication failed - check OPENAI_API_KEY ({e.message})"
        except openai.PermissionDeniedError as e:
            return f"OpenAI API error: permission denied ({e.message})"
        except openai.RateLimitError as e:
            return f"OpenAI API error: rate limited ({e.message})"
        except openai.APIConnectionError as e:
            return f"OpenAI API error: connection failed ({e.message})"
        except openai.APIStatusError as e:
            return f"OpenAI API error: {e.status_code} {e.message}"
        except openai.OpenAIError as e:
            return f"OpenAI API error: {str(e)}"

    async def _generate_anthropic(self, prompt: str, model: str = "claude-sonnet-5") -> str:
        if not self.anthropic_client:
            return "Anthropic client not configured"

        try:
            response = await self.anthropic_client.messages.create(
                model=model,
                max_tokens=1000,
                # `temperature` was removed from messages.create() entirely
                # in current anthropic SDK versions (it's no longer even an
                # accepted keyword argument, not just rejected server-side
                # for certain models) -- prompting is the recommended way
                # to steer output instead.
                system="You are an expert fantasy football analyst.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            # response.content is a list of content blocks (TextBlock,
            # ThinkingBlock, ...) -- guard on .type before reading .text
            # rather than indexing content[0] unconditionally.
            for block in response.content:
                if block.type == "text":
                    return block.text
            return "Anthropic API error: response contained no text content"
        # Most-specific-first: every branch below is a subclass of
        # anthropic.APIStatusError (itself a subclass of anthropic.APIError),
        # so order matters -- a broader except above a narrower one would
        # swallow it and produce a less useful message.
        except anthropic.AuthenticationError as e:
            return f"Anthropic API error: authentication failed - check ANTHROPIC_API_KEY ({e.message})"
        except anthropic.PermissionDeniedError as e:
            return f"Anthropic API error: permission denied ({e.message})"
        except anthropic.RateLimitError as e:
            return f"Anthropic API error: rate limited ({e.message})"
        except anthropic.APIConnectionError as e:
            return f"Anthropic API error: connection failed ({e.message})"
        except anthropic.APIStatusError as e:
            return f"Anthropic API error: {e.status_code} {e.message}"
        except anthropic.AnthropicError as e:
            return f"Anthropic API error: {str(e)}"

    async def get_ai_status(self) -> Dict[str, Any]:
        """Get the status of AI providers"""
        return {
            "openai_available": self.openai_client is not None,
            "anthropic_available": self.anthropic_client is not None,
            "primary_provider": "OpenAI" if self.openai_client else "Anthropic" if self.anthropic_client else "None",
            "fallback_enabled": self.openai_client is not None and self.anthropic_client is not None
        }


ai_service = AIService()