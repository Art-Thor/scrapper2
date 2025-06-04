"""
Media download and management handler for the FunTrivia scraper.

This module handles downloading and organizing media files (images and audio)
with proper filename formatting and directory structure management.
"""

import os
import logging
import aiohttp # type: ignore
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional, Tuple, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential # type: ignore


class MediaHandler:
    """
    Handles downloading and organizing media files with proper naming conventions.
    
    Ensures that:
    - Media files are named using question localization keys
    - Files are saved to correct directories (assets/images, assets/audio)
    - Only filenames (not paths) are referenced in CSV files
    - Proper error handling and retry logic
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the media handler.
        
        Args:
            config: Configuration dictionary containing storage paths
        """
        self.logger = logging.getLogger(__name__)
        self.config = config
        
        # Ensure media directories exist
        self._ensure_media_directories()
    
    def _ensure_media_directories(self) -> None:
        """Create media directories if they don't exist."""
        directories = [
            self.config['storage']['images_dir'],
            self.config['storage']['audio_dir']
        ]
        
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Ensured directory exists: {directory}")
    
    def get_media_filename(self, question_id: str, media_type: str, source_url: str) -> str:
        """
        Generate proper filename for media file using question localization key.
        
        Args:
            question_id: Question localization key (e.g., Question_MQ_Parsed_Culture_Easy_0001)
            media_type: Type of media ('image' or 'audio')
            source_url: Original URL to determine file extension
            
        Returns:
            Filename with proper extension (e.g., Question_MQ_Parsed_Culture_Easy_0001.jpg)
        """
        # Parse URL to get file extension
        parsed_url = urlparse(source_url)
        path_parts = parsed_url.path.split('.')
        ext = path_parts[-1].lower() if len(path_parts) > 1 else ''
        
        # Determine appropriate extension based on media type
        if media_type == "audio":
            if ext not in ['mp3', 'wav', 'ogg', 'm4a']:
                ext = 'mp3'  # Default to mp3 for audio
        else:  # image
            if ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                ext = 'jpg'  # Default to jpg for images
        
        # Return filename using localization key format
        return f"{question_id}.{ext}"
    
    def get_media_filepath(self, question_id: str, media_type: str, source_url: str) -> str:
        """
        Get full file path for media file.
        
        Args:
            question_id: Question localization key
            media_type: Type of media ('image' or 'audio')
            source_url: Original URL to determine file extension
            
        Returns:
            Full file path where media should be saved
        """
        filename = self.get_media_filename(question_id, media_type, source_url)
        
        if media_type == "audio":
            directory = self.config['storage']['audio_dir']
        else:  # image
            directory = self.config['storage']['images_dir']
        
        return os.path.join(directory, filename)
    
    def get_csv_reference(self, question_id: str, media_type: str, source_url: str) -> str:
        """
        Get the filename that should be written to CSV (filename only, no path).
        
        Args:
            question_id: Question localization key
            media_type: Type of media ('image' or 'audio')
            source_url: Original URL to determine file extension
            
        Returns:
            Just the filename for CSV reference (e.g., Question_MQ_Parsed_Culture_Easy_0001.jpg)
        """
        return self.get_media_filename(question_id, media_type, source_url)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def download_media(self, url: str, question_id: str, media_type: str, 
                           user_agent: str = None) -> Optional[str]:
        """
        Download media file and save with proper localization key filename.
        
        Args:
            url: URL of the media file to download
            question_id: Question localization key (e.g., Question_MQ_Parsed_Culture_Easy_0001)
            media_type: Type of media ('image' or 'audio')
            user_agent: User agent string for HTTP requests
            
        Returns:
            Filename of downloaded file (for CSV reference) or None if failed
        """
        if not url or not question_id:
            self.logger.warning("Missing URL or question ID for media download")
            return None
        
        try:
            # Get proper file path and filename
            filepath = self.get_media_filepath(question_id, media_type, url)
            filename = self.get_csv_reference(question_id, media_type, url)
            
            # Set up HTTP headers
            headers = {}
            if user_agent:
                headers['User-Agent'] = user_agent
            
            # Download the file
            self.logger.debug(f"Downloading {media_type} from {url} to {filepath}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        # Write file to disk
                        with open(filepath, 'wb') as f:
                            f.write(await response.read())
                        
                        self.logger.info(f"Successfully downloaded {media_type} for {question_id}: {filename}")
                        return filename  # Return just filename for CSV
                    else:
                        raise Exception(f"HTTP {response.status}: Failed to download {media_type}")
                        
        except Exception as e:
            self.logger.error(f"Failed to download {media_type} for {question_id}: {e}")
            return None
    
    def validate_media_file(self, question_id: str, media_type: str, source_url: str) -> bool:
        """
        Check if media file exists and is valid.
        
        Args:
            question_id: Question localization key
            media_type: Type of media ('image' or 'audio')
            source_url: Original URL to determine expected filename
            
        Returns:
            True if file exists and is valid, False otherwise
        """
        filepath = self.get_media_filepath(question_id, media_type, source_url)
        
        if not os.path.exists(filepath):
            return False
        
        # Check file size (should be > 0)
        try:
            size = os.path.getsize(filepath)
            if size == 0:
                self.logger.warning(f"Media file is empty: {filepath}")
                return False
            return True
        except OSError as e:
            self.logger.error(f"Error checking media file {filepath}: {e}")
            return False
    
    def get_media_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics about downloaded media files.
        
        Returns:
            Dictionary with statistics for images and audio files
        """
        stats = {
            'images': {'count': 0, 'total_size_mb': 0, 'directory': self.config['storage']['images_dir']},
            'audio': {'count': 0, 'total_size_mb': 0, 'directory': self.config['storage']['audio_dir']}
        }
        
        # Count images
        images_dir = Path(self.config['storage']['images_dir'])
        if images_dir.exists():
            image_files = list(images_dir.glob('*'))
            stats['images']['count'] = len(image_files)
            stats['images']['total_size_mb'] = sum(f.stat().st_size for f in image_files if f.is_file()) / (1024*1024)
        
        # Count audio files
        audio_dir = Path(self.config['storage']['audio_dir'])
        if audio_dir.exists():
            audio_files = list(audio_dir.glob('*'))
            stats['audio']['count'] = len(audio_files)
            stats['audio']['total_size_mb'] = sum(f.stat().st_size for f in audio_files if f.is_file()) / (1024*1024)
        
        return stats
    
    def cleanup_temp_files(self) -> int:
        """
        Remove temporary media files (files with 'temp_' prefix).
        
        Returns:
            Number of files cleaned up
        """
        cleaned_count = 0
        
        for directory in [self.config['storage']['images_dir'], self.config['storage']['audio_dir']]:
            try:
                dir_path = Path(directory)
                if dir_path.exists():
                    temp_files = list(dir_path.glob('temp_*'))
                    for temp_file in temp_files:
                        try:
                            temp_file.unlink()
                            cleaned_count += 1
                            self.logger.debug(f"Removed temporary file: {temp_file}")
                        except OSError as e:
                            self.logger.warning(f"Failed to remove temp file {temp_file}: {e}")
            except Exception as e:
                self.logger.error(f"Error cleaning temp files in {directory}: {e}")
        
        if cleaned_count > 0:
            self.logger.info(f"Cleaned up {cleaned_count} temporary media files")
        
        return cleaned_count


class MediaReference:
    """
    Helper class for managing media references in question data.
    
    Ensures consistent handling of media paths and CSV references.
    """
    
    @staticmethod
    def extract_media_path(question_data: Dict[str, Any]) -> Optional[str]:
        """
        Extract media path from question data.
        
        Args:
            question_data: Question dictionary
            
        Returns:
            Media path if found, None otherwise
        """
        # Check various possible media path keys
        path_keys = ['media_path', 'image_path', 'audio_path', 'imageUrl', 'audioUrl']
        
        for key in path_keys:
            if key in question_data and question_data[key]:
                return question_data[key]
        
        return None
    
    @staticmethod
    def set_csv_media_reference(formatted_question: Dict[str, Any], question_type: str, 
                               filename: str) -> None:
        """
        Set the appropriate media reference in formatted question data for CSV output.
        
        Args:
            formatted_question: Formatted question dictionary
            question_type: Type of question ('multiple_choice', 'sound', etc.)
            filename: Media filename (just filename, no path)
        """
        if question_type == 'sound' and 'AudioPath' in formatted_question:
            formatted_question['AudioPath'] = filename
        elif question_type in ['multiple_choice', 'photo'] and 'ImagePath' in formatted_question:
            formatted_question['ImagePath'] = filename
        else:
            # For backward compatibility, set a generic media_path
            formatted_question['media_path'] = filename
    
    @staticmethod
    def get_media_type_from_question(question_type: str) -> str:
        """
        Determine media type from question type.
        
        Args:
            question_type: Type of question
            
        Returns:
            'audio' for sound questions, 'image' for others
        """
        return 'audio' if question_type == 'sound' else 'image' 