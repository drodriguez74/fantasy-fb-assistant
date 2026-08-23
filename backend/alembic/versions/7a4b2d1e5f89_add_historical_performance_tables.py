"""Add historical performance tables

Revision ID: 7a4b2d1e5f89
Revises: 862b67a8787f
Create Date: 2025-08-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '7a4b2d1e5f89'
down_revision = '862b67a8787f'
branch_labels = None
depends_on = None


def upgrade():
    # Create enum types (with conditional creation to avoid duplicates)
    op.execute("DO $$ BEGIN CREATE TYPE performancetype AS ENUM ('weekly', 'season', 'career'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE gamelocation AS ENUM ('home', 'away', 'neutral'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    
    # Create player_historical_performance table
    op.create_table('player_historical_performance',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('player_id', sa.Integer(), nullable=False),
    sa.Column('season', sa.Integer(), nullable=False),
    sa.Column('week', sa.Integer(), nullable=True),
    sa.Column('game_date', sa.DateTime(), nullable=True),
    sa.Column('opponent_team', sa.String(length=10), nullable=True),
    sa.Column('game_location', postgresql.ENUM('home', 'away', 'neutral', name='gamelocation', create_type=False), nullable=True),
    sa.Column('weather_conditions', sa.String(length=100), nullable=True),
    sa.Column('game_script', sa.String(length=50), nullable=True),
    sa.Column('fantasy_points_ppr', sa.Float(), nullable=True),
    sa.Column('fantasy_points_half_ppr', sa.Float(), nullable=True),
    sa.Column('fantasy_points_standard', sa.Float(), nullable=True),
    sa.Column('passing_stats', sa.JSON(), nullable=True),
    sa.Column('rushing_stats', sa.JSON(), nullable=True),
    sa.Column('receiving_stats', sa.JSON(), nullable=True),
    sa.Column('defensive_stats', sa.JSON(), nullable=True),
    sa.Column('kicking_stats', sa.JSON(), nullable=True),
    sa.Column('snap_count', sa.Integer(), nullable=True),
    sa.Column('snap_percentage', sa.Float(), nullable=True),
    sa.Column('target_share', sa.Float(), nullable=True),
    sa.Column('air_yards', sa.Float(), nullable=True),
    sa.Column('red_zone_targets', sa.Integer(), nullable=True),
    sa.Column('end_zone_targets', sa.Integer(), nullable=True),
    sa.Column('touches_when_ahead', sa.Integer(), nullable=True),
    sa.Column('touches_when_behind', sa.Integer(), nullable=True),
    sa.Column('fourth_quarter_usage', sa.Float(), nullable=True),
    sa.Column('yards_per_touch', sa.Float(), nullable=True),
    sa.Column('yards_after_contact', sa.Float(), nullable=True),
    sa.Column('drop_rate', sa.Float(), nullable=True),
    sa.Column('injury_designation', sa.String(length=20), nullable=True),
    sa.Column('games_missed_prior', sa.Integer(), nullable=True),
    sa.Column('performance_type', postgresql.ENUM('weekly', 'season', 'career', name='performancetype', create_type=False), nullable=False),
    sa.Column('is_playoffs', sa.Boolean(), default=False),
    sa.Column('data_source', sa.String(length=50), nullable=True),
    sa.Column('last_updated', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['player_id'], ['players.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_player_historical_performance_id'), 'player_historical_performance', ['id'], unique=False)
    op.create_index(op.f('ix_player_historical_performance_player_id'), 'player_historical_performance', ['player_id'], unique=False)
    op.create_index(op.f('ix_player_historical_performance_season'), 'player_historical_performance', ['season'], unique=False)
    op.create_index(op.f('ix_player_historical_performance_week'), 'player_historical_performance', ['week'], unique=False)

    # Create player_season_summaries table
    op.create_table('player_season_summaries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('player_id', sa.Integer(), nullable=False),
    sa.Column('season', sa.Integer(), nullable=False),
    sa.Column('games_played', sa.Integer(), nullable=False),
    sa.Column('games_started', sa.Integer(), nullable=True),
    sa.Column('total_fantasy_points_ppr', sa.Float(), nullable=True),
    sa.Column('total_fantasy_points_half_ppr', sa.Float(), nullable=True),
    sa.Column('total_fantasy_points_standard', sa.Float(), nullable=True),
    sa.Column('avg_fantasy_points_ppr', sa.Float(), nullable=True),
    sa.Column('avg_fantasy_points_half_ppr', sa.Float(), nullable=True),
    sa.Column('avg_fantasy_points_standard', sa.Float(), nullable=True),
    sa.Column('weekly_ceiling', sa.Float(), nullable=True),
    sa.Column('weekly_floor', sa.Float(), nullable=True),
    sa.Column('consistency_score', sa.Float(), nullable=True),
    sa.Column('boom_weeks', sa.Integer(), nullable=True),
    sa.Column('bust_weeks', sa.Integer(), nullable=True),
    sa.Column('first_half_avg', sa.Float(), nullable=True),
    sa.Column('second_half_avg', sa.Float(), nullable=True),
    sa.Column('trend_direction', sa.String(length=20), nullable=True),
    sa.Column('vs_top_defenses_avg', sa.Float(), nullable=True),
    sa.Column('vs_bottom_defenses_avg', sa.Float(), nullable=True),
    sa.Column('home_game_avg', sa.Float(), nullable=True),
    sa.Column('away_game_avg', sa.Float(), nullable=True),
    sa.Column('injury_weeks_missed', sa.Integer(), nullable=True),
    sa.Column('injury_weeks_limited', sa.Integer(), nullable=True),
    sa.Column('health_grade', sa.String(length=2), nullable=True),
    sa.Column('breakout_score', sa.Float(), nullable=True),
    sa.Column('sustainability_score', sa.Float(), nullable=True),
    sa.Column('position_finish', sa.Integer(), nullable=True),
    sa.Column('position_finish_half_season', sa.Integer(), nullable=True),
    sa.Column('adp_vs_finish', sa.Float(), nullable=True),
    sa.Column('last_updated', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['player_id'], ['players.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_player_season_summaries_id'), 'player_season_summaries', ['id'], unique=False)
    op.create_index(op.f('ix_player_season_summaries_player_id'), 'player_season_summaries', ['player_id'], unique=False)
    op.create_index(op.f('ix_player_season_summaries_season'), 'player_season_summaries', ['season'], unique=False)

    # Create player_trends table
    op.create_table('player_trends',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('player_id', sa.Integer(), nullable=False),
    sa.Column('trend_start_date', sa.DateTime(), nullable=False),
    sa.Column('trend_end_date', sa.DateTime(), nullable=False),
    sa.Column('trend_type', sa.String(length=50), nullable=False),
    sa.Column('trend_direction', sa.String(length=20), nullable=False),
    sa.Column('trend_strength', sa.Float(), nullable=True),
    sa.Column('performance_change', sa.Float(), nullable=True),
    sa.Column('usage_trend', sa.Float(), nullable=True),
    sa.Column('efficiency_trend', sa.Float(), nullable=True),
    sa.Column('touchdown_trend', sa.Float(), nullable=True),
    sa.Column('health_trend', sa.String(length=20), nullable=True),
    sa.Column('team_situation_change', sa.Text(), nullable=True),
    sa.Column('competition_change', sa.Text(), nullable=True),
    sa.Column('schedule_strength_change', sa.Float(), nullable=True),
    sa.Column('sustainability_score', sa.Float(), nullable=True),
    sa.Column('regression_likelihood', sa.Float(), nullable=True),
    sa.Column('breakout_probability', sa.Float(), nullable=True),
    sa.Column('confidence_level', sa.Float(), nullable=True),
    sa.Column('sample_size', sa.Integer(), nullable=True),
    sa.Column('last_updated', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['player_id'], ['players.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_player_trends_id'), 'player_trends', ['id'], unique=False)
    op.create_index(op.f('ix_player_trends_player_id'), 'player_trends', ['player_id'], unique=False)

    # Create matchup_histories table
    op.create_table('matchup_histories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('season', sa.Integer(), nullable=False),
    sa.Column('week', sa.Integer(), nullable=False),
    sa.Column('team_a', sa.String(length=10), nullable=False),
    sa.Column('team_b', sa.String(length=10), nullable=False),
    sa.Column('game_date', sa.DateTime(), nullable=False),
    sa.Column('final_score_a', sa.Integer(), nullable=True),
    sa.Column('final_score_b', sa.Integer(), nullable=True),
    sa.Column('total_points', sa.Integer(), nullable=True),
    sa.Column('game_script', sa.String(length=50), nullable=True),
    sa.Column('qb_fantasy_allowed_a', sa.Float(), nullable=True),
    sa.Column('qb_fantasy_allowed_b', sa.Float(), nullable=True),
    sa.Column('rb_fantasy_allowed_a', sa.Float(), nullable=True),
    sa.Column('rb_fantasy_allowed_b', sa.Float(), nullable=True),
    sa.Column('wr_fantasy_allowed_a', sa.Float(), nullable=True),
    sa.Column('wr_fantasy_allowed_b', sa.Float(), nullable=True),
    sa.Column('te_fantasy_allowed_a', sa.Float(), nullable=True),
    sa.Column('te_fantasy_allowed_b', sa.Float(), nullable=True),
    sa.Column('weather', sa.String(length=100), nullable=True),
    sa.Column('temperature', sa.Integer(), nullable=True),
    sa.Column('wind_speed', sa.Integer(), nullable=True),
    sa.Column('precipitation', sa.String(length=50), nullable=True),
    sa.Column('dome_game', sa.Boolean(), default=False),
    sa.Column('data_source', sa.String(length=50), nullable=True),
    sa.Column('last_updated', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_matchup_histories_id'), 'matchup_histories', ['id'], unique=False)
    op.create_index(op.f('ix_matchup_histories_season'), 'matchup_histories', ['season'], unique=False)
    op.create_index(op.f('ix_matchup_histories_team_a'), 'matchup_histories', ['team_a'], unique=False)
    op.create_index(op.f('ix_matchup_histories_team_b'), 'matchup_histories', ['team_b'], unique=False)
    op.create_index(op.f('ix_matchup_histories_week'), 'matchup_histories', ['week'], unique=False)

    # Create fantasy_league_histories table
    op.create_table('fantasy_league_histories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('season', sa.Integer(), nullable=False),
    sa.Column('league_platform', sa.String(length=20), nullable=False),
    sa.Column('league_external_id', sa.String(length=100), nullable=False),
    sa.Column('league_name', sa.String(length=200), nullable=True),
    sa.Column('league_size', sa.Integer(), nullable=True),
    sa.Column('scoring_format', sa.String(length=20), nullable=True),
    sa.Column('regular_season_wins', sa.Integer(), nullable=True),
    sa.Column('regular_season_losses', sa.Integer(), nullable=True),
    sa.Column('playoff_finish', sa.Integer(), nullable=True),
    sa.Column('total_points_for', sa.Float(), nullable=True),
    sa.Column('total_points_against', sa.Float(), nullable=True),
    sa.Column('regular_season_rank', sa.Integer(), nullable=True),
    sa.Column('points_for_rank', sa.Integer(), nullable=True),
    sa.Column('efficiency_rank', sa.Integer(), nullable=True),
    sa.Column('draft_grade', sa.String(length=2), nullable=True),
    sa.Column('draft_value_generated', sa.Float(), nullable=True),
    sa.Column('best_draft_pick', sa.String(length=100), nullable=True),
    sa.Column('worst_draft_pick', sa.String(length=100), nullable=True),
    sa.Column('waiver_moves', sa.Integer(), nullable=True),
    sa.Column('trades_made', sa.Integer(), nullable=True),
    sa.Column('optimal_lineup_percentage', sa.Float(), nullable=True),
    sa.Column('highest_weekly_score', sa.Float(), nullable=True),
    sa.Column('lowest_weekly_score', sa.Float(), nullable=True),
    sa.Column('most_bench_points', sa.Float(), nullable=True),
    sa.Column('last_updated', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_fantasy_league_histories_id'), 'fantasy_league_histories', ['id'], unique=False)
    op.create_index(op.f('ix_fantasy_league_histories_season'), 'fantasy_league_histories', ['season'], unique=False)
    op.create_index(op.f('ix_fantasy_league_histories_user_id'), 'fantasy_league_histories', ['user_id'], unique=False)


def downgrade():
    # Drop tables
    op.drop_index(op.f('ix_fantasy_league_histories_user_id'), table_name='fantasy_league_histories')
    op.drop_index(op.f('ix_fantasy_league_histories_season'), table_name='fantasy_league_histories')
    op.drop_index(op.f('ix_fantasy_league_histories_id'), table_name='fantasy_league_histories')
    op.drop_table('fantasy_league_histories')
    
    op.drop_index(op.f('ix_matchup_histories_week'), table_name='matchup_histories')
    op.drop_index(op.f('ix_matchup_histories_team_b'), table_name='matchup_histories')
    op.drop_index(op.f('ix_matchup_histories_team_a'), table_name='matchup_histories')
    op.drop_index(op.f('ix_matchup_histories_season'), table_name='matchup_histories')
    op.drop_index(op.f('ix_matchup_histories_id'), table_name='matchup_histories')
    op.drop_table('matchup_histories')
    
    op.drop_index(op.f('ix_player_trends_player_id'), table_name='player_trends')
    op.drop_index(op.f('ix_player_trends_id'), table_name='player_trends')
    op.drop_table('player_trends')
    
    op.drop_index(op.f('ix_player_season_summaries_season'), table_name='player_season_summaries')
    op.drop_index(op.f('ix_player_season_summaries_player_id'), table_name='player_season_summaries')
    op.drop_index(op.f('ix_player_season_summaries_id'), table_name='player_season_summaries')
    op.drop_table('player_season_summaries')
    
    op.drop_index(op.f('ix_player_historical_performance_week'), table_name='player_historical_performance')
    op.drop_index(op.f('ix_player_historical_performance_season'), table_name='player_historical_performance')
    op.drop_index(op.f('ix_player_historical_performance_player_id'), table_name='player_historical_performance')
    op.drop_index(op.f('ix_player_historical_performance_id'), table_name='player_historical_performance')
    op.drop_table('player_historical_performance')
    
    # Drop enum types
    op.execute("DROP TYPE performancetype")
    op.execute("DROP TYPE gamelocation")