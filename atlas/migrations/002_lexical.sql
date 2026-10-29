CREATE VIRTUAL TABLE chunk_search USING fts5(text, content='chunks', content_rowid='rowid');
CREATE TRIGGER chunks_search_insert AFTER INSERT ON chunks BEGIN
    INSERT INTO chunk_search(rowid, text) VALUES (new.rowid, new.text);
END;
CREATE TRIGGER chunks_search_delete AFTER DELETE ON chunks BEGIN
    INSERT INTO chunk_search(chunk_search, rowid, text) VALUES ('delete', old.rowid, old.text);
END;
CREATE TRIGGER chunks_search_update AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunk_search(chunk_search, rowid, text) VALUES ('delete', old.rowid, old.text);
    INSERT INTO chunk_search(rowid, text) VALUES (new.rowid, new.text);
END;
INSERT INTO chunk_search(chunk_search) VALUES ('rebuild');

