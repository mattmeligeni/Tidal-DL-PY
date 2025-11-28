import requests
import base64
import xml.etree.ElementTree as ET
import os
import re
import json
import subprocess
import time
import uuid
from urllib.parse import unquote
from concurrent.futures import ThreadPoolExecutor, as_completed

# === UX ENHANCEMENTS: tqdm and rich ===
try:
    from tqdm import tqdm
except ImportError:
    tqdm = None
    print("[!] tqdm not installed. Progress bars will not be shown. Run 'pip install tqdm' for best experience.")

try:
    from rich.console import Console
    from rich.table import Table
    from rich.prompt import Prompt
    from rich import box
except ImportError:
    Console = None
    Table = None
    Prompt = None
    print("[!] rich not installed. Output will be plain. Run 'pip install rich' for best experience.")

class TokenManager:
    def __init__(self):
        self.token_file = 'tidal_token.json'
        self.token = None
        self.last_updated = 0
        
    def load_token(self):
        """Load token from cache"""
        try:
            with open(self.token_file, 'r') as f:
                data = json.load(f)
            self.token = data.get('token')
            self.last_updated = data.get('last_updated', 0)
            return self.token
        except:
            return None
    
    def save_token(self, token):
        """Save token to cache"""
        self.token = token
        self.last_updated = time.time()
        data = {
            'token': token,
            'last_updated': self.last_updated
        }
        with open(self.token_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def is_token_expired(self):
        """Check if token is older than 1 hour"""
        return time.time() - self.last_updated > 3600
    
    def get_token(self):
        """Get current token, prompt for new one if expired"""
        # Try to load cached token first
        if self.load_token() and not self.is_token_expired():
            return self.token
        
        print("🔑 Token expired or not found.")
        print("Please get a new token from HTTP Toolkit:")
        print("1. Open Tidal app on your rooted device")
        print("2. Capture the API calls with HTTP Toolkit") 
        print("3. Look for the 'Authorization: Bearer ...' header")
        print("4. Paste the new token below (without 'Bearer ')")
        
        new_token = input("Enter new token: ").strip()
        if new_token:
            self.save_token(new_token)
            print("✅ Token saved for future use")
            return new_token
        return None

class TidalDownloader:
    def __init__(self, token_manager):
        self.token_manager = token_manager
        self.update_headers()
        
    def update_headers(self):
        """Update headers with current valid token"""
        token = self.token_manager.get_token()
        if not token:
            raise Exception("No valid token available")
        
        self.headers = {
            'Authorization': f'Bearer {token}',
            'User-Agent': 'TIDAL_ANDROID/9047 null',
            'x-tidal-client-version': '2.167.0'
        }
        self.base_url = "https://api.tidal.com"
        
    def get_artist_display_name(self, artists, for_filename=False):
        """Get formatted artist name for display and filename"""
        if not artists:
            return "Unknown"
        
        # Get main artists (type MAIN or no type specified)
        main_artists = [artist for artist in artists if artist.get('type') in ['MAIN', None]]
        
        if not main_artists:
            # Fallback to all artists if no MAIN type found
            main_artists = artists
        
        artist_names = [artist.get('name', 'Unknown') for artist in main_artists]
        
        # Fix for Issue 1: Use "Various" if too many artists (for filenames)
        if for_filename and len(artist_names) > 4:
            return "Various"
        
        # Keep existing logic for display
        if len(artist_names) == 1:
            return artist_names[0]
        elif len(artist_names) == 2:
            return f"{artist_names[0]} & {artist_names[1]}"
        else:
            return ", ".join(artist_names)
    
    def clean_track_title(self, title, artists):
        """Remove featured artists from title if they're already in the main artists"""
        if not title or not artists:
            return title
        
        # Get all artist names for comparison
        all_artist_names = [artist.get('name', '').lower() for artist in artists]
        
        # Common feat patterns to remove
        feat_patterns = [
            r'\s*\(feat\.\s*[^)]+\)',
            r'\s*\(ft\.\s*[^)]+\)', 
            r'\s*feat\.\s*[^)]+',
            r'\s*ft\.\s*[^)]+',
            r'\s*\(with\s+[^)]+\)',
            r'\s*with\s+[^)]+'
        ]
        
        cleaned_title = title
        for pattern in feat_patterns:
            # Find all matches
            matches = re.findall(pattern, cleaned_title, re.IGNORECASE)
            for match in matches:
                # Extract featured artist name from the pattern
                feat_artist = re.sub(r'^[^(]*\(\s*(?:feat\.|ft\.|with)\s*', '', match, flags=re.IGNORECASE)
                feat_artist = re.sub(r'\)\s*$', '', feat_artist)
                feat_artist = feat_artist.strip()
                
                # Check if this featured artist is already in the main artists
                if feat_artist.lower() in all_artist_names:
                    # Remove the feat part from title
                    cleaned_title = cleaned_title.replace(match, '').strip()
        
        return cleaned_title
        
    def search_tracks(self, query, limit=10):
        """Search for tracks on Tidal with pagination"""
        print(f"🔍 Searching tracks for: '{query}'...")
        self.update_headers()
        url = f"{self.base_url}/v2/search"
        offset = 0
        all_tracks = []
        while True:
            params = {
                'limit': limit,
                'offset': offset,
                'query': query,
                'types': 'TRACKS',
                'includeUserPlaylists': 'false',
                'includeDidYouMean': 'true',
                'deviceType': 'PHONE',
                'locale': 'en_GB',
                'platform': 'ANDROID',
                'countryCode': 'IT'
            }
            try:
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
                tracks = data.get('tracks', {}).get('items', [])
                if not tracks:
                    if not all_tracks:
                        print("❌ No tracks found!")
                    break
                all_tracks.extend(tracks)
                self.display_track_results(tracks)
                if len(tracks) < limit:
                    break
                more = input("Show more results? (y/n): ").strip().lower()
                if more != 'y':
                    break
                offset += limit
            except Exception as e:
                print(f"❌ Track search failed: {e}")
                break
        return all_tracks
    
    def search_albums(self, query, limit=10):
        """Search for albums on Tidal with pagination"""
        print(f"🔍 Searching albums for: '{query}'...")
        self.update_headers()
        url = f"{self.base_url}/v2/search"
        offset = 0
        all_albums = []
        while True:
            params = {
                'limit': limit,
                'offset': offset,
                'query': query,
                'types': 'ALBUMS',
                'includeUserPlaylists': 'true',
                'includeDidYouMean': 'true',
                'deviceType': 'PHONE',
                'locale': 'en_GB',
                'platform': 'ANDROID',
                'countryCode': 'IT'
            }
            try:
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
                albums = data.get('albums', {}).get('items', [])
                if not albums:
                    if not all_albums:
                        print("❌ No albums found!")
                    break
                all_albums.extend(albums)
                self.display_album_results(albums)
                if len(albums) < limit:
                    break
                more = input("Show more results? (y/n): ").strip().lower()
                if more != 'y':
                    break
                offset += limit
            except Exception as e:
                print(f"❌ Album search failed: {e}")
                break
        return all_albums
    
    def search_artists(self, query, limit=5):
        """Search for artists on Tidal with pagination"""
        print(f"🔍 Searching artists for: '{query}'...")
        self.update_headers()
        url = f"{self.base_url}/v2/search"
        offset = 0
        all_artists = []
        while True:
            params = {
                'limit': limit,
                'offset': offset,
                'query': query,
                'types': 'ARTISTS',
                'includeUserPlaylists': 'true',
                'includeDidYouMean': 'true',
                'deviceType': 'PHONE',
                'locale': 'en_GB',
                'platform': 'ANDROID',
                'countryCode': 'IT'
            }
            try:
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
                artists = data.get('artists', {}).get('items', [])
                if not artists:
                    if not all_artists:
                        print("❌ No artists found!")
                    break
                all_artists.extend(artists)
                self.display_artist_results(artists)
                if len(artists) < limit:
                    break
                more = input("Show more results? (y/n): ").strip().lower()
                if more != 'y':
                    break
                offset += limit
            except Exception as e:
                print(f"❌ Artist search failed: {e}")
                break
        return all_artists
    
    def get_artist_details(self, artist_id):
        """Get detailed artist information including top tracks and albums"""
        print(f"📖 Getting artist details for ID: {artist_id}...")
        self.update_headers()
        
        url = f"{self.base_url}/v2/artist/{artist_id}"
        params = {
            'deviceType': 'PHONE',
            'locale': 'en_GB',
            'platform': 'ANDROID',
            'countryCode': 'IT'
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            print(f"❌ Failed to get artist details: {e}")
            return None
    
    def get_album_details(self, album_id):
        """Get detailed album information including tracklist"""
        print(f"📖 Getting album details for ID: {album_id}...")
        self.update_headers()
        
        url = f"{self.base_url}/v1/pages/album"
        params = {
            'albumId': album_id,
            'deviceType': 'PHONE',
            'locale': 'en_GB',
            'platform': 'ANDROID',
            'countryCode': 'IT'
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            print(f"❌ Failed to get album details: {e}")
            return None
    
    def get_quality_display(self, item):
        """Determine quality display with Hi-Res detection - fixed for both tag types"""
        base_quality = item.get('audioQuality', 'UNKNOWN')
        tags = item.get('mediaMetadata', {}).get('tags', [])
        
        # Check for both Hi-Res tag variations
        if 'HIRES_LOSSLESS' in tags or 'HI_RES_LOSSLESS' in tags:
            return "Lossless - FLAC 24bit"
        elif base_quality == 'LOSSLESS':
            return "Lossless - FLAC 16bit"
        elif base_quality == 'HI_RES':
            return "Hi-Res - FLAC 24bit"
        else:
            return base_quality
    
    def display_track_results(self, tracks):
        """Display track search results with rich table if available"""
        if Table and Console:
            console = Console()
            table = Table(title=f"Found {len(tracks)} tracks", box=box.SIMPLE)
            table.add_column("#", style="cyan", width=3)
            table.add_column("Title", style="bold")
            table.add_column("Artists", style="magenta")
            table.add_column("Album", style="green")
            table.add_column("Dur.", style="yellow", width=6)
            table.add_column("Qual.", style="blue")
            table.add_column("Exp.", style="red", width=3)
            table.add_column("Date", style="white", width=10)
            table.add_column("ID", style="dim", width=8)
            for i, track in enumerate(tracks, 1):
                title = track.get('title', 'Unknown Title')
                artists = self.get_artist_display_name(track.get('artists', []))
                album = track.get('album', {}).get('title', 'Unknown Album')
                duration = track.get('duration', 0)
                quality = self.get_quality_display(track)
                explicit = "🔞" if track.get('explicit') else ""
                release_date = track.get('album', {}).get('releaseDate', 'Unknown')
                minutes = duration // 60
                seconds = duration % 60
                duration_str = f"{minutes}:{seconds:02d}"
                table.add_row(str(i), title, artists, album, duration_str, quality, explicit, release_date, str(track.get('id')))
            console.print(table)
        else:
            print(f"\n🎵 Found {len(tracks)} tracks:")
            print("=" * 70)
            for i, track in enumerate(tracks, 1):
                title = track.get('title', 'Unknown Title')
                artists = self.get_artist_display_name(track.get('artists', []))
                album = track.get('album', {}).get('title', 'Unknown Album')
                duration = track.get('duration', 0)
                quality = self.get_quality_display(track)
                explicit = "🔞" if track.get('explicit') else ""
                release_date = track.get('album', {}).get('releaseDate', 'Unknown')
                minutes = duration // 60
                seconds = duration % 60
                duration_str = f"{minutes}:{seconds:02d}"
                print(f"{i}. {artists} - {title} {explicit}")
                print(f"   📀 {album} | ⏱️ {duration_str} | 🎚️ {quality}")
                print(f"   📅 {release_date} | 🆔 {track.get('id')}")
                print()
    
    def display_album_results(self, albums):
        """Display album search results with rich table if available"""
        if Table and Console:
            console = Console()
            table = Table(title=f"Found {len(albums)} albums", box=box.SIMPLE)
            table.add_column("#", style="cyan", width=3)
            table.add_column("Title", style="bold")
            table.add_column("Artists", style="magenta")
            table.add_column("Tracks", style="yellow", width=6)
            table.add_column("Dur.", style="green", width=6)
            table.add_column("Qual.", style="blue")
            table.add_column("Exp.", style="red", width=3)
            table.add_column("Date", style="white", width=10)
            table.add_column("ID", style="dim", width=8)
            for i, album in enumerate(albums, 1):
                title = album.get('title', 'Unknown Album')
                artists = self.get_artist_display_name(album.get('artists', []))
                tracks_count = album.get('numberOfTracks', 0)
                release_date = album.get('releaseDate', 'Unknown')
                quality = self.get_quality_display(album)
                explicit = "🔞" if album.get('explicit') else ""
                duration = album.get('duration', 0)
                total_minutes = duration // 60
                total_seconds = duration % 60
                duration_str = f"{total_minutes}:{total_seconds:02d}"
                table.add_row(str(i), title, artists, str(tracks_count), duration_str, quality, explicit, release_date, str(album.get('id')))
            console.print(table)
        else:
            print(f"\n💿 Found {len(albums)} albums:")
            print("=" * 70)
            for i, album in enumerate(albums, 1):
                title = album.get('title', 'Unknown Album')
                artists = self.get_artist_display_name(album.get('artists', []))
                tracks_count = album.get('numberOfTracks', 0)
                release_date = album.get('releaseDate', 'Unknown')
                quality = self.get_quality_display(album)
                explicit = "🔞" if album.get('explicit') else ""
                duration = album.get('duration', 0)
                total_minutes = duration // 60
                total_seconds = duration % 60
                duration_str = f"{total_minutes}:{total_seconds:02d}"
                print(f"{i}. {artists} - {title} {explicit}")
                print(f"   📀 {tracks_count} tracks | ⏱️ {duration_str} | 🎚️ {quality}")
                print(f"   📅 {release_date} | 🆔 {album.get('id')}")
                print()
    
    def display_artist_results(self, artists):
        """Display artist search results with rich table if available"""
        if Table and Console:
            console = Console()
            table = Table(title=f"Found {len(artists)} artists", box=box.SIMPLE)
            table.add_column("#", style="cyan", width=3)
            table.add_column("Name", style="bold")
            table.add_column("Popularity", style="yellow", width=10)
            table.add_column("ID", style="dim", width=8)
            for i, artist in enumerate(artists, 1):
                name = artist.get('name', 'Unknown Artist')
                popularity = str(artist.get('popularity', 0)) + "%"
                table.add_row(str(i), name, popularity, str(artist.get('id')))
            console.print(table)
        else:
            print(f"\n🎤 Found {len(artists)} artists:")
            print("=" * 70)
            for i, artist in enumerate(artists, 1):
                name = artist.get('name', 'Unknown Artist')
                popularity = artist.get('popularity', 0)
                picture = artist.get('picture')
                print(f"{i}. {name}")
                print(f"   📊 Popularity: {popularity}% | 🆔 {artist.get('id')}")
                print()
    
    def display_artist_details(self, artist_data):
        """Display artist details including top tracks and albums, with rich tables and pagination"""
        if not artist_data:
            return None, None

        artist_info = artist_data.get('item', {}).get('data', {})
        artist_name = artist_info.get('name', 'Unknown Artist')
        print(f"\n🎤 Artist: {artist_name}")
        print("=" * 70)

        # Initialize variables at the start
        top_tracks = []
        albums = []
        displayed_albums = {}

        for item in artist_data.get('items', []):
            if item.get('type') == 'TRACK_LIST' and item.get('moduleId') == 'ARTIST_TOP_TRACKS':
                top_tracks = [track_item['data'] for track_item in item.get('items', [])]
            elif item.get('type') == 'HORIZONTAL_LIST' and item.get('moduleId') == 'ARTIST_ALBUMS':
                albums = [album_item['data'] for album_item in item.get('items', [])]

        # Paginate top tracks
        page_size = 10
        if top_tracks:
            page = 0
            while True:
                start = page * page_size
                end = start + page_size
                page_tracks = top_tracks[start:end]
                if not page_tracks:
                    break
                if Table and Console:
                    console = Console()
                    table = Table(title=f"Top Tracks ({start+1}-{min(end, len(top_tracks))} of {len(top_tracks)})", box=box.SIMPLE)
                    table.add_column("#", style="cyan", width=3)
                    table.add_column("Title", style="bold")
                    table.add_column("Dur.", style="yellow", width=6)
                    table.add_column("Qual.", style="blue")
                    table.add_column("Exp.", style="red", width=3)
                    table.add_column("ID", style="dim", width=8)
                    for i, track in enumerate(page_tracks, start+1):
                        title = track.get('title', 'Unknown Title')
                        duration = track.get('duration', 0)
                        minutes = duration // 60
                        seconds = duration % 60
                        duration_str = f"{minutes}:{seconds:02d}"
                        explicit = "🔞" if track.get('explicit') else ""
                        quality = self.get_quality_display(track)
                        table.add_row(str(i), title, duration_str, quality, explicit, str(track.get('id')))
                    console.print(table)
                else:
                    print(f"\n🎵 Top Tracks ({start+1}-{min(end, len(top_tracks))} of {len(top_tracks)}):")
                    print("-" * 50)
                    for i, track in enumerate(page_tracks, start+1):
                        title = track.get('title', 'Unknown Title')
                        duration = track.get('duration', 0)
                        minutes = duration // 60
                        seconds = duration % 60
                        duration_str = f"{minutes}:{seconds:02d}"
                        explicit = "🔞" if track.get('explicit') else ""
                        quality = self.get_quality_display(track)
                        print(f"{i}. {title} {explicit}")
                        print(f"   ⏱️ {duration_str} | 🎚️ {quality} | 🆔 {track.get('id')}")
                if end >= len(top_tracks):
                    break
                more = input("Show more top tracks? (y/n): ").strip().lower()
                if more != 'y':
                    break

        # Paginate albums
        if albums:
            page = 0
            album_list = []
            # Flatten album versions for pagination
            album_groups = {}
            for album in albums:
                title = album.get('title', 'Unknown Album')
                if title not in album_groups:
                    album_groups[title] = []
                album_groups[title].append(album)
            for title, album_versions in album_groups.items():
                if len(album_versions) == 1:
                    album_list.append((title, album_versions[0], None))
                else:
                    for idx, version in enumerate(album_versions, 1):
                        album_list.append((f"{title} (v{idx})", version, album_versions))
            page_size = 10
            while True:
                start = page * page_size
                end = start + page_size
                page_albums = album_list[start:end]
                if not page_albums:
                    break
                if Table and Console:
                    console = Console()
                    table = Table(title=f"Albums ({start+1}-{min(end, len(album_list))} of {len(album_list)})", box=box.SIMPLE)
                    table.add_column("#", style="cyan", width=3)
                    table.add_column("Title", style="bold")
                    table.add_column("Tracks", style="yellow", width=6)
                    table.add_column("Qual.", style="blue")
                    table.add_column("Exp.", style="red", width=3)
                    table.add_column("Date", style="white", width=10)
                    table.add_column("ID", style="dim", width=8)
                    for i, (title, album, versions) in enumerate(page_albums, start+1):
                        tracks_count = album.get('numberOfTracks', 0)
                        release_date = album.get('releaseDate', 'Unknown')
                        quality = self.get_quality_display(album)
                        explicit = "🔞" if album.get('explicit') else ""
                        table.add_row(str(i), title, str(tracks_count), quality, explicit, release_date, str(album.get('id')))
                    console.print(table)
                else:
                    print(f"\n💿 Albums ({start+1}-{min(end, len(album_list))} of {len(album_list)}):")
                    print("-" * 50)
                    for i, (title, album, versions) in enumerate(page_albums, start+1):
                        tracks_count = album.get('numberOfTracks', 0)
                        release_date = album.get('releaseDate', 'Unknown')
                        quality = self.get_quality_display(album)
                        explicit = "🔞" if album.get('explicit') else ""
                        print(f"{i}. {title} {explicit}")
                        print(f"   📀 {tracks_count} tracks | 🎚️ {quality}")
                        print(f"   📅 {release_date} | 🆔 {album.get('id')}")
                if end >= len(album_list):
                    break
                more = input("Show more albums? (y/n): ").strip().lower()
                if more != 'y':
                    break
            # Build displayed_albums index for selection
            for idx, (title, album, versions) in enumerate(album_list, 1):
                if versions:
                    displayed_albums[idx] = versions
                else:
                    displayed_albums[idx] = album
        else:
            print("\n💿 No albums found for this artist")
        return top_tracks, displayed_albums
    
    def display_album_tracks(self, album_data):
        """Display tracks from an album with rich table and pagination"""
        album_info = album_data['rows'][0]['modules'][0]['album']
        tracks = []
        for row in album_data['rows']:
            for module in row['modules']:
                if module.get('type') == 'ALBUM_ITEMS':
                    for item in module['pagedList']['items']:
                        if item['type'] == 'track':
                            tracks.append(item['item'])
        print(f"\n📋 Album: {album_info.get('title')}")
        print(f"🎤 Artist: {self.get_artist_display_name(album_info.get('artists', []))}")
        print(f"📅 Released: {album_info.get('releaseDate')}")
        print(f"🎚️ Quality: {self.get_quality_display(album_info)}")
        print(f"🔞 Explicit: {'Yes' if album_info.get('explicit') else 'No'}")
        print(f"📄 Copyright: {album_info.get('copyright', 'Unknown')}")
        print("\nTracklist:")
        page_size = 15
        page = 0
        while True:
            start = page * page_size
            end = start + page_size
            page_tracks = tracks[start:end]
            if not page_tracks:
                break
            if Table and Console:
                console = Console()
                table = Table(title=f"Tracks {start+1}-{min(end, len(tracks))} of {len(tracks)}", box=box.SIMPLE)
                table.add_column("#", style="cyan", width=3)
                table.add_column("Title", style="bold")
                table.add_column("Artists", style="magenta")
                table.add_column("Dur.", style="yellow", width=6)
                table.add_column("Exp.", style="red", width=3)
                for i, track in enumerate(page_tracks, start+1):
                    title = track.get('title', 'Unknown')
                    artists = self.get_artist_display_name(track.get('artists', []))
                    duration = track.get('duration', 0)
                    minutes = duration // 60
                    seconds = duration % 60
                    duration_str = f"{minutes}:{seconds:02d}"
                    explicit = "🔞" if track.get('explicit') else ""
                    table.add_row(str(i), title, artists, duration_str, explicit)
                console.print(table)
            else:
                print("-" * 50)
                for i, track in enumerate(page_tracks, start+1):
                    title = track.get('title', 'Unknown')
                    artists = self.get_artist_display_name(track.get('artists', []))
                    duration = track.get('duration', 0)
                    minutes = duration // 60
                    seconds = duration % 60
                    duration_str = f"{minutes}:{seconds:02d}"
                    explicit = "🔞" if track.get('explicit') else ""
                    print(f"{i:2d}. {title} {explicit}")
                    print(f"    {artists} | ⏱️ {duration_str}")
            if end >= len(tracks):
                break
            more = input("Show more tracks? (y/n): ").strip().lower()
            if more != 'y':
                break
        return tracks
    
    def download_cover_art(self, cover_id, output_dir, size="1280x1280"):
        """Download cover art for the track/album"""
        if not cover_id:
            return None
        
        # Construct cover art URL
        cover_url = f"https://resources.tidal.com/images/{cover_id.replace('-', '/')}/{size}.jpg"
        
        try:
            response = requests.get(cover_url, stream=True)
            response.raise_for_status()
            
            cover_path = os.path.join(output_dir, "cover.jpg")
            with open(cover_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"🖼️  Cover art downloaded: cover.jpg")
            return cover_path
            
        except Exception as e:
            print(f"⚠️  Could not download cover art: {e}")
            return None
    
    def get_track_playback_info(self, track_id, quality="HI_RES_LOSSLESS"):
        """Get playback info and manifest for a track"""
        
        self.update_headers()
        
        url = f"{self.base_url}/v1/tracks/{track_id}/playbackinfo"
        params = {
            'playbackmode': 'STREAM',
            'assetpresentation': 'FULL',
            'audioquality': quality,
            'immersiveaudio': 'true'
        }
        
        headers = self.headers.copy()
        headers['User-Agent'] = 'okhttp/4.12.0'
        headers['x-tidal-streamingsessionid'] = f'download-session-{int(time.time())}'
        
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Check if we got a valid response with manifest
            if not data.get('manifest'):
                print(f"❌ No manifest in playback response. Response: {data}")
                return None
                
            return data
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Network error getting playback info: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in playback response: {e}")
            if 'response' in locals():
                print(f"🔍 Response text: {response.text[:200]}...")
            return None
        except Exception as e:
            print(f"❌ Failed to get playback info: {e}")
            return None
    
    def download_file(self, url, filename):
        """Download a file with error handling"""
        try:
            response = requests.get(url, headers=self.headers, stream=True)
            response.raise_for_status()
            
            with open(filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            print(f"❌ Download failed: {e}")
            return False
    
    def parse_manifest(self, manifest_b64):
        """Parse the base64 encoded DASH manifest with better error handling"""
        try:
            
            # Check if it's actually base64
            if not manifest_b64 or len(manifest_b64) < 10:
                raise Exception("Empty or too short manifest")
            
            manifest_xml = base64.b64decode(manifest_b64).decode('utf-8')
            
            
            root = ET.fromstring(manifest_xml)
            
            segment_template = root.find('.//{urn:mpeg:dash:schema:mpd:2011}SegmentTemplate')
            if segment_template is None:
                # Try alternative namespace
                segment_template = root.find('.//SegmentTemplate')
                if segment_template is None:
                    raise Exception("Could not find SegmentTemplate in manifest")
            
            init_url = segment_template.get('initialization')
            media_template = segment_template.get('media')
            
            if not init_url or not media_template:
                raise Exception("Missing initialization URL or media template")
            
            segment_timeline = segment_template.find('{urn:mpeg:dash:schema:mpd:2011}SegmentTimeline')
            if segment_timeline is None:
                segment_timeline = segment_template.find('SegmentTimeline')
            
            total_segments = 0
            
            if segment_timeline is not None:
                for s_element in segment_timeline:
                    duration = int(s_element.get('d', 0))
                    repeat = int(s_element.get('r', 0)) + 1
                    total_segments += repeat
            
            
            return init_url, media_template, total_segments
            
        except Exception as e:
            print(f"❌ Failed to parse manifest: {e}")
            print(f"🔍 Manifest type: {type(manifest_b64)}, length: {len(manifest_b64) if manifest_b64 else 0}")
            return None, None, 0
    
    def sanitize_filename(self, filename):
        """Remove invalid characters from filename"""
        return re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    def add_flac_metadata(self, flac_file, track_info, cover_path=None):
        """Add metadata to FLAC file using ffmpeg, including version tag"""
        try:
            temp_file = flac_file + '.temp.flac'
            
            # Prepare metadata
            metadata_args = []
            artists = self.get_artist_display_name(track_info.get('artists', []))
            album_artist = track_info.get('artists', [{}])[0].get('name', '') if track_info.get('artists') else ''
            
            # FIX: Handle genres properly - they come as list of dictionaries
            genres_data = track_info.get('genres', [])
            if genres_data and isinstance(genres_data, list):
                if isinstance(genres_data[0], dict):
                    # Extract genre names from dictionaries
                    genre_names = [genre.get('name', '') for genre in genres_data if genre.get('name')]
                    genres_str = '; '.join(genre_names)
                else:
                    genres_str = '; '.join(genres_data)
            else:
                genres_str = ''
            
            # Build metadata map including version
            metadata_map = {
                'title': track_info.get('title', ''),
                'album': track_info.get('album', {}).get('title', ''),
                'artist': artists,
                'album_artist': album_artist,
                'track': str(track_info.get('trackNumber', 1)),
                'date': track_info.get('album', {}).get('releaseDate', '').split('-')[0],
                'genre': genres_str,
                'isrc': track_info.get('isrc', ''),
                'copyright': track_info.get('copyright', ''),
            }
            
            # Add version tag if present (as a separate metadata field)
            version = track_info.get('version')
            if version:
                metadata_map['version'] = version
            
            for key, value in metadata_map.items():
                if value:
                    metadata_args.extend(['-metadata', f'{key}={value}'])
            
            # Build ffmpeg command
            if cover_path and os.path.exists(cover_path):
                cmd = [
                    'ffmpeg',
                    '-i', flac_file,
                    '-i', cover_path,
                    '-map', '0:0',
                    '-map', '1:0',
                    '-c', 'copy',
                    '-disposition:v', 'attached_pic',
                    '-id3v2_version', '3'
                ] + metadata_args + [temp_file]
            else:
                cmd = ['ffmpeg', '-i', flac_file] + metadata_args + ['-c', 'copy', temp_file]
            
            # Run ffmpeg
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                os.replace(temp_file, flac_file)
                print("✅ Metadata added to FLAC file")
                if cover_path:
                    pass
            else:
                print(f"⚠️  Could not add metadata: {result.stderr}")
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            
        except Exception as e:
            print(f"⚠️  Error adding metadata: {e}")
    
    def download_segments_parallel(self, media_template, total_segments, temp_dir, max_workers=4):
        """Download segments in parallel with progress bar"""
        segment_files = []

        def download_single_segment(segment_num):
            media_url = media_template.replace('$Number$', str(segment_num))
            segment_file = os.path.join(temp_dir, f"segment_{segment_num:03d}.mp4")
            if self.download_file(media_url, segment_file):
                return segment_num, segment_file
            return segment_num, None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_segment = {
                executor.submit(download_single_segment, segment_num): segment_num
                for segment_num in range(1, total_segments + 1)
            }

            if tqdm:
                pbar = tqdm(total=total_segments, desc="Downloading segments", unit="seg", ncols=70)
            else:
                pbar = None
            successful_downloads = 0
            for future in as_completed(future_to_segment):
                segment_num = future_to_segment[future]
                try:
                    result_segment_num, result_file = future.result()
                    if result_file:
                        segment_files.append((result_segment_num, result_file))
                        successful_downloads += 1
                        if pbar:
                            pbar.update(1)
                        else:
                            print(f"   ✅ Segment {successful_downloads}/{total_segments}", end='\r')
                except Exception as e:
                    print(f"❌ Segment {segment_num} failed: {e}")
            if pbar:
                pbar.close()

        
        segment_files.sort(key=lambda x: x[0])
        return [file for _, file in segment_files]
    
    def download_track(self, track_info, output_dir="downloads"):
        """Download a single track with parallel segment downloads (minimal verbose output)"""
        track_id = track_info.get('id')
        title = track_info.get('title', 'Unknown Title')
        artists = track_info.get('artists', [])
        album = track_info.get('album', {}).get('title', 'Unknown Album')
        track_number = track_info.get('trackNumber', 1)

        # Apply track name fixes
        clean_title = self.clean_track_title(title, artists)
        filename_artists = self.get_artist_display_name(artists, for_filename=True)

        # Create safe filename with track number and artist
        safe_filename = self.sanitize_filename(f"{track_number:02d}. {filename_artists} - {clean_title}.flac")
        track_dir = os.path.join(output_dir, self.sanitize_filename(f"{filename_artists} - {album}"))

        # FIX: Create unique temp directory for each track to avoid conflicts
        unique_temp_dir = os.path.join(track_dir, f"temp_{uuid.uuid4().hex[:8]}")

        os.makedirs(track_dir, exist_ok=True)
        os.makedirs(unique_temp_dir, exist_ok=True)

        print(f"Will save as: {safe_filename}")
        print(f"Quality: {self.get_quality_display(track_info)}")

        # Download cover art
        cover_id = track_info.get('album', {}).get('cover')
        cover_path = self.download_cover_art(cover_id, track_dir) if cover_id else None
        if cover_path:
            pass

        # Get playback info
        playback_info = self.get_track_playback_info(track_id)
        if not playback_info:
            return False

        manifest_b64 = playback_info.get('manifest')
        if not manifest_b64:
            print("❌ No manifest found in playback info")
            return False

        # Parse manifest
        init_url, media_template, total_segments = self.parse_manifest(manifest_b64)
        if not init_url or not media_template:
            return False

        # Download initialization segment
        init_file = os.path.join(unique_temp_dir, "init.mp4")
        if not self.download_file(init_url, init_file):
            return False

        # Download media segments in parallel (progress bar inside)
        segment_files = self.download_segments_parallel(media_template, total_segments, unique_temp_dir)

        # Combine segments
        final_file = os.path.join(track_dir, safe_filename)
        try:
            with open(final_file, 'wb') as outfile:
                with open(init_file, 'rb') as init:
                    outfile.write(init.read())
                for segment_file in segment_files:
                    with open(segment_file, 'rb') as seg:
                        outfile.write(seg.read())

            # Add metadata
            self.add_flac_metadata(final_file, track_info, cover_path)
            # Clean up
            import shutil
            shutil.rmtree(unique_temp_dir)
            # Verify final file
            if os.path.exists(final_file):
                file_size = os.path.getsize(final_file) / (1024 * 1024)
                print(f"Download complete! File: {safe_filename} ({file_size:.1f} MB)")
                print(f"Location: {track_dir}")
                return True
            else:
                print("❌ Failed to create final file")
                return False
        except Exception as e:
            print(f"❌ Error combining files: {e}")
            # Clean up temp directory even on error
            try:
                import shutil
                shutil.rmtree(unique_temp_dir)
            except:
                pass
            return False
    
    def download_album_parallel(self, album_data, output_dir="downloads", max_workers=3):
        """Download an entire album with parallel track downloads, handling volumes and versions"""
        album_info = album_data['rows'][0]['modules'][0]['album']
        album_title = album_info.get('title', 'Unknown Album')
        album_artist = self.get_artist_display_name(album_info.get('artists', []))
        
        # Extract tracks
        tracks = []
        for row in album_data['rows']:
            for module in row['modules']:
                if module.get('type') == 'ALBUM_ITEMS':
                    for item in module['pagedList']['items']:
                        if item['type'] == 'track':
                            tracks.append(item['item'])
        
        if not tracks:
            print("❌ No tracks found in album")
            return False
        
        # Check if album has multiple volumes
        has_multiple_volumes = album_info.get('numberOfVolumes', 1) > 1
        print(f"📚 Album has {album_info.get('numberOfVolumes', 1)} volume(s)")
        
        # Create album directory
        album_dir = os.path.join(output_dir, self.sanitize_filename(f"{album_artist} - {album_title}"))
        os.makedirs(album_dir, exist_ok=True)
        
        print(f"💿 Downloading Album: {album_artist} - {album_title}")
        print(f"📀 Total tracks: {len(tracks)}")
        print(f"🎚️  Quality: {self.get_quality_display(album_info)}")
        print(f"📁 Location: {album_dir}")
        print(f"🚀 Downloading {max_workers} tracks in parallel")
        print("-" * 50)
        
        # Download cover art
        cover_id = album_info.get('cover')
        cover_path = self.download_cover_art(cover_id, album_dir) if cover_id else None
        
        # Download tracks in parallel
        def download_track_wrapper(track):
            print(f"📥 Starting download: {track.get('title')}")
            
            # Add album info to track for metadata
            track_with_album = track.copy()
            track_with_album['album'] = {
                'title': album_title,
                'releaseDate': album_info.get('releaseDate'),
                'cover': cover_id
            }
            
            # Pass volume info for directory structure
            success = self.download_track_to_album_parallel(
                track_with_album, 
                album_dir, 
                cover_path,
                has_multiple_volumes
            )
            return track.get('title'), success
        
        successful_downloads = 0
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_track = {
                executor.submit(download_track_wrapper, track): track
                for track in tracks
            }

            if tqdm:
                pbar = tqdm(total=len(tracks), desc="Downloading tracks", unit="trk", ncols=70)
            else:
                pbar = None

            for future in as_completed(future_to_track):
                track_title, success = future.result()
                results.append((track_title, success))
                if success:
                    successful_downloads += 1
                if pbar:
                    pbar.update(1)
                else:
                    print(f"✅ Completed: {track_title} ({successful_downloads}/{len(tracks)})")
                if not success:
                    print(f"❌ Failed: {track_title}")
            if pbar:
                pbar.close()

        print(f"\n🎉 Album download complete! {successful_downloads}/{len(tracks)} tracks downloaded successfully")
        print(f"📁 Album location: {album_dir}")
        return successful_downloads > 0
    
    def download_track_to_album_parallel(self, track_info, album_dir, cover_path=None, has_multiple_volumes=False):
        """Download a track to an album directory with volume subfolders and version tags"""
        track_id = track_info.get('id')
        title = track_info.get('title', 'Unknown Title')
        track_number = track_info.get('trackNumber', 1)
        volume_number = track_info.get('volumeNumber', 1)
        artists = track_info.get('artists', [])
        version = track_info.get('version')
        
        # Apply track name fixes
        clean_title = self.clean_track_title(title, artists)
        filename_artists = self.get_artist_display_name(artists, for_filename=True)
        
        # Create filename with version tag if present
        if version:
            safe_filename = self.sanitize_filename(f"{track_number:02d}. {filename_artists} - {clean_title} ({version}).flac")
        else:
            safe_filename = self.sanitize_filename(f"{track_number:02d}. {filename_artists} - {clean_title}.flac")
        
        # Create volume subfolder if needed
        if has_multiple_volumes:
            volume_dir = os.path.join(album_dir, f"Volume {volume_number}")
            os.makedirs(volume_dir, exist_ok=True)
            final_dir = volume_dir
        else:
            final_dir = album_dir
        
        # FIX: Create unique temp directory for each track to avoid conflicts
        unique_temp_dir = os.path.join(final_dir, f"temp_{uuid.uuid4().hex[:8]}")
        os.makedirs(unique_temp_dir, exist_ok=True)
        
        # Get playback info
        playback_info = self.get_track_playback_info(track_id)
        if not playback_info:
            return False
        
        manifest_b64 = playback_info.get('manifest')
        if not manifest_b64:
            print("❌ No manifest found in playback info")
            return False
        
        # Parse manifest
        init_url, media_template, total_segments = self.parse_manifest(manifest_b64)
        if not init_url or not media_template:
            return False
        
        # Download initialization segment
        init_file = os.path.join(unique_temp_dir, "init.mp4")
        if not self.download_file(init_url, init_file):
            return False
        
        # Download media segments in parallel
        segment_files = self.download_segments_parallel(media_template, total_segments, unique_temp_dir)
        
        # Combine segments
        final_file = os.path.join(final_dir, safe_filename)
        
        try:
            with open(final_file, 'wb') as outfile:
                with open(init_file, 'rb') as init:
                    outfile.write(init.read())
                
                for segment_file in segment_files:
                    with open(segment_file, 'rb') as seg:
                        outfile.write(seg.read())
            
            # Add metadata (including version tag)
            self.add_flac_metadata(final_file, track_info, cover_path)
            
            # Clean up temp files for this track
            import shutil
            shutil.rmtree(unique_temp_dir)
            
            return os.path.exists(final_file)
                
        except Exception as e:
            print(f"❌ Error downloading track: {e}")
            # Clean up temp directory even on error
            try:
                import shutil
                shutil.rmtree(unique_temp_dir)
            except:
                pass
            return False
    
    def run(self):
        """Main application loop"""
        print("🎵 Tidal Downloader - Enhanced Version")
        print("=" * 50)
        
        while True:
            print("\nWhat would you like to do?")
            print("1. Search and download tracks")
            print("2. Search and download albums") 
            print("3. Search and download by artist")
            print("4. Exit")
            
            choice = input("\nEnter your choice (1-4): ").strip()
            
            if choice == '1':
                query = input("Enter track search query: ").strip()
                if not query:
                    print("❌ Please enter a search query")
                    continue
                
                tracks = self.search_tracks(query, limit=10)
                if not tracks:
                    continue
                
                self.display_track_results(tracks)
                
                try:
                    selection = input(f"\nSelect track to download (1-{len(tracks)}) or '0' to go back: ").strip()
                    if selection == '0':
                        continue
                    
                    track_index = int(selection) - 1
                    if 0 <= track_index < len(tracks):
                        selected_track = tracks[track_index]
                        self.download_track(selected_track)
                    else:
                        print("❌ Invalid selection!")
                        
                except ValueError:
                    print("❌ Please enter a valid number!")
            
            elif choice == '2':
                query = input("Enter album search query: ").strip()
                if not query:
                    print("❌ Please enter a search query")
                    continue
                
                albums = self.search_albums(query, limit=10)
                if not albums:
                    continue
                
                self.display_album_results(albums)
                
                try:
                    selection = input(f"\nSelect album to download (1-{len(albums)}) or '0' to go back: ").strip()
                    if selection == '0':
                        continue
                    
                    album_index = int(selection) - 1
                    if 0 <= album_index < len(albums):
                        selected_album = albums[album_index]
                        album_data = self.get_album_details(selected_album['id'])
                        
                        if album_data:
                            tracks = self.display_album_tracks(album_data)
                            
                            confirm = input("\nDownload this album? (y/n): ").strip().lower()
                            if confirm == 'y':
                                # Use parallel album download
                                self.download_album_parallel(album_data, max_workers=3)
                        else:
                            print("❌ Failed to get album details")
                    else:
                        print("❌ Invalid selection!")
                        
                except ValueError:
                    print("❌ Please enter a valid number!")
            
            elif choice == '3':
                query = input("Enter artist search query: ").strip()
                if not query:
                    print("❌ Please enter a search query")
                    continue
                
                artists = self.search_artists(query, limit=5)
                if not artists:
                    continue
                
                self.display_artist_results(artists)
                
                try:
                    selection = input(f"\nSelect artist (1-{len(artists)}) or '0' to go back: ").strip()
                    if selection == '0':
                        continue
                    
                    artist_index = int(selection) - 1
                    if 0 <= artist_index < len(artists):
                        selected_artist = artists[artist_index]
                        artist_data = self.get_artist_details(selected_artist['id'])
                        
                        if artist_data:
                            top_tracks, albums = self.display_artist_details(artist_data)
                            
                            if not top_tracks and not albums:
                                print("❌ No content found for this artist")
                                continue
                            
                            # Ask what to download
                            print("\nWhat would you like to download?")
                            if top_tracks:
                                print("1. Download top tracks")
                            if albums:
                                print("2. Download an album")
                            print("0. Go back")
                            
                            download_choice = input("Enter your choice: ").strip()
                            
                            if download_choice == '1' and top_tracks:
                                # FIX: Let user choose which top tracks to download
                                print(f"\nSelect tracks to download (1-{len(top_tracks)}):")
                                print("Enter track numbers separated by commas (e.g., 1,3,5)")
                                print("Or type 'all' to download all tracks")
                                
                                track_selection = input("Your selection: ").strip().lower()
                                
                                tracks_to_download = []
                                if track_selection == 'all':
                                    tracks_to_download = top_tracks
                                else:
                                    try:
                                        selected_indices = [int(x.strip()) - 1 for x in track_selection.split(',')]
                                        for idx in selected_indices:
                                            if 0 <= idx < len(top_tracks):
                                                tracks_to_download.append(top_tracks[idx])
                                            else:
                                                print(f"❌ Invalid track number: {idx + 1}")
                                    except ValueError:
                                        print("❌ Please enter valid track numbers!")
                                        continue
                                
                                if tracks_to_download:
                                    print(f"\nDownloading {len(tracks_to_download)} tracks...")
                                    successful = 0
                                    for track in tracks_to_download:
                                        if self.download_track(track):
                                            successful += 1
                                    print(f"✅ Downloaded {successful}/{len(tracks_to_download)} tracks successfully")
                                
                            elif download_choice == '2' and albums:
                                # Let user select which album to download
                                try:
                                    album_selection = input(f"\nSelect album to download (1-{len(albums)}) or '0' to go back: ").strip()
                                    if album_selection == '0':
                                        continue
                                    
                                    album_index = int(album_selection) - 1
                                    if 0 <= album_index < len(albums):
                                        selected_album_data = albums[album_index + 1]  # +1 because displayed_albums starts from 1
                                        
                                        # Handle multiple versions
                                        if isinstance(selected_album_data, list):
                                            print("\nMultiple versions available:")
                                            for i, album_version in enumerate(selected_album_data, 1):
                                                tracks_count = album_version.get('numberOfTracks', 0)
                                                quality = self.get_quality_display(album_version)
                                                print(f"{i}. {tracks_count} tracks | {quality}")
                                            
                                            version_choice = input("Select version to download: ").strip()
                                            try:
                                                version_index = int(version_choice) - 1
                                                if 0 <= version_index < len(selected_album_data):
                                                    selected_album_data = selected_album_data[version_index]
                                                else:
                                                    print("❌ Invalid version selection!")
                                                    continue
                                            except ValueError:
                                                print("❌ Please enter a valid number!")
                                                continue
                                        
                                        # Get album details and download
                                        album_full_data = self.get_album_details(selected_album_data['id'])
                                        if album_full_data:
                                            self.display_album_tracks(album_full_data)
                                            confirm = input("\nDownload this album? (y/n): ").strip().lower()
                                            if confirm == 'y':
                                                self.download_album_parallel(album_full_data, max_workers=3)
                                        else:
                                            print("❌ Failed to get album details")
                                    else:
                                        print("❌ Invalid selection!")
                                except ValueError:
                                    print("❌ Please enter a valid number!")
                                    
                        else:
                            print("❌ Failed to get artist details")
                    else:
                        print("❌ Invalid selection!")
                        
                except ValueError:
                    print("❌ Please enter a valid number!")
                
            elif choice == '4':
                print("👋 Goodbye!")
                break
            else:
                print("❌ Invalid choice!")

# =============================================================================
# MAIN EXECUTION
# =============================================================================
if __name__ == "__main__":
    token_manager = TokenManager()
    
    # Try to load cached token first
    token = token_manager.load_token()
    
    if not token or token_manager.is_token_expired():
        token = token_manager.get_token()
        if not token:
            print("❌ No valid token available")
            exit()
    
    downloader = TidalDownloader(token_manager)
    downloader.run()