import sqlite3
import sys

def build_fts_index(db_path='posa_wiki.db'):
    """
    Builds or rebuilds the Full-Text Search (FTS) index for the videos table.
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        print("Building FTS5 index for videos...")

        # Drop the existing FTS table if it exists to ensure a fresh build
        cursor.execute("DROP TABLE IF EXISTS videos_fts;")
        print("- Dropped existing index (if any).")

        # Create a new FTS5 virtual table.
        # We are linking it to the 'videos' table using the 'content' option.
        # This helps keep the FTS table synchronized with the main content.
        cursor.execute("""
        CREATE VIRTUAL TABLE videos_fts USING fts5(
            title, 
            description, 
            content='videos',
            content_rowid='rowid'
        );
        """)
        print("- Created new FTS5 virtual table 'videos_fts'.")

        # Populate the FTS table with all existing data from the videos table.
        # FTS5 automatically indexes the text columns specified during creation.
        cursor.execute("""
        INSERT INTO videos_fts(rowid, title, description) 
        SELECT rowid, title, description FROM videos;
        """)
        print(f"- Indexed {cursor.rowcount} records.")

        conn.commit()
        conn.close()
        
        print("\nFTS index built successfully.")

    except sqlite3.Error as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    build_fts_index()
