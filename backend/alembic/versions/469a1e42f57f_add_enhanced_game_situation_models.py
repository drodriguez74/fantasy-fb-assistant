"""Add enhanced game situation models

Revision ID: 469a1e42f57f
Revises: df6277376539
Create Date: 2025-08-21 22:11:43.131839

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '469a1e42f57f'
down_revision: Union[str, None] = 'df6277376539'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use string types for now to avoid enum conflicts
    pass

    # Create game_situations table
    op.create_table('game_situations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('game_id', sa.String(), nullable=False),
        sa.Column('week', sa.Integer(), nullable=False),
        sa.Column('season', sa.Integer(), nullable=False),
        sa.Column('is_home_game', sa.Boolean(), nullable=False),
        sa.Column('opponent_team', sa.String(), nullable=False),
        sa.Column('venue_name', sa.String(), nullable=True),
        sa.Column('venue_type', sa.String(), nullable=True),
        sa.Column('temperature', sa.Float(), nullable=True),
        sa.Column('humidity', sa.Float(), nullable=True),
        sa.Column('wind_speed', sa.Float(), nullable=True),
        sa.Column('weather_condition', sa.String(), nullable=True),
        sa.Column('precipitation', sa.Float(), nullable=True),
        sa.Column('game_script', sa.String(), nullable=True),
        sa.Column('time_of_possession', sa.Float(), nullable=True),
        sa.Column('team_score', sa.Integer(), nullable=True),
        sa.Column('opponent_score', sa.Integer(), nullable=True),
        sa.Column('point_differential', sa.Integer(), nullable=True),
        sa.Column('opponent_def_rank_vs_position', sa.Integer(), nullable=True),
        sa.Column('opponent_def_yards_allowed', sa.Float(), nullable=True),
        sa.Column('opponent_def_points_allowed', sa.Float(), nullable=True),
        sa.Column('opponent_def_takeaways', sa.Integer(), nullable=True),
        sa.Column('total_plays', sa.Integer(), nullable=True),
        sa.Column('pace_of_play', sa.Float(), nullable=True),
        sa.Column('red_zone_visits', sa.Integer(), nullable=True),
        sa.Column('third_down_conversions', sa.Integer(), nullable=True),
        sa.Column('total_third_downs', sa.Integer(), nullable=True),
        sa.Column('is_prime_time', sa.Boolean(), nullable=True, default=False),
        sa.Column('is_division_rival', sa.Boolean(), nullable=True, default=False),
        sa.Column('is_playoff_game', sa.Boolean(), nullable=True, default=False),
        sa.Column('days_rest', sa.Integer(), nullable=True),
        sa.Column('fantasy_points', sa.Float(), nullable=True),
        sa.Column('targets', sa.Integer(), nullable=True),
        sa.Column('carries', sa.Integer(), nullable=True),
        sa.Column('snaps_played', sa.Integer(), nullable=True),
        sa.Column('snap_percentage', sa.Float(), nullable=True),
        sa.Column('target_share', sa.Float(), nullable=True),
        sa.Column('air_yards_share', sa.Float(), nullable=True),
        sa.Column('red_zone_targets', sa.Integer(), nullable=True),
        sa.Column('goal_line_carries', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_game_situations_id'), 'game_situations', ['id'], unique=False)
    op.create_index(op.f('ix_game_situations_player_id'), 'game_situations', ['player_id'], unique=False)

    # Create defensive_rankings table
    op.create_table('defensive_rankings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team', sa.String(), nullable=False),
        sa.Column('season', sa.Integer(), nullable=False),
        sa.Column('week', sa.Integer(), nullable=False),
        sa.Column('overall_def_rank', sa.Integer(), nullable=True),
        sa.Column('points_allowed_rank', sa.Integer(), nullable=True),
        sa.Column('yards_allowed_rank', sa.Integer(), nullable=True),
        sa.Column('qb_fantasy_rank', sa.Integer(), nullable=True),
        sa.Column('rb_fantasy_rank', sa.Integer(), nullable=True),
        sa.Column('wr_fantasy_rank', sa.Integer(), nullable=True),
        sa.Column('te_fantasy_rank', sa.Integer(), nullable=True),
        sa.Column('pass_def_rank', sa.Integer(), nullable=True),
        sa.Column('rush_def_rank', sa.Integer(), nullable=True),
        sa.Column('red_zone_def_rank', sa.Integer(), nullable=True),
        sa.Column('third_down_def_rank', sa.Integer(), nullable=True),
        sa.Column('qb_points_allowed', sa.Float(), nullable=True),
        sa.Column('rb_points_allowed', sa.Float(), nullable=True),
        sa.Column('wr_points_allowed', sa.Float(), nullable=True),
        sa.Column('te_points_allowed', sa.Float(), nullable=True),
        sa.Column('pressure_rate', sa.Float(), nullable=True),
        sa.Column('blitz_rate', sa.Float(), nullable=True),
        sa.Column('man_coverage_rate', sa.Float(), nullable=True),
        sa.Column('zone_coverage_rate', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_defensive_rankings_id'), 'defensive_rankings', ['id'], unique=False)

    # Create venue_data table
    op.create_table('venue_data',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('venue_name', sa.String(), nullable=False),
        sa.Column('team', sa.String(), nullable=False),
        sa.Column('city', sa.String(), nullable=False),
        sa.Column('state', sa.String(), nullable=True),
        sa.Column('venue_type', sa.String(), nullable=False),
        sa.Column('capacity', sa.Integer(), nullable=True),
        sa.Column('elevation', sa.Float(), nullable=True),
        sa.Column('avg_temperature', sa.Float(), nullable=True),
        sa.Column('avg_humidity', sa.Float(), nullable=True),
        sa.Column('avg_wind_speed', sa.Float(), nullable=True),
        sa.Column('surface_type', sa.String(), nullable=True),
        sa.Column('is_offense_friendly', sa.Boolean(), nullable=True, default=True),
        sa.Column('historical_scoring_factor', sa.Float(), nullable=True, default=1.0),
        sa.Column('has_retractable_roof', sa.Boolean(), nullable=True, default=False),
        sa.Column('typical_weather_impact', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('venue_name')
    )
    op.create_index(op.f('ix_venue_data_id'), 'venue_data', ['id'], unique=False)

    # Create weather_history table
    op.create_table('weather_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('game_id', sa.String(), nullable=False),
        sa.Column('venue_name', sa.String(), nullable=False),
        sa.Column('game_date', sa.DateTime(), nullable=False),
        sa.Column('temperature', sa.Float(), nullable=True),
        sa.Column('humidity', sa.Float(), nullable=True),
        sa.Column('wind_speed', sa.Float(), nullable=True),
        sa.Column('wind_direction', sa.String(), nullable=True),
        sa.Column('weather_condition', sa.String(), nullable=True),
        sa.Column('precipitation', sa.Float(), nullable=True),
        sa.Column('visibility', sa.Float(), nullable=True),
        sa.Column('weather_severity_score', sa.Float(), nullable=True),
        sa.Column('expected_fantasy_impact', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_weather_history_id'), 'weather_history', ['id'], unique=False)

    # Create situational_trends table
    op.create_table('situational_trends',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('situation_type', sa.String(), nullable=False),
        sa.Column('situation_value', sa.String(), nullable=False),
        sa.Column('games_played', sa.Integer(), nullable=True, default=0),
        sa.Column('avg_fantasy_points', sa.Float(), nullable=True, default=0.0),
        sa.Column('total_fantasy_points', sa.Float(), nullable=True, default=0.0),
        sa.Column('std_deviation', sa.Float(), nullable=True, default=0.0),
        sa.Column('avg_targets', sa.Float(), nullable=True, default=0.0),
        sa.Column('avg_carries', sa.Float(), nullable=True, default=0.0),
        sa.Column('avg_snap_percentage', sa.Float(), nullable=True, default=0.0),
        sa.Column('games_over_projection', sa.Integer(), nullable=True, default=0),
        sa.Column('boom_games', sa.Integer(), nullable=True, default=0),
        sa.Column('bust_games', sa.Integer(), nullable=True, default=0),
        sa.Column('recent_performance', sa.Float(), nullable=True, default=0.0),
        sa.Column('trend_direction', sa.String(), nullable=True),
        sa.Column('sample_size_confidence', sa.Float(), nullable=True, default=0.0),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_situational_trends_id'), 'situational_trends', ['id'], unique=False)
    op.create_index(op.f('ix_situational_trends_player_id'), 'situational_trends', ['player_id'], unique=False)


def downgrade() -> None:
    # Drop all tables and enums in reverse order
    op.drop_index(op.f('ix_situational_trends_player_id'), table_name='situational_trends')
    op.drop_index(op.f('ix_situational_trends_id'), table_name='situational_trends')
    op.drop_table('situational_trends')
    
    op.drop_index(op.f('ix_weather_history_id'), table_name='weather_history')
    op.drop_table('weather_history')
    
    op.drop_index(op.f('ix_venue_data_id'), table_name='venue_data')
    op.drop_table('venue_data')
    
    op.drop_index(op.f('ix_defensive_rankings_id'), table_name='defensive_rankings')
    op.drop_table('defensive_rankings')
    
    op.drop_index(op.f('ix_game_situations_player_id'), table_name='game_situations')
    op.drop_index(op.f('ix_game_situations_id'), table_name='game_situations')
    op.drop_table('game_situations')
    
    # No enums to drop since we used strings