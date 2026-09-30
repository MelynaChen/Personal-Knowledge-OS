from pathlib import Path

from sqlalchemy.dialects import sqlite
from sqlalchemy.schema import CreateIndex, CreateTable

from app.database.base import Base
import app.models  # noqa: F401


def sql_literal(sql: str) -> str:
    return repr(sql)


tables = list(Base.metadata.sorted_tables)
dialect = sqlite.dialect()
lines = ['"""Initial SQLite schema."""', '', 'from alembic import op', '',
         'revision = "0001_initial"', 'down_revision = None',
         'branch_labels = None', 'depends_on = None', '', '', 'def upgrade():']
for table in tables:
    lines.append(f"    op.execute({sql_literal(str(CreateTable(table).compile(dialect=dialect)))})")
    for index in table.indexes:
        lines.append(f"    op.execute({sql_literal(str(CreateIndex(index).compile(dialect=dialect)))})")
lines.extend(['', '', 'def downgrade():'])
for table in reversed(tables):
    lines.append(f'    op.execute("DROP TABLE {table.name}")')
Path('alembic/versions').mkdir(parents=True, exist_ok=True)
Path('alembic/versions/0001_initial.py').write_text('\n'.join(lines) + '\n', encoding='utf-8')
