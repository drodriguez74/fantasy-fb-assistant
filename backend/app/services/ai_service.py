from typing import List, Dict, Optional, Any
from enum import Enum
import openai
import anthropic
from app.core.config import settings
from app.services.scoring_rules import describe_scoring_rules
import json
import asyncio


class AIProvider(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class AIService:
    # -------------------------------------------------------------------
    # Model tiers
    #
    # Two tiers per provider, chosen for the two workload shapes this
    # service actually produces:
    #
    #   FAST -- short, bounded, low-stakes generations: a single player's
    #           write-up, a per-position grade + summary, a batch of
    #           waiver-wire priority blurbs, a single matchup blurb. These
    #           are close to "summarize/classify this data" tasks -- they
    #           don't need frontier reasoning, and paying frontier prices
    #           for them multiplies cost with no quality payoff a user
    #           would notice.
    #   DEEP -- longer, more nuanced, higher-stakes generations: the 5-way
    #           multi-perspective draft/waiver analysis, the consensus
    #           synthesis across those 5 perspectives, top-3 draft-pick
    #           recommendations, and trade proposals that weigh multiple
    #           rosters against each other. These genuinely benefit from
    #           stronger reasoning -- they compare/rank multiple players or
    #           reconcile conflicting viewpoints, and sit closer to the
    #           product's core value proposition, so it's worth paying more
    #           for quality here.
    #
    # Pricing/capability verified live via WebFetch against
    # developers.openai.com (official OpenAI docs) and the current Anthropic
    # model catalog on 2026-08-22 -- both prior defaults ("gpt-4" and
    # "claude-3-sonnet-20240229") were stale: gpt-4 predates the entire
    # GPT-5 line, and claude-3-sonnet-20240229 is a retired Claude model.
    #
    #   gpt-5-mini        $0.25 / $2.00  per 1M tok -- OpenAI's cheap tier;
    #                      still reliable enough to follow the JSON-format
    #                      instructions the FAST calls below depend on.
    #                      (gpt-5-nano is even cheaper at $0.05/$0.40 and is
    #                      explicitly tuned for summarization/classification,
    #                      but is a riskier bet on structured JSON output --
    #                      several FAST-tier callers here parse the response
    #                      with json.loads(), so mini's extra headroom is
    #                      worth the small premium.)
    #   gpt-5.6-terra     $2.00 / $12.00 per 1M tok -- OpenAI's current
    #                      "balances intelligence and cost" flagship tier
    #                      (their own docs' framing). gpt-5.6-sol ($4/$20,
    #                      "frontier ... complex professional work") would be
    #                      overkill for a fantasy-football write-up.
    #   claude-haiku-4-5  $1.00 / $5.00  per 1M tok -- Anthropic's fastest,
    #                      most cost-effective model; explicitly positioned
    #                      for simple tasks.
    #   claude-sonnet-5   $3.00 / $15.00 per 1M tok (intro pricing $2/$10
    #                      through 2026-08-31) -- "near-Opus quality" on
    #                      reasoning/synthesis at a fraction of Opus 5's
    #                      $5/$25 or Fable 5's $10/$50 -- the same
    #                      "balanced flagship, not top-of-line" choice as
    #                      gpt-5.6-terra above.
    # -------------------------------------------------------------------
    FAST_OPENAI_MODEL = "gpt-5-mini"
    DEEP_OPENAI_MODEL = "gpt-5.6-terra"
    FAST_ANTHROPIC_MODEL = "claude-haiku-4-5"
    DEEP_ANTHROPIC_MODEL = "claude-sonnet-5"

    # Sentinel prefix _generate_with_fallback() returns only when *every*
    # configured provider genuinely failed. Callers that parse the response
    # (json.loads, etc.) check for this prefix first so a real, honest error
    # never gets reported as "failed to parse AI response".
    FAILURE_PREFIX = "AI generation failed: "

    DEFAULT_SYSTEM_PROMPT = "You are an expert fantasy football analyst."

    def __init__(self):
        self.openai_client = None
        self.anthropic_client = None

        if settings.OPENAI_API_KEY:
            self.openai_client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        if settings.ANTHROPIC_API_KEY:
            self.anthropic_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    # -------------------------------------------------------------------
    # Consolidated fallback primitive
    #
    # Every AI-generation method in this file (and
    # LeagueManagementService._analyze_current_matchup /
    # _analyze_position_group / _get_trade_recommendations) routes through
    # this single method instead of hand-rolling its own try-OpenAI-then-
    # Anthropic dance. That duplication is exactly what let
    # generate_multi_perspective_content and generate_consensus_recommendation
    # skip fallback entirely before this change -- they called
    # _generate_openai() directly with no fallback and no way to fall back,
    # so a rate-limited or unconfigured OpenAI client meant "OpenAI client
    # not configured" got embedded straight into what looked like real AI
    # analysis.
    # -------------------------------------------------------------------
    async def _generate_with_fallback(
        self,
        prompt: str,
        *,
        prefer_fast_model: bool = False,
        primary: AIProvider = AIProvider.OPENAI,
        system: str = DEFAULT_SYSTEM_PROMPT,
        max_tokens: int = 1000,
    ) -> str:
        """Try `primary`, falling back to the other configured provider on
        failure.

        Rate limits are detected specifically (openai.RateLimitError /
        anthropic.RateLimitError) so a 429 on the primary provider triggers
        an immediate, unambiguous fallback -- the scenario explicitly asked
        for. Any other failure (auth, network, malformed response, a
        provider simply not being configured, ...) also falls back,
        matching this app's prior broad-except behavior, just centralized
        in one place instead of duplicated per method. An auth/billing
        failure on the primary is *not* assumed to doom the secondary --
        they're different accounts on different providers -- so the
        secondary is still attempted.

        prefer_fast_model selects the cheap/fast model tier (see the
        FAST_*/DEEP_* constants and the comment above them) for short,
        low-stakes generations; the default is the stronger tier reserved
        for longer, more nuanced analysis.

        Returns the generated text, or -- only when every configured
        provider genuinely failed -- a clear, honest error string prefixed
        with FAILURE_PREFIX naming every provider attempted and why each one
        failed. Never silently fabricates a success.
        """
        other = AIProvider.ANTHROPIC if primary == AIProvider.OPENAI else AIProvider.OPENAI
        errors: List[str] = []

        for provider in (primary, other):
            client = self.openai_client if provider == AIProvider.OPENAI else self.anthropic_client
            if not client:
                errors.append(f"{provider.value}: not configured")
                continue

            model = self._model_for(provider, prefer_fast_model)
            try:
                if provider == AIProvider.OPENAI:
                    return await self._call_openai(prompt, model=model, max_tokens=max_tokens, system=system)
                else:
                    return await self._call_anthropic(prompt, model=model, max_tokens=max_tokens, system=system)
            except (openai.RateLimitError, anthropic.RateLimitError) as e:
                print(f"AI provider '{provider.value}' rate-limited ({model}); falling back")
                errors.append(f"{provider.value} rate-limited: {str(e)}")
            except Exception as e:
                print(f"AI provider '{provider.value}' failed ({type(e).__name__}: {str(e)}); falling back")
                errors.append(f"{provider.value} error ({type(e).__name__}): {str(e)}")

        return self.FAILURE_PREFIX + "; ".join(errors)

    def _model_for(self, provider: AIProvider, prefer_fast_model: bool) -> str:
        if provider == AIProvider.OPENAI:
            return self.FAST_OPENAI_MODEL if prefer_fast_model else self.DEEP_OPENAI_MODEL
        return self.FAST_ANTHROPIC_MODEL if prefer_fast_model else self.DEEP_ANTHROPIC_MODEL

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

        # A single player write-up from supplied data is a bounded
        # summarization task -- FAST tier. `provider` picks which one goes
        # first; the other is still tried as a fallback.
        return await self._generate_with_fallback(prompt, prefer_fast_model=True, primary=provider)

    async def generate_draft_recommendation(
        self,
        available_players: List[Dict[str, Any]],
        team_needs: List[str],
        draft_position: int,
        scoring_format: str = "PPR",
        points_per_reception: Optional[float] = None,
        scoring_rules: Optional[Dict[str, Any]] = None
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

        # Reception scoring is one knob among many real ones -- a league can
        # also reward/penalize pass completions, incompletions, attempts,
        # yardage, TDs, interceptions, and fumbles lost independently of
        # PPR (see app.services.scoring_rules; a real, live-verified example:
        # some leagues set Sleeper's `pass_cmp`/`pass_att` non-zero to reward
        # accurate, efficient QBs over high-volume ones). When the caller has
        # the connected league's real scoring_rules dict, state the notable
        # non-Standard rules explicitly so the model reasons about the
        # league's actual complete scoring picture, not just PPR -- this
        # extends scoring_description above rather than replacing it.
        scoring_rules_note = ""
        rules_summary = describe_scoring_rules(scoring_rules)
        if rules_summary:
            scoring_rules_note = (
                f"\n        This league's real scoring also: {rules_summary}. "
                "Factor this into player value -- e.g. a league that rewards "
                "completions and penalizes incompletions makes accurate, "
                "efficient QBs more valuable than high-volume, lower-accuracy "
                "ones, independent of raw passing yardage."
            )

        prompt = f"""
        Draft Assistant for {scoring_description}:{scoring_rules_note}

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

        if not self.openai_client and not self.anthropic_client:
            return {"recommendations": [], "error": "No AI provider available"}

        # Ranking/comparing multiple players for a live draft pick is
        # consequential and benefits from stronger reasoning -- DEEP tier.
        response = await self._generate_with_fallback(prompt, prefer_fast_model=False)
        if response.startswith(self.FAILURE_PREFIX):
            return {"recommendations": [], "error": response}

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

        if not self.openai_client and not self.anthropic_client:
            return []

        # Short, per-player waiver-wire blurbs -- FAST tier.
        response = await self._generate_with_fallback(prompt, prefer_fast_model=True)
        if response.startswith(self.FAILURE_PREFIX):
            print(f"Waiver analysis failed: {response}")
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

            # The flagship multi-perspective analysis -- genuinely nuanced
            # per-viewpoint reasoning -- DEEP tier.
            analysis = await self._generate_with_fallback(prompt, prefer_fast_model=False)
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

        # Synthesizing conflicting viewpoints into one recommendation --
        # DEEP tier.
        response = await self._generate_with_fallback(prompt, prefer_fast_model=False)
        if response.startswith(self.FAILURE_PREFIX):
            return {"error": response}

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return {"error": "Failed to generate consensus"}

    async def _call_openai(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1000,
        system: str = DEFAULT_SYSTEM_PROMPT,
    ) -> str:
        """Low-level OpenAI call. Raises on any failure -- never returns an
        error string. This is the single place that actually builds the
        OpenAI request; both _generate_openai() (legacy, non-raising) and
        _generate_with_fallback() (new, consolidated) call through here.

        The GPT-5 family (which every model this file uses belongs to --
        see FAST_OPENAI_MODEL / DEEP_OPENAI_MODEL above) rejects both
        `max_tokens` and a non-default `temperature` on Chat Completions:
        confirmed live while wiring this up -- with a real key configured,
        `max_tokens` 400s with "Unsupported parameter: 'max_tokens' is not
        supported with this model. Use 'max_completion_tokens' instead.",
        and any `temperature` other than the default (1) 400s with
        "Unsupported value: 'temperature' does not support ... Only the
        default (1) value is supported." Use `max_completion_tokens` and
        omit `temperature` entirely."""
        if not self.openai_client:
            raise RuntimeError("OpenAI client not configured")

        response = await self.openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=max_tokens
        )
        return response.choices[0].message.content

    async def _call_anthropic(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1000,
        system: str = DEFAULT_SYSTEM_PROMPT,
    ) -> str:
        """Low-level Anthropic call. Raises on any failure -- never returns
        an error string. Single place that builds the Anthropic request;
        see _call_openai() docstring for why this split exists.

        `temperature` is intentionally omitted: confirmed live against the
        installed anthropic SDK (1.0.0) that `messages.create()` no longer
        accepts it at all on current-generation models (TypeError at the
        Python level, before any request is even sent) -- matching the
        current Claude API's removal of temperature/top_p/top_k on
        Sonnet-5-and-later models."""
        if not self.anthropic_client:
            raise RuntimeError("Anthropic client not configured")

        response = await self.anthropic_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        # response.content is a list of content blocks (TextBlock,
        # ThinkingBlock, ...) -- guard on .type before reading .text rather
        # than indexing content[0] unconditionally.
        for block in response.content:
            if block.type == "text":
                return block.text
        raise RuntimeError("Anthropic response contained no text content")

    async def _generate_openai(self, prompt: str, model: str = DEEP_OPENAI_MODEL) -> str:
        """Direct, non-raising OpenAI call kept for existing callers that
        expect a returned string (including an error string) rather than a
        raised exception -- e.g. leagues.py's roster-analysis endpoint,
        which is intentionally left untouched here. New code should call
        _generate_with_fallback() instead, which adds the fallback-to-
        Anthropic behavior this method deliberately does not provide."""
        if not self.openai_client:
            return "OpenAI client not configured"

        try:
            return await self._call_openai(prompt, model=model)
        except Exception as e:
            return f"OpenAI API error: {str(e)}"

    async def _generate_anthropic(self, prompt: str, model: str = DEEP_ANTHROPIC_MODEL) -> str:
        """Direct, non-raising Anthropic call. See _generate_openai()
        docstring -- same rationale, kept for symmetry and any direct
        callers."""
        if not self.anthropic_client:
            return "Anthropic client not configured"

        try:
            return await self._call_anthropic(prompt, model=model)
        except Exception as e:
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
