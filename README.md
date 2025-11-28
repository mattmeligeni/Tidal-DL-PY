# Tidal-DL-PY
Python Tidal Downloader
[readme.md](https://github.com/user-attachments/files/23830276/readme.md)

# Tidal Music Downloader

A sophisticated Python application for downloading music from Tidal with high-quality audio preservation, metadata embedding, and intelligent file organization.

## Features

### Core Capabilities
- **Triple Search System**: Search by tracks, albums, or artists
- **Lossless Audio**: Download in FLAC format (16-bit and 24-bit Hi-Res)
- **Parallel Downloads**: Multi-threaded downloading for maximum speed
- **Metadata Preservation**: Full ID3 tagging with cover art embedding
- **Smart File Organization**: Logical directory structure and filename formatting

### Audio Quality Support
- **Hi-Res Lossless**: FLAC 24-bit (when available)
- **Lossless**: FLAC 16-bit (CD quality)
- **Automatic Quality Detection**: Identifies best available quality

### Search & Discovery
- **Track Search**: Find and download individual tracks
- **Album Search**: Download complete albums with parallel track processing
- **Artist Profiles**: Browse artist top tracks and discography
- **Version Comparison**: Highlights differences between album editions

## How It Works

### Authentication
The application uses Tidal's official API with user-provided ANDROID APP authentication tokens. Tokens can be obtained from:
- **Android Mobile App**: Via HTTP Toolkit interception


### Streaming Technology
The downloader utilizes Tidal's DASH (Dynamic Adaptive Streaming over HTTP) protocol:
1. **Manifest Retrieval**: Gets base64-encoded streaming instructions
2. **Segment Processing**: Downloads audio segments in parallel
3. **File Assembly**: Combines segments into complete FLAC files
4. **Metadata Embedding**: Adds comprehensive track information and artwork

### Parallel Processing
- **Segment-Level**: Downloads 4 audio segments simultaneously per track
- **Track-Level**: Downloads 3 tracks simultaneously in album mode
- **Conflict Prevention**: Unique temporary directories prevent file collisions

## Installation

### Prerequisites
- Python 3.7+
- FFmpeg (for metadata processing)
- Required Python packages: `requests`

### Quick Start
1. Clone the repository
2. Install dependencies: `pip install requests`
3. Ensure FFmpeg is in your system PATH
4. Run the application

### Token Setup
The application will guide you through obtaining and configuring your Tidal authentication token on first run.

## Usage

### Basic Workflow
1. **Start the application** and configure authentication
2. **Choose search type**: Tracks, Albums, or Artists
3. **Browse results** with quality indicators and metadata
4. **Select content** to download
5. **Monitor progress** with real-time status updates

### Search Modes

#### Track Search
- Search for individual songs
- Preview quality and metadata before downloading
- Single-track processing with segment parallelization

#### Album Search  
- Download complete albums
- Parallel track downloading (3 simultaneous)
- Automatic cover art and metadata handling

#### Artist Search
- Browse artist profiles and top tracks
- View complete discography with version comparisons
- Download top tracks or select specific albums

## Technical Details

### Audio Quality Detection
The application automatically detects and displays available audio qualities:
- **Hi-Res Lossless**: 24-bit FLAC with expanded dynamic range
- **Lossless**: 16-bit FLAC (CD quality)
- **Standard**: Lower quality fallbacks when lossless unavailable

### Metadata System
Comprehensive FLAC metadata embedding including:
- Track title, artist, album information
- Track numbering and disc positions
- Release year and genre classification
- Copyright and ISRC codes
- Embedded cover artwork

### File Organization
Intelligent filename and directory structure:
- Artist and album-based folder organization
- Track number prefixes for proper sorting
- Sanitized filenames compatible across all operating systems
- Smart artist name formatting for multi-artist tracks

## Performance Features

### Parallel Download Architecture
- **Dual-Level Parallelism**: Segment and track-level simultaneous downloads
- **Configurable Concurrency**: Adjustable worker counts for different scenarios
- **Efficient Resource Usage**: Memory-friendly streaming and processing

### Error Handling & Recovery
- **Network Resilience**: Automatic retry mechanisms for failed downloads
- **Partial Download Recovery**: Resume capability for interrupted operations
- **Comprehensive Logging**: Detailed progress and error reporting

### User Experience
- **Progress Indicators**: Real-time download status and ETA
- **Quality Transparency**: Clear display of audio quality before downloading
- **Interactive Selection**: Flexible content selection with preview options

## Legal & Ethical Considerations

### Important Notes
- Requires a legitimate Tidal subscription
- Only downloads content accessible to your account
- Respects copyright and terms of service
- Intended for personal use and music preservation
- Uses official Tidal APIs without DRM circumvention

### Privacy & Security
- Authentication tokens stored locally only
- No data collection or telemetry
- All processing occurs on your local machine

## Advanced Features

### Multi-Threading Configuration
Adjust parallel processing levels in the code for optimal performance on your system:
- Segment download workers (default: 4)
- Album track workers (default: 3)

### Quality Preferences
The application automatically selects the highest available quality, with configurable fallback options.

### Metadata Customization
Advanced users can modify the metadata embedding logic to include additional fields or custom formatting.

## Contributing

This project is open for improvements and feature additions. Key areas for enhancement:
- Additional metadata sources
- Extended quality format support
- User interface improvements
- Performance optimizations

## License

This project is provided for educational and personal use. Users are responsible for complying with Tidal's terms of service and applicable copyright laws.

## Troubleshooting

### Common Issues
- **Authentication Errors**: Verify token validity and expiration
- **FFmpeg Not Found**: Ensure FFmpeg is installed and in PATH
- **Network Issues**: Check internet connectivity and firewall settings
- **Storage Problems**: Verify sufficient disk space and write permissions

### Performance Tips
- Use wired internet connections for large downloads
- Adjust parallel workers based on your system capabilities
- Monitor system resources during intensive operations

---

**Note**: This tool is designed for music enthusiasts who want to preserve their legitimate Tidal content in the highest possible quality with proper metadata organization.
