
"""
Columbia's COMS W4111.001 Introduction to Databases
Example Webserver
To run locally:
    python server.py
Go to http://localhost:8111 in your browser.
A debugger such as "pdb" may be helpful for debugging.
Read about it online.
"""
import os
  # accessible as a variable in index.html:
from sqlalchemy import *
from sqlalchemy.pool import NullPool
from flask import Flask, request, render_template, g, redirect, Response

tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app = Flask(__name__, template_folder=tmpl_dir)

DATABASE_USERNAME = "zf2342"
DATABASE_PASSWRD = "399067"
DATABASE_HOST = "34.148.223.31"
DATABASEURI = f"postgresql://{DATABASE_USERNAME}:{DATABASE_PASSWRD}@{DATABASE_HOST}/proj1part2"

engine = create_engine(DATABASEURI)

@app.before_request
def before_request():
    try:
        g.conn = engine.connect()
    except:
        print("Database connection error")
        g.conn = None

@app.teardown_request
def teardown_request(exception):
    try:
        g.conn.close()
    except Exception as e:
        pass
@app.route('/')
def index():
    """Main page showing personalized recommendations"""
    try:
        # Get recommendations for user 1 (example user)
        query = text("""
            SELECT r.rec_id, t.track_name, a.artist_name, g.genre_name, r.rec_reason 
            FROM Recommendation r
            JOIN Track t ON r.track_id = t.track_id
            JOIN ArtistTrack at ON t.track_id = at.track_id
            JOIN Artist a ON at.artist_id = a.artist_id
            JOIN Genre g ON t.genre_id = g.genre_id
            WHERE r.user_id = 1
            ORDER BY r.generated_at DESC
            LIMIT 10
        """)
        cursor = g.conn.execute(query)
        recommendations = [dict(row) for row in cursor.mappings()]
        return render_template("index.html", recommendations=recommendations)
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return render_template("error.html", message="Failed to load recommendations")

@app.route('/search', methods=['GET'])
def search():
    """Handle music search functionality"""
    try:
        search_term = request.args.get('q', '').strip()
        if not search_term:
            return redirect('/')
        
        query = text("""
            SELECT t.track_id, t.track_name, a.artist_name, g.genre_name, t.track_popularity
            FROM Track t
            JOIN ArtistTrack at ON t.track_id = at.track_id
            JOIN Artist a ON at.artist_id = a.artist_id
            JOIN Genre g ON t.genre_id = g.genre_id
            WHERE t.track_name ILIKE :term OR a.artist_name ILIKE :term
            LIMIT 20
        """)
        cursor = g.conn.execute(query, {"term": f"%{search_term}%"})
        results = [dict(row) for row in cursor.mappings()]
        return render_template("search.html", results=results, search_term=search_term)
    
    except Exception as e:
        print(f"Search error: {str(e)}")
        return render_template("error.html", message="Search failed")

@app.route('/feedback', methods=['POST'])
def handle_feedback():
    """Process user feedback on recommendations"""
    try:
        user_id = 1  # Hardcoded for example purposes
        track_id = request.form.get('track_id')
        action = request.form.get('action')
        
        if action not in ['like', 'skip'] or not track_id:
            return redirect('/')
        
        # Record user action
        query = text("""
            INSERT INTO UserAction (user_id, track_id, action_type)
            VALUES (:user_id, :track_id, :action)
        """)
        g.conn.execute(query, {
            "user_id": user_id,
            "track_id": track_id,
            "action": action
        })
        g.conn.commit()
        
        return redirect('/')
    
    except Exception as e:
        print(f"Feedback error: {str(e)}")
        return render_template("error.html", message="Failed to record feedback")

@app.route('/artist/<artist_id>')
def artist_detail(artist_id):
    """Display artist details and related tracks"""
    try:
        # Get artist info
        artist_query = text("""
            SELECT * FROM Artist 
            WHERE artist_id = :artist_id
        """)
        artist = g.conn.execute(artist_query, {"artist_id": artist_id}).fetchone()
        
        # Get artist's tracks
        tracks_query = text("""
            SELECT t.track_id, t.track_name, t.track_popularity 
            FROM Track t
            JOIN ArtistTrack at ON t.track_id = at.track_id
            WHERE at.artist_id = :artist_id
            ORDER BY t.track_popularity DESC
            LIMIT 10
        """)
        tracks = g.conn.execute(tracks_query, {"artist_id": artist_id}).fetchall()
        
        return render_template("artist.html", 
                             artist=dict(artist._mapping), 
                             tracks=[dict(row._mapping) for row in tracks])
    
    except Exception as e:
        print(f"Artist detail error: {str(e)}")
        return render_template("error.html", message="Artist not found")

@app.route('/user/preferences')
def user_preferences():
    """Display and update user preferences"""
    try:
        user_id = 1  # Example user
        
        # Get user preferences
        pref_query = text("""
            SELECT liked_genres, liked_artists 
            FROM UserPreference 
            WHERE user_id = :user_id
        """)
        preferences = g.conn.execute(pref_query, {"user_id": user_id}).fetchone()
        
        return render_template("preferences.html", 
                             preferences=dict(preferences._mapping) if preferences else None)
    
    except Exception as e:
        print(f"Preferences error: {str(e)}")
        return render_template("error.html", message="Failed to load preferences")

if __name__ == "__main__":
    import click

    @click.command()
    @click.option('--debug', is_flag=True)
    @click.option('--threaded', is_flag=True)
    @click.argument('HOST', default='0.0.0.0')
    @click.argument('PORT', default=8111, type=int)
    def run(debug, threaded, host, port):
        HOST, PORT = host, port
        print("Starting server...")
        app.run(host=HOST, port=PORT, debug=debug, threaded=threaded)

    run()