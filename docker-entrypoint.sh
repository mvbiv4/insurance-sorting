#!/bin/sh
set -e

# Initialize DB on startup (not per-request)
python -c "from src import db; conn = db.get_connection(); db.init_db(conn); conn.close()"

exec "$@"
