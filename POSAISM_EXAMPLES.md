# Posaism & Reference Examples

## Salt References
- **"Not too much salt, not too little salt, just the right amount of salt"** 
  - Type: posaism
  - Category: phrase  
  - Context: Cooking/seasoning commentary
  - Frequency: recurring

## Fishing Wisdom
- **"Where there's downed trees there's fish and where there's fish you'll catch 'em"**
  - Type: posaism
  - Category: phrase
  - Context: Fishing philosophy/advice
  - Frequency: recurring
  - Note: Has silly variations

## Weather Commentary  
- **"Blue Sklies"**
  - Type: posaism
  - Category: phrase
  - Context: Intentional mispronunciation of "blue skies" 
  - Frequency: recurring

## Characters & Objects
- **"Ronaldo The Unsplittable"**
  - Type: character
  - Category: object
  - Context: Memorable stubborn log that wouldn't split
  - Frequency: one-time

## Songs
- **"Chopping Wood"** 
  - Type: song
  - Category: song
  - Context: Original campfire song about wood chopping
  - Frequency: recurring
  
- **"Still Chopping Wood"**
  - Type: song  
  - Category: song
  - Context: Sequel to the wood chopping song series
  - Frequency: recurring

## Implementation Notes
- Each reference gets **one page** listing all video appearances
- **First canonical appearance** tracked with video ID + timestamp
- **Cross-linking** from video pages to reference pages
- **Search/filtering** by reference type, frequency, person
- **Dynamic playlists** possible once properly tagged (e.g., "All videos with salt references")

## Database Structure
References stored in `references` table, linked via `video_references` many-to-many relationship, allowing for:
- Timestamp tracking per video appearance
- Context notes for each usage
- First appearance designation
- Frequency analysis over time