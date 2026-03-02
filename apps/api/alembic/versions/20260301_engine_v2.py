"""engine v2: groove, hits, confidence vector, MIDI, octave correction

Revision ID: 20260301_engine_v2
Revises: (initial)
Create Date: 2026-03-01

Adds columns to analysis_results for:
  - onset_times_json
  - groove_profile_json, swing_ratio, groove_type
  - drum_hits_json, num_drum_hits
  - confidence_vector_json
  - raw_bpm, octave_correction_factor, tempo_candidates_json
  - midi_file_path
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers
revision = "20260301_engine_v2"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analysis_results", sa.Column("onset_times_json", JSON, nullable=True))
    op.add_column("analysis_results", sa.Column("groove_profile_json", JSON, nullable=True))
    op.add_column("analysis_results", sa.Column("swing_ratio", sa.Float, nullable=True))
    op.add_column("analysis_results", sa.Column("groove_type", sa.String(50), nullable=True))
    op.add_column("analysis_results", sa.Column("drum_hits_json", JSON, nullable=True))
    op.add_column("analysis_results", sa.Column("num_drum_hits", sa.Integer, nullable=True))
    op.add_column("analysis_results", sa.Column("confidence_vector_json", JSON, nullable=True))
    op.add_column("analysis_results", sa.Column("raw_bpm", sa.Float, nullable=True))
    op.add_column("analysis_results", sa.Column("octave_correction_factor", sa.Float, nullable=True))
    op.add_column("analysis_results", sa.Column("tempo_candidates_json", JSON, nullable=True))
    op.add_column("analysis_results", sa.Column("midi_file_path", sa.String(1000), nullable=True))


def downgrade() -> None:
    op.drop_column("analysis_results", "midi_file_path")
    op.drop_column("analysis_results", "tempo_candidates_json")
    op.drop_column("analysis_results", "octave_correction_factor")
    op.drop_column("analysis_results", "raw_bpm")
    op.drop_column("analysis_results", "confidence_vector_json")
    op.drop_column("analysis_results", "num_drum_hits")
    op.drop_column("analysis_results", "drum_hits_json")
    op.drop_column("analysis_results", "groove_type")
    op.drop_column("analysis_results", "swing_ratio")
    op.drop_column("analysis_results", "groove_profile_json")
    op.drop_column("analysis_results", "onset_times_json")
