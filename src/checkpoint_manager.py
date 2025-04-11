import os
import pickle
from pathlib import Path
from datetime import datetime
from loguru import logger
from typing import Dict, Set, List, Optional, Any

class CheckpointManager:
    def __init__(self, checkpoint_file: str = "book_generation_checkpoint.pkl"):
        """Initialize the checkpoint manager with a checkpoint file path."""
        self.checkpoint_file = Path(checkpoint_file)
        
        # Initialize state variables
        self.output_dir: Optional[Path] = None
        self.completed_pages: Set[int] = set()
        self.last_attempted_page: int = 0
        self.previous_descriptions: Dict[int, str] = {}
        self.conversation_history: List[str] = []
        self.pages_with_images: Set[int] = set()
        self.original_image_files: Dict[int, str] = {}
        
        # Try to load existing checkpoint
        self._load_checkpoint()

    def _save_checkpoint(self) -> None:
        """Save checkpoint data to file."""
        checkpoint_data = {
            'output_dir': str(self.output_dir) if self.output_dir else None,
            'completed_pages': self.completed_pages,
            'last_attempted_page': self.last_attempted_page,
            'previous_descriptions': self.previous_descriptions,
            'conversation_history': self.conversation_history,
            'pages_with_images': self.pages_with_images,
            'original_image_files': self.original_image_files,
            'timestamp': datetime.now().isoformat(),
            'is_complete': False  # This will be set by the book generator
        }
        
        with open(self.checkpoint_file, 'wb') as f:
            pickle.dump(checkpoint_data, f)
            
        logger.info(f"Checkpoint saved: {len(self.completed_pages)} pages completed")

    def _load_checkpoint(self) -> Optional[Dict[str, Any]]:
        """Load checkpoint data from file."""
        if not self.checkpoint_file.exists():
            return None
            
        try:
            with open(self.checkpoint_file, 'rb') as f:
                checkpoint_data = pickle.load(f)
                
            # If the book is complete, ask if user wants to regenerate pages
            if checkpoint_data.get('is_complete', False):
                logger.info("Book generation is complete. Use --regenerate to regenerate specific pages.")
            
            # Update state variables from checkpoint data
            if checkpoint_data.get('output_dir'):
                self.output_dir = Path(checkpoint_data['output_dir'])
            self.completed_pages = checkpoint_data.get('completed_pages', set())
            self.last_attempted_page = checkpoint_data.get('last_attempted_page', 0)
            self.previous_descriptions = checkpoint_data.get('previous_descriptions', {})
            self.conversation_history = checkpoint_data.get('conversation_history', [])
            self.pages_with_images = checkpoint_data.get('pages_with_images', set())
            self.original_image_files = checkpoint_data.get('original_image_files', {})
                
            return checkpoint_data
        except Exception as e:
            logger.error(f"Error loading checkpoint: {str(e)}")
            return None

    def clear_checkpoint(self) -> None:
        """Clear the checkpoint file."""
        if self.checkpoint_file.exists():
            os.remove(self.checkpoint_file)
            logger.info("Checkpoint cleared")
            
        # Reset state variables
        self.output_dir = None
        self.completed_pages = set()
        self.last_attempted_page = 0
        self.previous_descriptions = {}
        self.conversation_history = []
        self.pages_with_images = set()
        self.original_image_files = {}

    def save(self) -> None:
        """Save the current state to checkpoint."""
        self._save_checkpoint()

    def set_output_dir(self, output_dir: Path) -> None:
        """Set the output directory and save checkpoint."""
        self.output_dir = output_dir
        self.save()

    def add_completed_page(self, page_number: int) -> None:
        """Add a completed page and save checkpoint."""
        self.completed_pages.add(page_number)
        self.save()

    def remove_completed_page(self, page_number: int) -> None:
        """Remove a completed page and save checkpoint."""
        if page_number in self.completed_pages:
            self.completed_pages.remove(page_number)
            self.save()

    def update_last_attempted_page(self, page_number: int) -> None:
        """Update the last attempted page and save checkpoint."""
        self.last_attempted_page = page_number
        self.save()

    def add_page_description(self, page_number: int, description: str) -> None:
        """Add a page description and save checkpoint."""
        self.previous_descriptions[page_number] = description
        self.save()

    def remove_page_description(self, page_number: int) -> None:
        """Remove a page description and save checkpoint."""
        if page_number in self.previous_descriptions:
            del self.previous_descriptions[page_number]
            self.save()

    def add_to_conversation_history(self, text: str) -> None:
        """Add text to conversation history and save checkpoint."""
        self.conversation_history.append(text)
        # Keep only last 10 exchanges
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-10:]
        self.save()

    def add_page_with_image(self, page_number: int) -> None:
        """Add a page that has an image and save checkpoint."""
        self.pages_with_images.add(page_number)
        self.save()

    def remove_page_with_image(self, page_number: int) -> None:
        """Remove a page that has an image and save checkpoint."""
        if page_number in self.pages_with_images:
            self.pages_with_images.remove(page_number)
            self.save()

    def add_original_image_file(self, page_number: int, file_path: str) -> None:
        """Add an original image file path and save checkpoint."""
        self.original_image_files[page_number] = file_path
        self.save()

    def remove_original_image_file(self, page_number: int) -> None:
        """Remove an original image file path and save checkpoint."""
        if page_number in self.original_image_files:
            del self.original_image_files[page_number]
            self.save()

    def mark_as_complete(self) -> None:
        """Mark the book generation as complete and save checkpoint."""
        checkpoint_data = {
            'output_dir': str(self.output_dir) if self.output_dir else None,
            'completed_pages': self.completed_pages,
            'last_attempted_page': self.last_attempted_page,
            'previous_descriptions': self.previous_descriptions,
            'conversation_history': self.conversation_history,
            'pages_with_images': self.pages_with_images,
            'original_image_files': self.original_image_files,
            'timestamp': datetime.now().isoformat(),
            'is_complete': True
        }
        
        with open(self.checkpoint_file, 'wb') as f:
            pickle.dump(checkpoint_data, f)
            
        logger.info("Book generation marked as complete") 