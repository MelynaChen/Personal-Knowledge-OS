"""Initial SQLite schema."""

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute('\nCREATE TABLE imports (\n\tid INTEGER NOT NULL, \n\traw_text TEXT NOT NULL, \n\tnormalized_json JSON NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tschema_version INTEGER NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tcompleted_at DATETIME, \n\tcreated_at DATETIME NOT NULL, \n\tupdated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n')
    op.execute('CREATE INDEX ix_imports_content_hash ON imports (content_hash)')
    op.execute('\nCREATE TABLE knowledge_nodes (\n\tid INTEGER NOT NULL, \n\tparent_id INTEGER, \n\tname VARCHAR(200) NOT NULL, \n\tnormalized_name VARCHAR(200) NOT NULL, \n\tpath_json JSON NOT NULL, \n\tdisplay_path TEXT NOT NULL, \n\tlevel INTEGER NOT NULL, \n\tnode_key VARCHAR(64) NOT NULL, \n\tcategory VARCHAR(100), \n\tdescription TEXT NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tupdated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_knowledge_child UNIQUE (parent_id, normalized_name), \n\tFOREIGN KEY(parent_id) REFERENCES knowledge_nodes (id), \n\tUNIQUE (node_key)\n)\n\n')
    op.execute('CREATE UNIQUE INDEX uq_knowledge_root ON knowledge_nodes (normalized_name) WHERE parent_id IS NULL')
    op.execute('CREATE INDEX ix_knowledge_nodes_parent_id ON knowledge_nodes (parent_id)')
    op.execute('\nCREATE TABLE notion_databases (\n\tid INTEGER NOT NULL, \n\tlogical_name VARCHAR(40) NOT NULL, \n\tdatabase_id VARCHAR(64), \n\tdata_source_id VARCHAR(64), \n\tproperty_ids_json JSON NOT NULL, \n\tinit_step VARCHAR(40) NOT NULL, \n\tschema_version INTEGER NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tupdated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (logical_name)\n)\n\n')
    op.execute('\nCREATE TABLE notion_objects (\n\tid INTEGER NOT NULL, \n\tobject_type VARCHAR(30) NOT NULL, \n\tlocal_id INTEGER NOT NULL, \n\texternal_id VARCHAR(64) NOT NULL, \n\tnotion_page_id VARCHAR(64), \n\tdata_source_id VARCHAR(64), \n\tbody_block_id VARCHAR(64), \n\tremote_edited_at DATETIME, \n\tsync_version INTEGER NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tupdated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (object_type, local_id), \n\tUNIQUE (notion_page_id)\n)\n\n')
    op.execute('CREATE INDEX ix_notion_objects_external_id ON notion_objects (external_id)')
    op.execute('\nCREATE TABLE settings (\n\t"key" VARCHAR(100) NOT NULL, \n\tvalue_json JSON NOT NULL, \n\tPRIMARY KEY ("key")\n)\n\n')
    op.execute('\nCREATE TABLE sync_operations (\n\tid INTEGER NOT NULL, \n\toperation_key VARCHAR(150) NOT NULL, \n\tobject_type VARCHAR(30) NOT NULL, \n\tlocal_id INTEGER NOT NULL, \n\tobject_version INTEGER NOT NULL, \n\tstep VARCHAR(50) NOT NULL, \n\trequest_json JSON, \n\tdepends_on_id INTEGER, \n\tstatus VARCHAR(20) NOT NULL, \n\tattempts INTEGER NOT NULL, \n\tnext_attempt_at DATETIME, \n\tlease_until DATETIME, \n\tresult_json JSON, \n\tcreated_at DATETIME NOT NULL, \n\tupdated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (operation_key), \n\tFOREIGN KEY(depends_on_id) REFERENCES sync_operations (id)\n)\n\n')
    op.execute('\nCREATE TABLE sync_logs (\n\tid INTEGER NOT NULL, \n\toperation_id INTEGER, \n\terror_category VARCHAR(50) NOT NULL, \n\thttp_status INTEGER, \n\tnotion_request_id VARCHAR(100), \n\tmessage TEXT NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(operation_id) REFERENCES sync_operations (id)\n)\n\n')
    op.execute('\nCREATE TABLE tasks (\n\tid INTEGER NOT NULL, \n\texternal_id VARCHAR(64) NOT NULL, \n\tdate DATE NOT NULL, \n\tname VARCHAR(200) NOT NULL, \n\tcategory VARCHAR(100) NOT NULL, \n\tpriority VARCHAR(20) NOT NULL, \n\tlearning_goal TEXT NOT NULL, \n\taction_steps_json JSON NOT NULL, \n\toutput_required TEXT NOT NULL, \n\tknowledge_node_id INTEGER NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tupdated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (external_id), \n\tFOREIGN KEY(knowledge_node_id) REFERENCES knowledge_nodes (id)\n)\n\n')
    op.execute('CREATE INDEX ix_tasks_date ON tasks (date)')
    op.execute('CREATE INDEX ix_tasks_knowledge_node_id ON tasks (knowledge_node_id)')
    op.execute('\nCREATE TABLE import_items (\n\tid INTEGER NOT NULL, \n\timport_id INTEGER NOT NULL, \n\titem_index INTEGER NOT NULL, \n\ttask_id INTEGER, \n\tstatus VARCHAR(20) NOT NULL, \n\tresult_json JSON, \n\tPRIMARY KEY (id), \n\tUNIQUE (import_id, item_index), \n\tFOREIGN KEY(import_id) REFERENCES imports (id), \n\tFOREIGN KEY(task_id) REFERENCES tasks (id)\n)\n\n')
    op.execute('CREATE INDEX ix_import_items_import_id ON import_items (import_id)')
    op.execute('\nCREATE TABLE notes (\n\tid INTEGER NOT NULL, \n\texternal_id VARCHAR(64) NOT NULL, \n\ttask_id INTEGER NOT NULL, \n\tknowledge_node_id INTEGER NOT NULL, \n\tdate DATE NOT NULL, \n\ttitle VARCHAR(200) NOT NULL, \n\tsummary TEXT NOT NULL, \n\tcontent_json JSON NOT NULL, \n\tcontent_hash VARCHAR(64) NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tupdated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (external_id), \n\tUNIQUE (task_id), \n\tFOREIGN KEY(task_id) REFERENCES tasks (id), \n\tFOREIGN KEY(knowledge_node_id) REFERENCES knowledge_nodes (id)\n)\n\n')
    op.execute('CREATE INDEX ix_notes_knowledge_node_id ON notes (knowledge_node_id)')
    op.execute('\nCREATE TABLE reviews (\n\tid INTEGER NOT NULL, \n\texternal_id VARCHAR(64) NOT NULL, \n\tnote_id INTEGER NOT NULL, \n\ttask_id INTEGER NOT NULL, \n\tknowledge_node_id INTEGER NOT NULL, \n\tinitial_learning_date DATE NOT NULL, \n\treview_level INTEGER NOT NULL, \n\tnext_review_date DATE NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tdifficulty VARCHAR(20) NOT NULL, \n\tmemory_score INTEGER, \n\tversion INTEGER NOT NULL, \n\talgorithm_version VARCHAR(20) NOT NULL, \n\talgorithm_config_json JSON NOT NULL, \n\tcreated_at DATETIME NOT NULL, \n\tupdated_at DATETIME NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (external_id), \n\tUNIQUE (note_id), \n\tFOREIGN KEY(note_id) REFERENCES notes (id), \n\tFOREIGN KEY(task_id) REFERENCES tasks (id), \n\tFOREIGN KEY(knowledge_node_id) REFERENCES knowledge_nodes (id)\n)\n\n')
    op.execute('CREATE INDEX ix_reviews_next_review_date ON reviews (next_review_date)')
    op.execute('CREATE INDEX ix_reviews_knowledge_node_id ON reviews (knowledge_node_id)')
    op.execute('\nCREATE TABLE review_events (\n\tid INTEGER NOT NULL, \n\treview_id INTEGER NOT NULL, \n\trequest_key VARCHAR(200) NOT NULL, \n\tmemory_score INTEGER NOT NULL, \n\told_level INTEGER NOT NULL, \n\tnew_level INTEGER NOT NULL, \n\told_next_review_date DATE NOT NULL, \n\tnew_next_review_date DATE NOT NULL, \n\tcompleted_at DATETIME NOT NULL, \n\talgorithm_version VARCHAR(20) NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (review_id, request_key), \n\tFOREIGN KEY(review_id) REFERENCES reviews (id)\n)\n\n')
    op.execute('CREATE INDEX ix_review_events_review_id ON review_events (review_id)')


def downgrade():
    op.execute("DROP TABLE review_events")
    op.execute("DROP TABLE reviews")
    op.execute("DROP TABLE notes")
    op.execute("DROP TABLE import_items")
    op.execute("DROP TABLE tasks")
    op.execute("DROP TABLE sync_logs")
    op.execute("DROP TABLE sync_operations")
    op.execute("DROP TABLE settings")
    op.execute("DROP TABLE notion_objects")
    op.execute("DROP TABLE notion_databases")
    op.execute("DROP TABLE knowledge_nodes")
    op.execute("DROP TABLE imports")
