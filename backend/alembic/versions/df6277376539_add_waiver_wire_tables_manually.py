"""Add waiver wire tables manually

Revision ID: df6277376539
Revises: 8f2a4c5d6e91
Create Date: 2025-08-17 18:58:30.628232

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'df6277376539'
down_revision: Union[str, None] = '8f2a4c5d6e91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the enum types first
    op.execute("CREATE TYPE recommendationtype AS ENUM ('add', 'drop', 'stash', 'avoid')")
    op.execute("CREATE TYPE priority AS ENUM ('urgent', 'high', 'medium', 'low', 'watch')")
    
    # Use raw SQL to create tables to avoid enum conflicts
    op.execute("""
        CREATE TABLE waiver_wire_recommendations (
            id SERIAL PRIMARY KEY,
            player_id INTEGER NOT NULL REFERENCES players(id),
            week INTEGER NOT NULL,
            season INTEGER NOT NULL,
            recommendation_type recommendationtype NOT NULL,
            priority priority NOT NULL,
            confidence_score FLOAT NOT NULL,
            reason TEXT NOT NULL,
            projected_points FLOAT,
            ownership_percentage FLOAT,
            trend_direction VARCHAR(10),
            injury_related BOOLEAN DEFAULT FALSE,
            matchup_driven BOOLEAN DEFAULT FALSE,
            target_share_increase BOOLEAN DEFAULT FALSE,
            volume_increase BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    op.execute("""
        CREATE TABLE waiver_wire_trends (
            id SERIAL PRIMARY KEY,
            player_id INTEGER NOT NULL REFERENCES players(id),
            week INTEGER NOT NULL,
            season INTEGER NOT NULL,
            ownership_change FLOAT NOT NULL,
            pickup_rate FLOAT NOT NULL,
            drop_rate FLOAT NOT NULL,
            recent_performance FLOAT,
            upcoming_matchup_rating FLOAT,
            target_share_trend FLOAT,
            snap_count_trend FLOAT,
            red_zone_trend FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    op.execute("""
        CREATE TABLE player_evaluations (
            id SERIAL PRIMARY KEY,
            player_id INTEGER NOT NULL REFERENCES players(id),
            week INTEGER NOT NULL,
            season INTEGER NOT NULL,
            projected_points FLOAT NOT NULL,
            floor_projection FLOAT NOT NULL,
            ceiling_projection FLOAT NOT NULL,
            target_share FLOAT,
            snap_percentage FLOAT,
            red_zone_opportunities INTEGER,
            goal_line_carries INTEGER,
            matchup_rating FLOAT,
            opposing_defense_rank INTEGER,
            home_away VARCHAR(4),
            injury_report_status VARCHAR(20),
            weather_concerns BOOLEAN DEFAULT FALSE,
            game_script_favorable BOOLEAN DEFAULT FALSE,
            performance_trend FLOAT,
            usage_trend FLOAT,
            efficiency_trend FLOAT,
            breakout_probability FLOAT DEFAULT 0.0,
            bust_probability FLOAT DEFAULT 0.0,
            consistency_score FLOAT DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    op.execute("""
        CREATE TABLE waiver_wire_alerts (
            id SERIAL PRIMARY KEY,
            player_id INTEGER NOT NULL REFERENCES players(id),
            week INTEGER NOT NULL,
            season INTEGER NOT NULL,
            alert_type VARCHAR(50) NOT NULL,
            title VARCHAR(200) NOT NULL,
            message TEXT NOT NULL,
            urgency priority NOT NULL,
            expires_at TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            trigger_event VARCHAR(100),
            ownership_threshold FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            acknowledged_at TIMESTAMP
        );
    """)
    
    # Create indexes
    op.create_index(op.f('ix_waiver_wire_recommendations_id'), 'waiver_wire_recommendations', ['id'], unique=False)
    op.create_index(op.f('ix_waiver_wire_trends_id'), 'waiver_wire_trends', ['id'], unique=False)
    op.create_index(op.f('ix_player_evaluations_id'), 'player_evaluations', ['id'], unique=False)
    op.create_index(op.f('ix_waiver_wire_alerts_id'), 'waiver_wire_alerts', ['id'], unique=False)


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_index(op.f('ix_waiver_wire_alerts_id'), table_name='waiver_wire_alerts')
    op.drop_table('waiver_wire_alerts')
    
    op.drop_index(op.f('ix_player_evaluations_id'), table_name='player_evaluations')
    op.drop_table('player_evaluations')
    
    op.drop_index(op.f('ix_waiver_wire_trends_id'), table_name='waiver_wire_trends')
    op.drop_table('waiver_wire_trends')
    
    op.drop_index(op.f('ix_waiver_wire_recommendations_id'), table_name='waiver_wire_recommendations')
    op.drop_table('waiver_wire_recommendations')
    
    # Drop enums
    op.execute('DROP TYPE IF EXISTS priority;')
    op.execute('DROP TYPE IF EXISTS recommendationtype;')