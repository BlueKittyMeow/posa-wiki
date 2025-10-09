
import sqlite3
import sys


def build_fts_index(db_path='posa_wiki.db'):
    """Build or rebuild the Full-Text Search (FTS) index for the videos table."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        print("Building FTS5 index for videos...")

        # Drop existing maintenance triggers before rebuilding
        cursor.executescript("""
        DROP TRIGGER IF EXISTS videos_ai;
        DROP TRIGGER IF EXISTS videos_ad;
        DROP TRIGGER IF EXISTS videos_au;
        """)
        print("- Removed existing FTS maintenance triggers.")

        # Drop the existing FTS table if it exists to ensure a fresh build
        cursor.execute("DROP TABLE IF EXISTS videos_fts;")
        print("- Dropped existing index (if any).")

        # Create a new FTS5 virtual table linked to the videos table
        cursor.execute("""
        CREATE VIRTUAL TABLE videos_fts USING fts5(
            title,
            description,
            content='videos',
            content_rowid='rowid'
        );
        """)
        print("- Created new FTS5 virtual table 'videos_fts'.")

        # Seed the FTS table with current video data
        cursor.execute("""
        INSERT INTO videos_fts(rowid, title, description)
        SELECT rowid, title, description FROM videos;
        """)
        print(f"- Indexed {cursor.rowcount} records.")

        # Create triggers to keep the FTS table in sync with the videos table
        cursor.executescript("""
        CREATE TRIGGER videos_ai AFTER INSERT ON videos BEGIN
            INSERT INTO videos_fts(rowid, title, description)
            VALUES (new.rowid, new.title, new.description);
        END;

        CREATE TRIGGER videos_ad AFTER DELETE ON videos BEGIN
            DELETE FROM videos_fts WHERE rowid = old.rowid;
        END;

        CREATE TRIGGER videos_au AFTER UPDATE ON videos BEGIN
            UPDATE videos_fts
            SET title = new.title,
                description = new.description
            WHERE rowid = new.rowid;
        END;
        """)
        print("- Created FTS maintenance triggers.")

        conn.commit()
        conn.close()

        print("\nFTS index built successfully.")

    except sqlite3.Error as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    build_fts_index()
