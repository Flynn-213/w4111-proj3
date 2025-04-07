"""
Columbia's COMS W4111.001 Introduction to Databases
Music Recommendation System Web Server
"""
import os
import uuid
from sqlalchemy import *
from sqlalchemy.pool import NullPool
from flask import Flask, request, render_template, g, redirect, Response, session

tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app = Flask(__name__, template_folder=tmpl_dir)
app.secret_key = os.urandom(24)  # Required for session management

# Database configuration
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

@app.before_request
def method_override():
    if request.method == 'POST' and '_method' in request.form:
        request.environ['REQUEST_METHOD'] = request.form['_method'].upper()

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
            (SELECT track_id::TEXT AS id, track_name AS name, 'track' AS type
             FROM Track WHERE track_name ILIKE :term)
            UNION
            (SELECT artist_id::TEXT AS id, artist_name AS name, 'artist' AS type
             FROM Artist WHERE artist_name ILIKE :term)
            UNION
            (SELECT album_id::TEXT AS id, album_name AS name, 'album' AS type
             FROM Album WHERE album_name ILIKE :term)
            UNION
            (SELECT genre_name::TEXT AS id, genre_name AS name, 'genre' AS type
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
    """Generate personalized recommendations"""
    if 'user_id' not in session:
        return redirect('/')

    user_id = session['user_id']
    recommendations = []

    try:
        # Artist-based recommendations
        artist_recs = g.conn.execute(text("""
            SELECT 
                t.track_id,
                t.track_name,
                a.artist_id,
                a.artist_name AS recommendation_source,
                'artist' AS recommendation_type
            FROM Track t
            JOIN ArtistTrack at ON t.track_id = at.track_id
            JOIN Artist a ON at.artist_id = a.artist_id
            WHERE a.artist_id IN (
                SELECT artist_id FROM userartistpreference
                WHERE user_id = :user_id
            )
            AND t.track_id NOT IN (
                SELECT track_id FROM usertrackpreference
                WHERE user_id = :user_id
            )
            LIMIT 5
        """), {"user_id": user_id}).mappings().fetchall()

        # Genre-based recommendations
        genre_recs = g.conn.execute(text("""
            SELECT 
                t.track_id,
                t.track_name,
                t.genre_name AS recommendation_source,
                'genre' AS recommendation_type
            FROM Track t
            WHERE t.genre_name IN (
                SELECT genre_name FROM usergenrepreference
                WHERE user_id = :user_id
            )
            AND t.track_id NOT IN (
                SELECT track_id FROM usertrackpreference
                WHERE user_id = :user_id
            )
            LIMIT 5
        """), {"user_id": user_id}).mappings().fetchall()

        # Album-based recommendations
        album_recs = g.conn.execute(text("""
            SELECT 
                t.track_id,
                t.track_name,
                a.album_name,
                utp.source_track_name
            FROM (
                -- 获取用户收藏曲目对应的专辑ID和曲目名称
                SELECT DISTINCT 
                    Track.album_id, 
                    Track.track_name AS source_track_name
                FROM UserTrackPreference
                JOIN Track USING (track_id)
                WHERE user_id = :user_id
            ) utp
            JOIN Track t USING (album_id)
            JOIN Album a USING (album_id)
            WHERE t.track_id NOT IN (
                SELECT track_id FROM UserTrackPreference
                WHERE user_id = :user_id
            )
            ORDER BY t.track_popularity DESC
            LIMIT 5
        """), {"user_id": user_id}).mappings().fetchall()

        # Process artist recommendations
        for rec in artist_recs:
            recommendations.append({
                'track_id': rec['track_id'],
                'track_name': rec['track_name'],
                'reason': f"Similar artist: {rec['recommendation_source']}",
                'type': rec['recommendation_type']
            })

        # Process genre recommendations
        for rec in genre_recs:
            recommendations.append({
                'track_id': rec['track_id'],
                'track_name': rec['track_name'],
                'reason': f"Same genre: {rec['recommendation_source']}",
                'type': rec['recommendation_type']
            })

        # Process album recommendations
        for rec in album_recs:
            recommendations.append({
                'track_id': rec['track_id'],
                'track_name': rec['track_name'],
                'reason': f"From album '{rec['album_name']}' (you liked: {rec['source_track_name']})",
                'type': 'album'
            })

        return render_template("recommendation.html",
                             recommendations=recommendations)

    except Exception as e:
        print(f"Recommendation error: {str(e)}")
        return render_template("error.html", message="Failed to load recommendations"), 500
# Preference management
@app.route('/preferences', methods=['GET', 'POST', 'DELETE'])
def preferences():
    if 'user_id' not in session:
        return redirect('/')

    user_id = session['user_id']

    if request.method == 'DELETE':
        item_id = request.form.get('item_id')
        pref_type = request.form.get('type')
        if not item_id or not pref_type:
            print(f"Missing parameters! item_id: {item_id}, type: {pref_type}")
            return render_template("error.html", message="Invalid request"), 400

        print(f"Processing DELETE: type={pref_type}, id={item_id}")
        try:
            if pref_type == 'artist':
                artist_uuid = uuid.UUID(item_id)
                g.conn.execute(text("""
                    DELETE FROM userartistpreference
                    WHERE user_id = :user_id AND artist_id = :item_id
                """), {"user_id": user_id, "item_id": artist_uuid})

            elif pref_type == 'track':
                g.conn.execute(text("""
                    DELETE FROM usertrackpreference
                    WHERE user_id = :user_id AND track_id = :item_id
                """), {"user_id": user_id, "item_id": item_id})

            elif pref_type == 'genre':
                g.conn.execute(text("""
                    DELETE FROM usergenrepreference
                    WHERE user_id = :user_id AND genre_name = :item_id
                """), {"user_id": user_id, "item_id": item_id})

            g.conn.commit()
            print("Delete operation committed successfully")
            return redirect('/preferences')

        except Exception as e:
            print(f"Delete error: {str(e)}")
            g.conn.rollback()
            return render_template("error.html", message="Failed to delete preference"), 500

    # add preference
    if request.method == 'POST':
        item_id = request.form['item_id']
        pref_type = request.form['type']

        try:
            if pref_type == 'track':
                g.conn.execute(text("""
                    INSERT INTO usertrackpreference (user_id, track_id)
                    VALUES (:user_id, :item_id)
                    ON CONFLICT DO NOTHING
                """), {"user_id": user_id, "item_id": item_id})
            elif pref_type == 'artist':
                g.conn.execute(text("""
                    INSERT INTO userartistpreference (user_id, artist_id)
                    VALUES (:user_id, :item_id)
                    ON CONFLICT DO NOTHING
                """), {"user_id": user_id, "item_id": item_id})
            elif pref_type == 'genre':
                g.conn.execute(text("""
                    INSERT INTO usergenrepreference (user_id, genre_name)
                    VALUES (:user_id, :item_id)
                    ON CONFLICT DO NOTHING
                """), {"user_id": user_id, "item_id": item_id})

            g.conn.commit()

        except Exception as e:
            print(f"Preference error: {str(e)}")
            g.conn.rollback()

    # get current preference
    try:
        # Modified queries to get complete entity information
        tracks = g.conn.execute(text("""
                SELECT t.track_id, t.track_name 
                FROM usertrackpreference utp
                JOIN track t ON utp.track_id = t.track_id
                WHERE utp.user_id = :user_id
            """), {"user_id": user_id}).fetchall()

        artists = g.conn.execute(text("""
                SELECT a.artist_id, a.artist_name 
                FROM userartistpreference uap
                JOIN artist a ON uap.artist_id = a.artist_id
                WHERE uap.user_id = :user_id
            """), {"user_id": user_id}).fetchall()

        genres = g.conn.execute(text("""
            SELECT genre_name 
            FROM usergenrepreference
            WHERE user_id = :user_id
        """), {"user_id": user_id}).fetchall()

    except Exception as e:
        print(f"Preference fetch error: {str(e)}")
        tracks = artists = genres = []

    return render_template("preference.html",
                           tracks=tracks,
                           artists=artists,
                           genres=genres)

# Item detail pages
@app.route('/track/<track_id>')
def track_detail(track_id):
    """Display detailed track information"""
    try:
        # Execute query with explicit safe column selection
        track = g.conn.execute(text("""
            SELECT 
                t.track_id,
                t.track_name,
                t.track_popularity,
                t.genre_name,
                a.artist_id,
                a.artist_name,
                al.album_name
            FROM Track t
            JOIN ArtistTrack at ON t.track_id = at.track_id
            JOIN Artist a ON at.artist_id = a.artist_id
            LEFT JOIN Album al ON t.album_id = al.album_id
            WHERE t.track_id = :track_id
        """), {"track_id": track_id}).mappings().first()

        if not track:
            return render_template("error.html", message="Track not found"), 404

        # Convert to dict with safe field access
        track_data = dict(track)
        return render_template("track.html", track=track_data)

    except Exception as e:
        print(f"Track error: {str(e)}")
        return render_template("error.html", message="Error loading track details"), 500

# genre
@app.route('/genre/<genre_name>')
def genre_detail(genre_name):
    """Display genre details and add to preferences"""
    if 'user_id' not in session:
        return redirect('/')

    try:
        genre = g.conn.execute(text("""
            SELECT * FROM Genre
            WHERE genre_name = :genre_name
        """), {"genre_name": genre_name}).mappings().first()

        if not genre:
            return render_template("error.html", message="Genre not found"), 404

        top_tracks = g.conn.execute(text("""
            SELECT track_id, track_name, track_popularity
            FROM Track
            WHERE genre_name = :genre_name
            ORDER BY track_popularity DESC
            LIMIT 10
        """), {"genre_name": genre_name}).mappings().fetchall()

        return render_template("genre.html",
                             genre=genre,
                             tracks=top_tracks)

    except Exception as e:
        print(f"Genre error: {str(e)}")
        return render_template("error.html", message="Error loading genre details"), 500

@app.route('/artist/<artist_id>')
def artist_detail(artist_id):
    """Display detailed artist information"""
    try:
        # Get specific artist details with column aliases
        artist = g.conn.execute(text("""
            SELECT 
                artist_id AS id,
                artist_name AS name,
                artist_nation AS nation,
                artist_popularity_score AS popularity,
                artist_tag AS tags
            FROM Artist
            WHERE artist_id = :artist_id
        """), {"artist_id": artist_id}).mappings().first()

        if not artist:
            return render_template("error.html", message="Artist not found"), 404

        # Get top tracks with explicit columns
        tracks = g.conn.execute(text("""
            SELECT 
                t.track_id AS id,
                t.track_name AS name,
                t.track_popularity AS popularity
            FROM Track t
            JOIN ArtistTrack at ON t.track_id = at.track_id
            WHERE at.artist_id = :artist_id
            ORDER BY t.track_popularity DESC
            LIMIT 10
        """), {"artist_id": artist_id}).mappings().fetchall()

        return render_template("artist.html",
                               artist=artist,
                               tracks=tracks)

    except Exception as e:
        print(f"Artist error: {str(e)}")
        return render_template("error.html", message="Error loading artist details"), 500
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8111, debug=True)