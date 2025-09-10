# YouTube Video Link Extraction Research

## The Challenge
Matthew Posa often mentions linking to other videos and points to corners of the screen where YouTube cards/end screens appear. We want to extract these embedded video links to understand video cross-references.

## API Limitations (Confirmed)
- **YouTube Data API**: No access to cards, end screens, or annotations
- **Official Support**: Only available to special YouTube Partners via private APIs

## Tool Options Investigated

### 1. yt-dlp (Most Promising)
- **Pros**: Active, maintained fork of youtube-dl with robust metadata extraction
- **Capabilities**: Video metadata, comments, descriptions, thumbnails
- **Limitations**: No specific card/end screen extraction documented
- **Status**: Worth testing - may capture some embedded link data in metadata

### 2. Selenium + Web Scraping
- **Approach**: Load YouTube page, inspect DOM for card/end screen elements
- **Challenges**: 
  - Bot detection/CAPTCHA
  - Dynamic loading of interactive elements
  - Requires stealth techniques
- **Feasibility**: Possible but fragile

### 3. Browser Automation + Network Monitoring
- **Method**: Capture network requests while video plays to detect card/link API calls
- **Tools**: Selenium + network logs, playwright
- **Complexity**: High - requires understanding YouTube's internal APIs

## Recommendation

**Phase 1**: Test yt-dlp to see what embedded link data it can extract from video metadata
**Phase 2**: If insufficient, explore Selenium-based DOM scraping for visible cards
**Phase 3**: Consider manual curation as fallback (crowd-sourced or targeted)

## Alternative: Description Link Analysis
Many YouTubers include related video links in descriptions - this is accessible via YouTube API and might capture some of the same cross-reference data.

## Implementation Plan
1. Try yt-dlp on sample videos to see what link data is available
2. Analyze video descriptions for embedded YouTube links  
3. Build manual curation interface for important cross-references
4. Explore Selenium approach if automated extraction proves valuable

## Status
- **Research**: Complete  
- **Testing**: Pending
- **Implementation**: TBD based on test results