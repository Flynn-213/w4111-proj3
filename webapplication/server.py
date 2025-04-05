"""
Columbia's COMS W4111.001 Introduction to Databases
Music Recommendation System Web Server
"""
import os
from sqlalchemy import *
from sqlalchemy.pool import NullPool
from flask import Flask, request, render_template, g, redirect, Response, session

tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app = Flask(__name__, template_folder=tmpl_dir)
app.secret_key = os.urandom(24)  # Required for session management

# Database configuration
DATABASE_USERNAME = "zf2342"
DATABASE_PASSWRD = "your_password"
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

# Authentication routes
@app.route('/', methods=['GET', 'POST'])
def index():
    if 'user_id' in session:
        return redirect('/recommendations')
    
    if request.method == 'POST':
        email = request.form['email']
        name = request.form['name']
        
        try:
            # Check if user exists
            user = g.conn.execute(text("""
                SELECT user_id FROM "User"
                WHERE user_email = :email
            """), {"email": email}).fetchone()
            
            if not user:
                # Create new user
                result = g.conn.execute(text("""
                    INSERT INTO "User" (user_name, user_email, registration_date)
                    VALUES (:name, :email, CURRENT_DATE)
                    RETURNING user_id
                """), {"name": name, "email": email})
                user_id = result.fetchone()[0]
                g.conn.commit()
            else:
                user_id = user[0]
            
            session['user_id'] = user_id
            return redirect('/recommendations')
        
        except Exception as e:
            print(f"Auth error: {str(e)}")
            return render_template("error.html", message="Authentication failed")
    
    return render_template("index.html")

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect('/')

# Search functionality
@app.route('/search', methods=['GET'])
def search():
    if 'user_id' not in session:
        return redirect('/')
    
    search_term = request.args.get('q', '')
    results = []
    
    try:
        query = text("""
            (SELECT track_id AS id, track_name AS name, 'track' AS type
             FROM Track WHERE track_name ILIKE :term)
            UNION
            (SELECT artist_id AS id, artist_name AS name, 'artist' AS type
             FROM Artist WHERE artist_name ILIKE :term)
            UNION
            (SELECT album_id AS id, album_name AS name, 'album' AS type
             FROM Album WHERE album_name ILIKE :term)
            UNION
            (SELECT genre_name AS id, genre_name AS name, 'genre' AS type
             FROM Genre WHERE genre_name ILIKE :term)
            LIMIT 20
        """)
        results = g.conn.execute(query, {"term": f"%{search_term}%"}).fetchall()
    
    except Exception as e:
        print(f"Search error: {str(e)}")
    
    return render_template("search.html", results=results, search_term=search_term)

# Recommendation engine
@app.route('/recommendations')
def recommendations():
    if 'user_id' not in session:
        return redirect('/')
    
    user_id = session['user_id']
    recommendations = []
    
    try:
        # Get artist-based recommendations
        artist_recs = g.conn.execute(text("""
            SELECT t.track_id, t.track_name, a.artist_name, 
                   'Same artist: ' || a.artist_name AS reason
            FROM Track t
            JOIN ArtistTrack at ON t.track_id = at.track_id
            JOIN Artist a ON at.artist_id = a.artist_id
            WHERE a.artist_id IN (
                SELECT artist_id FROM UserArtistPreference
                WHERE user_id = :user_id
            )
            AND t.track_id NOT IN (
                SELECT track_id FROM UserTrackPreference
                WHERE user_id = :user_id
            )
            LIMIT 5
        """), {"user_id": user_id}).fetchall()
        
        # Get genre-based recommendations
        genre_recs = g.conn.execute(text("""
            SELECT t.track_id, t.track_name, t.genre_name,
                   'Same genre: ' || t.genre_name AS reason
            FROM Track t
            WHERE t.genre_name IN (
                SELECT genre_name FROM UserGenrePreference
                WHERE user_id = :user_id
            )
            AND t.track_id NOT IN (
                SELECT track_id FROM UserTrackPreference
                WHERE user_id = :user_id
            )
            LIMIT 5
        """), {"user_id": user_id}).fetchall()
        
        recommendations = [dict(row) for row in artist_recs + genre_recs]
    
    except Exception as e:
        print(f"Recommendation error: {str(e)}")
    
    return render_template("recommendation.html", recommendations=recommendations)

# Preference management
@app.route('/preferences', methods=['GET', 'POST'])
def preferences():
    if 'user_id' not in session:
        return redirect('/')
    
    user_id = session['user_id']
    
    # Handle adding preferences
    if request.method == 'POST':
        item_id = request.form['item_id']
        pref_type = request.form['type']
        
        try:
            if pref_type == 'track':
                g.conn.execute(text("""
                    INSERT INTO UserTrackPreference (user_id, track_id)
                    VALUES (:user_id, :item_id)
                    ON CONFLICT DO NOTHING
                """), {"user_id": user_id, "item_id": item_id})
            elif pref_type == 'artist':
                g.conn.execute(text("""
                    INSERT INTO UserArtistPreference (user_id, artist_id)
                    VALUES (:user_id, :item_id)
                    ON CONFLICT DO NOTHING
                """), {"user_id": user_id, "item_id": item_id})
            elif pref_type == 'genre':
                g.conn.execute(text("""
                    INSERT INTO UserGenrePreference (user_id, genre_name)
                    VALUES (:user_id, :item_id)
                    ON CONFLICT DO NOTHING
                """), {"user_id": user_id, "item_id": item_id})
            
            g.conn.commit()
        
        except Exception as e:
            print(f"Preference error: {str(e)}")
    
    # Get current preferences
    try:
        tracks = g.conn.execute(text("""
            SELECT t.track_name FROM UserTrackPreference utp
            JOIN Track t ON utp.track_id = t.track_id
            WHERE utp.user_id = :user_id
        """), {"user_id": user_id}).fetchall()
        
        artists = g.conn.execute(text("""
            SELECT a.artist_name FROM UserArtistPreference uap
            JOIN Artist a ON uap.artist_id = a.artist_id
            WHERE uap.user_id = :user_id
        """), {"user_id": user_id}).fetchall()
        
        genres = g.conn.execute(text("""
            SELECT genre_name FROM UserGenrePreference
            WHERE user_id = :user_id
        """), {"user_id": user_id}).fetchall()
    
    except Exception as e:
        print(f"Preference fetch error: {str(e)}")
        tracks = artists = genres = []
    
    return render_template("preference.html",
                         tracks=[t[0] for t in tracks],
                         artists=[a[0] for a in artists],
                         genres=[g[0] for g in genres])

# Item detail pages
@app.route('/track/<track_id>')
def track_detail(track_id):
    try:
        track = g.conn.execute(text("""
            SELECT t.*, a.artist_name, al.album_name 
            FROM Track t
            JOIN ArtistTrack at ON t.track_id = at.track_id
            JOIN Artist a ON at.artist_id = a.artist_id
            LEFT JOIN Album al ON t.album_id = al.album_id
            WHERE t.track_id = :track_id
        """), {"track_id": track_id}).fetchone()
        
        return render_template("track.html", track=dict(track))
    
    except Exception as e:
        print(f"Track error: {str(e)}")
        return render_template("error.html", message="Track not found")

@app.route('/artist/<artist_id>')
def artist_detail(artist_id):
    try:
        artist = g.conn.execute(text("""
            SELECT * FROM Artist
            WHERE artist_id = :artist_id
        """), {"artist_id": artist_id}).fetchone()
        
        return render_template("artist.html", artist=dict(artist))
    
    except Exception as e:
        print(f"Artist error: {str(e)}")
        return render_template("error.html", message="Artist not found")

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8111, debug=True)