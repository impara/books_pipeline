import os
import yaml
import time
import base64
from io import BytesIO
from pathlib import Path
from datetime import datetime
from loguru import logger
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv
import argparse
from typing import Optional, List, Dict, Any, Tuple

from .text_overlay_manager import TextOverlayManager
from .scene_manager import SceneManager
from .checkpoint_manager import CheckpointManager
from .api_client import APIClient
from .book_formatter import BookFormatter
from .transition_manager import TransitionManager
from .image_processor import process_and_save_images
from .prompt_manager import PromptManager

# Load environment variables
load_dotenv()

# Helper function to load config (moved from BookGenerator)
def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

class BookGenerator:
    def __init__(self, 
                 config_path: str, 
                 api_client: APIClient,
                 checkpoint_manager: CheckpointManager,
                 text_overlay_manager: TextOverlayManager,
                 scene_manager: SceneManager,
                 transition_manager: TransitionManager,
                 prompt_manager: PromptManager):
        """Initialize the book generator with configuration and injected managers."""
        self.config = load_config(config_path) # Still load config internally for now
        
        # Assign injected managers
        self.api_client = api_client
        self.checkpoint_manager = checkpoint_manager
        self.text_overlay_manager = text_overlay_manager
        self.scene_manager = scene_manager
        self.transition_manager = transition_manager
        self.prompt_manager = prompt_manager
        
        # Set target image dimensions
        image_settings = self.config.get('image_settings', {})
        self.image_width = image_settings.get('width', 1024)
        self.image_height = image_settings.get('height', 1024)
        
        # Try to load checkpoint if it exists
        # CheckpointManager is already injected and initialized
        checkpoint_data = self.checkpoint_manager._load_checkpoint() 
        
        if checkpoint_data:
            logger.info(f"Resuming from checkpoint: {checkpoint_data['output_dir']}")
            self.output_dir = Path(checkpoint_data['output_dir'])
            self.completed_pages = checkpoint_data['completed_pages']
            self.last_attempted_page = checkpoint_data.get('last_attempted_page', 0)
            self.previous_descriptions = checkpoint_data.get('previous_descriptions', {})
            self.conversation_history = checkpoint_data.get('conversation_history', [])
            self.pages_with_images = checkpoint_data.get('pages_with_images', set())
            self.original_image_files = checkpoint_data.get('original_image_files', {})
            # Pass loaded previous descriptions to the injected scene manager
            self.scene_manager.set_previous_descriptions(self.previous_descriptions) 
        else:
            # Start fresh
            self.output_dir = self._create_output_directory()
            self.completed_pages = set()
            self.last_attempted_page = 0
            self.previous_descriptions = {}
            self.conversation_history = []
            self.pages_with_images = set()
            self.original_image_files = {}
            self.checkpoint_manager.set_output_dir(self.output_dir)
        
        # Configure logging
        logger.add(
            self.output_dir / "generation.log",
            rotation="500 MB",
            level="INFO"
        )
        
        # Create outputs directory
        self.processed_dir = self.output_dir / "processed_book"
        self.processed_dir.mkdir(exist_ok=True)
        
        # Managers are now injected, remove their internal initialization:
        # self.text_overlay_manager = TextOverlayManager(Path("assets/fonts"), self.config)
        # self.scene_manager = SceneManager(self.config)
        # self.scene_manager.set_previous_descriptions(self.previous_descriptions) # Moved earlier
        # self.transition_manager = TransitionManager(self.config)
        # self.prompt_manager = PromptManager(self.config, self.scene_manager)
        
        # Font configuration (relies on injected text_overlay_manager)
        self.fonts_dir = Path("assets/fonts")
        self.fonts_dir.mkdir(parents=True, exist_ok=True)
        self.text_styles = self.text_overlay_manager._initialize_text_styles()

    def _create_output_directory(self) -> Path:
        """Create a unique output directory for the book."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_name = self.config['book']['title'].lower().replace(" ", "_")
        output_dir = Path(f"outputs/{project_name}_{timestamp}")
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir
        
    def generate_page_text(self, page_number: int):
        """Generate text for a single page of the book."""
        try:
            # Use predefined story text if available
            if story_pages := self.config.get('story', {}).get('pages'):
                if 0 <= page_number - 1 < len(story_pages):
                    story_text = story_pages[page_number - 1]
                    page_dir = self.output_dir / f"page_{page_number:02d}"
                    page_dir.mkdir(exist_ok=True)
                    story_file = page_dir / "story_text.txt"
                    with open(story_file, 'w') as f: f.write(story_text)
                    self.previous_descriptions[page_number] = story_text
                    self.checkpoint_manager.add_page_description(page_number, story_text)
                    logger.info(f"Used predefined text for page {page_number}")
                    return story_text
            
            # Generate text using PromptManager
            prompt = self.prompt_manager.generate_text_prompt(page_number, self.previous_descriptions)
            
            # Calculate dynamic temperature
            temperature = self._calculate_temperature(page_number)
            
            # Call APIClient to get the *extracted* story text
            # Pass page_number and temperature for better extraction and control
            extracted_story_text, success = self.api_client.generate_story_text(
                prompt, 
                self.conversation_history, 
                page_number=page_number,
                temperature=temperature
            )
            
            if success and extracted_story_text: # Check if text was successfully extracted
                # Update conversation history (using the extracted text)
                # Note: Might want to store the *full* response in a debug log if needed
                self.conversation_history.extend([prompt, extracted_story_text])
                self.checkpoint_manager.add_to_conversation_history(extracted_story_text) # Store extracted text
                if len(self.conversation_history) > 10:
                    self.conversation_history = self.conversation_history[-10:]
                
                story_text = extracted_story_text # Assign the directly returned text
                
                # Save the raw response and the extracted text separately
                page_dir = self.output_dir / f"page_{page_number:02d}"
                page_dir.mkdir(exist_ok=True)
                # Optional: Save the raw response for debugging
                # with open(page_dir / "text_raw_response.txt", 'w') as f: f.write(raw_response_text_if_needed) 
                with open(page_dir / "story_text.txt", 'w') as f: f.write(story_text)
                
                # The backup generation logic might still be useful if the *extracted* text is too short
                if len(story_text.split()) < 5:
                    logger.warning(f"Extracted story text is very short for page {page_number}. Generating backup.")
                    # The backup generation now needs the original prompt or context, not the raw response
                    # We'll need to adjust _generate_backup_story_text or its prompt creation
                    backup_story = self._generate_backup_story_text(page_number, story_text) # Pass the extracted text as context maybe?
                    if backup_story:
                        story_text = backup_story # Use backup if successful
                        # Overwrite story_text.txt with backup
                        with open(page_dir / "story_text.txt", 'w') as f: f.write(story_text) 
                
                # Store final description and update checkpoint
                self.previous_descriptions[page_number] = story_text
                self.checkpoint_manager.add_page_description(page_number, story_text)
                
                logger.info(f"Generated and saved text for page {page_number}")
                return story_text
            elif success and not extracted_story_text:
                # Handle case where API call succeeded but extraction failed within APIClient
                 logger.error(f"API call succeeded but failed to extract story text for page {page_number}. Check APIClient logs.")
                 raise Exception(f"Text extraction failed for page {page_number}")
            else:
                # Handle API call failure
                raise Exception(f"API call failed for text generation for page {page_number}")
            
        except Exception as e:
            logger.error(f"Error generating text for page {page_number}: {str(e)}")
            raise

    def _calculate_temperature(self, page_number: int) -> float:
        """Calculate generation temperature based on position within story phase."""
        # (Keep this method here)
        current_phase = self.scene_manager._get_story_phase(page_number)
        if current_phase and 'story_progression' in self.config:
            phase_mapping = self.config['story_progression']['phase_mapping'].get(current_phase, {})
            phase_start = phase_mapping.get('start_page', page_number)
            phase_end = phase_mapping.get('end_page', page_number)
            
            phase_length = max(1, phase_end - phase_start + 1)
            phase_position = (page_number - phase_start) / max(1, phase_length - 1) if phase_length > 1 else 0
            
            temp_config = self.config.get('generation', {}).get('temperature', {})
            base_temp = temp_config.get('base', 0.2)
            phase_increment = temp_config.get('phase_increment', 0.3)
            max_temp = temp_config.get('max', 0.5)
            
            temp = min(base_temp + (phase_position * phase_increment), max_temp)
            logger.info(f"Dynamic temp {temp:.2f} for page {page_number} (pos {phase_position:.2f} in '{current_phase}')")
            return temp
        
        return self.config.get('generation', {}).get('temperature', {}).get('base', 0.2)

    def generate_page_image(self, page_number: int, prompt_text: str, scene_requirements: dict, required_characters: List[dict]) -> Optional[str]:
        """Generate an image for the given page and save it."""
        logger.info(f"Generating image for page {page_number}")
        
        try:
            # Analyze Transition
            transition_requirements = {}
            if page_number > 1:
                previous_page = page_number - 1
                # Call TransitionManager directly (already done by PromptManager implicitly? Check PM.)
                # transition_requirements = self.transition_manager.analyze_transition(page_number, previous_page)
                # if transition_requirements: logger.info(f"Generated transition requirements for page {page_number}")

            # --- Determine reference page using SceneManager --- #
            reference_page_num = self.scene_manager.find_reference_page(page_number, self.original_image_files)
            reference_image_b64 = None
            if reference_page_num:
                ref_image_path = self.original_image_files.get(reference_page_num)
                if ref_image_path and os.path.exists(ref_image_path):
                    try:
                        with open(ref_image_path, 'rb') as f: image_data = f.read()
                        reference_image_b64 = base64.b64encode(image_data).decode('utf-8')
                        logger.info(f"Found reference image from page {reference_page_num} for page {page_number}")
                        # Note: Reference handling guidance is now handled within APIClient or PromptManager
                    except Exception as e:
                        logger.warning(f"Failed to load reference image from {ref_image_path}: {e}")
                else:
                    logger.warning(f"Reference image path for page {reference_page_num} not found or missing in original_image_files.")
            # --- End reference finding --- #
            
            # Generate the image prompt using PromptManager
            # PromptManager will need the reference page number to generate appropriate guidance
            final_prompt_text = self.prompt_manager.generate_image_prompt(
                page_number=page_number,
                story_text=prompt_text,
                scene_requirements=scene_requirements,
                required_characters=required_characters,
                reference_page_num=reference_page_num, # Pass the determined ref page
                original_image_files=self.original_image_files # Pass the dictionary of saved files
            )
            
            # Generate the image using the API client
            # Pass reference_image_b64 directly
            response = self.api_client.generate_image(
                prompt_text=final_prompt_text, 
                reference_image_b64=reference_image_b64, # Pass the loaded image data
                page_number=page_number,
                scene_requirements=scene_requirements # Pass scene_reqs for potential API use (e.g., overrides)
            )
            
            # Process and save the images using the external processor
            # Pass the story_text (which was input to this function)
            image_count, first_original_path = self._process_and_save_images(response, page_number, prompt_text) 
            
            if image_count > 0 and first_original_path:
                logger.info(f"Successfully generated image for page {page_number}: {first_original_path}")
                # Return the relative path from the output directory
                return first_original_path # Return relative path
            
            logger.error(f"No images were generated or saved for page {page_number}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to generate image for page {page_number}: {str(e)}")
            return None

    def _check_for_character_duplicates(self, prompt: str, required_characters: List[dict]) -> None:
        """Post-process check for potential character duplicates in the prompt."""
        # (Keep this method here for debugging prompts)
        import re
        required_char_names = [char['name'] for char in required_characters]
        all_char_names = [info['name'] for info in self.config.get('characters', {}).values()]
        non_required_chars = [name for name in all_char_names if name not in required_char_names]
        
        logger.info("DUPLICATE DETECTION CHECK:")
        logger.info(f"Required: {', '.join(required_char_names)}")
        logger.info(f"Non-Required: {', '.join(non_required_chars)}")
        
        for char_name in required_char_names:
            char_section_pattern = fr"Character: {re.escape(char_name)}.*?EXACTLY ONCE"
            char_sections = re.findall(char_section_pattern, prompt, re.IGNORECASE | re.DOTALL)
            if len(char_sections) > 1: logger.warning(f"POTENTIAL DUPLICATE: '{char_name}' mentioned {len(char_sections)} times in instructions!")
            if len(char_sections) == 0: logger.warning(f"POTENTIAL ISSUE: '{char_name}' missing 'EXACTLY ONCE' instruction!")
        
        for char_name in non_required_chars:
            char_req_pattern = fr"{re.escape(char_name)}.*?MUST APPEAR EXACTLY ONCE"
            if re.search(char_req_pattern, prompt, re.IGNORECASE | re.DOTALL):
                logger.error(f"NON-REQUIRED CHAR INCLUDED: '{char_name}' in character requirements!")
        
        total_match = re.search(r"TOTAL CHARACTERS: EXACTLY (\d+)", prompt)
        if total_match:
            specified_count = int(total_match.group(1))
            if specified_count != len(required_characters):
                logger.error(f"COUNT MISMATCH: Specified {specified_count}, actual {len(required_characters)}!")
        else: logger.warning("No explicit total character count found!")
        logger.info("END DUPLICATE CHECK")

    def _process_and_save_images(self, image_data_list: Optional[List[str]], page_number: int, text: str) -> Tuple[int, Optional[str]]:
        """Process and save images by calling the external image processor."""
        image_settings = self.config.get('image_settings', {})
        # Extract individual settings to pass to the function
        target_width = image_settings.get('width', 1024)
        target_height = image_settings.get('height', 1024)
        image_format = image_settings.get('format', 'RGB')
        resize_method_name = image_settings.get('resize_method', 'LANCZOS')
        maintain_aspect = image_settings.get('maintain_aspect_ratio', True)
        smart_crop = image_settings.get('smart_crop', False)
        bg_color = image_settings.get('background_color', 'white')
        
        image_count, first_original_image_path = process_and_save_images(
            image_data_list=image_data_list, 
            page_number=page_number, 
            text=text,
            output_dir=self.output_dir, 
            processed_dir=self.processed_dir,
            # Pass managers
            text_overlay_manager=self.text_overlay_manager,
            checkpoint_manager=self.checkpoint_manager,
            # Pass individual settings
            target_width=target_width,
            target_height=target_height,
            image_format=image_format,
            resize_method_name=resize_method_name,
            maintain_aspect=maintain_aspect,
            smart_crop=smart_crop,
            bg_color=bg_color
        )
        if first_original_image_path:
             absolute_path = self.output_dir / first_original_image_path
             self.original_image_files[page_number] = str(absolute_path)
        return image_count, first_original_image_path

    def generate_cover(self):
        """Generate the book cover image and apply text overlay."""
        # (Refactor cover generation to use PromptManager)
        logger.info("Attempting to generate book cover...")
        cover_config = self.config.get('cover', {})
        if not cover_config.get('generate_cover', False):
            logger.info("Cover generation disabled. Skipping.")
            return

        try:
            # Get cover prompt text and overlay text from PromptManager
            full_prompt_text, cover_text_for_overlay = self.prompt_manager.generate_cover_prompt()
            
            # Determine reference image
            ref_page_num = cover_config.get('reference_page_for_style', 1)
            ref_image_path = self.output_dir / f"page_{ref_page_num:02d}" / "image_original_1.png"
            reference_image_b64 = None
            if ref_image_path.exists():
                logger.info(f"Using image from page {ref_page_num} as style reference for the cover.")
                with open(ref_image_path, "rb") as f: reference_image_b64 = base64.b64encode(f.read()).decode('utf-8')
            else:
                logger.warning(f"Reference image not found at {ref_image_path}. Generating cover without style reference.")

            # Generate image via API
            image_data_list = self.api_client.generate_image(
                prompt_text=full_prompt_text,
                page_number=0, # Using 0 for cover
                reference_image_b64=reference_image_b64
            )

            if not image_data_list:
                logger.error("API did not return image data for the cover.")
                return

            # Save original cover image (using first result)
            cover_original_path = self.output_dir / "cover_original.png"
            try:
                img_data = base64.b64decode(image_data_list[0])
                img = Image.open(BytesIO(img_data))
                if img.size != (self.image_width, self.image_height):
                   logger.warning(f"Resizing generated cover {img.size} to target ({self.image_width}x{self.image_height}).")
                   img = img.resize((self.image_width, self.image_height), Image.Resampling.LANCZOS)
                img.save(cover_original_path)
                logger.info(f"Saved original cover image to {cover_original_path}")
            except Exception as e:
                logger.error(f"Failed to save original cover image: {e}")
                return

            # Apply text overlay
            cover_final_path = self.output_dir / "cover_final.png"
            import shutil
            shutil.copy2(cover_original_path, cover_final_path)
            position = cover_config.get('cover_text_position', 'middle')
            
            self.text_overlay_manager.apply_text_overlay(
                image_path=cover_final_path, text=cover_text_for_overlay, 
                page_number=0, position=position, is_cover=True
            )
            logger.info(f"Applied text overlay and saved final cover to {cover_final_path}")

        except Exception as e:
            logger.error(f"Failed to generate cover: {e}")

    def generate_page(self, page_number: int):
        """Generate a complete page (text and image)."""
        # Skip if already completed
        if page_number in self.completed_pages:
            logger.info(f"Skipping page {page_number} (already completed)")
            return
            
        self.last_attempted_page = page_number
        self.checkpoint_manager.update_last_attempted_page(page_number)
        
        try:
            # First generate the text
            story_text = self.generate_page_text(page_number)
            
            # Get scene requirements
            scene_requirements = self.scene_manager.get_scene_requirements(page_number, story_text)
            
            # Get required characters (now from SceneManager)
            required_characters = self.scene_manager.get_required_characters(page_number, story_text)
            
            # Then generate the image based on the text
            image_path = self.generate_page_image(page_number, story_text, scene_requirements, required_characters)
            
            if image_path:
                logger.info(f"Successfully generated page {page_number} with image: {image_path}")
                # Mark as having images
                self.pages_with_images.add(page_number)
            else:
                logger.warning(f"Page {page_number} was generated but without images")
            
            # Mark as completed and update checkpoint
            self.completed_pages.add(page_number)
            self.checkpoint_manager.add_completed_page(page_number)
                
        except Exception as e:
            logger.error(f"Error generating page {page_number}: {str(e)}")
            raise

    def generate_book(self):
        """Generate the complete book."""
        total_pages = self.config['book']['page_count']
        if self.completed_pages:
            logger.info(f"Resuming book generation: {len(self.completed_pages)}/{total_pages} pages already completed")
        else:
            logger.info("Starting book generation...")
        
        try:
            for page_num in range(1, total_pages + 1):
                if page_num in self.completed_pages:
                    logger.info(f"Page {page_num} already completed, skipping")
                    continue
                    
                logger.info(f"Generating page {page_num}...")
                self.generate_page(page_num)
                
                # Add delay between pages to avoid rate limits
                if page_num < total_pages:
                    logger.info(f"Waiting 8 seconds before next page...")
                    time.sleep(8)  # Increased delay to further reduce rate limit issues
            
            logger.info("Book generation completed!")

            # Generate the cover image
            self.generate_cover()
            
            # Create a final book PDF or HTML file
            self._create_final_book()
            
            # If print settings are configured, calculate and log spine width for KDP Cover Creator
            if self.config.get('print_settings'):
                BookFormatter.calculate_and_log_spine_width(self.config)

            # Mark book generation as complete
            self.checkpoint_manager.mark_as_complete()
            
        except Exception as e:
            logger.error(f"Book generation interrupted: {str(e)}")
            logger.info(f"You can resume generation later from the last checkpoint")
            raise
    
    def _create_final_book(self):
        """Create a final book file with consistent layout."""
        try:
            # Initialize book formatter with specific config sections
            formatter = BookFormatter(
                output_dir=self.output_dir, 
                book_config=self.config.get('book', {}),
                characters_config=self.config.get('characters', {}),
                print_settings=self.config.get('print_settings', {}),
                metadata_config=self.config.get('metadata', {}),
                cover_config=self.config.get('cover', {}),
                output_formats_config=self.config.get('output_formats', {})
            )
            
            # Create all supported formats
            formats = formatter.create_all_formats()
            
            logger.info("Created book in multiple formats:")
            for format_name, file_path in formats.items():
                logger.info(f"- {format_name.upper()}: {file_path}")
            
        except Exception as e:
            logger.error(f"Error creating final book: {str(e)}")

    def regenerate_pages(self, page_numbers: list):
        """Regenerate specific pages while maintaining consistency and visual flow."""
        logger.info(f"Regenerating pages: {page_numbers}")
        
        # Sort page numbers to ensure we process them in order
        page_numbers.sort()
        
        # Backup the original state
        original_completed_pages = self.completed_pages.copy()
        original_pages_with_images = self.pages_with_images.copy()
        original_previous_descriptions = self.previous_descriptions.copy()
        # Backup existing characters from scene_manager
        # original_existing_characters = self.scene_manager.existing_characters.copy()
        original_image_files = self.original_image_files.copy()
        
        try:
            # Remove pages from completed_pages to force regeneration
            for page_num in page_numbers:
                if page_num in self.completed_pages:
                    self.completed_pages.remove(page_num)
                    logger.info(f"Removed page {page_num} from completed pages for regeneration")
            
            # Process pages in sequence to maintain the flow
            for page_num in page_numbers:
                logger.info(f"Regenerating page {page_num}")
                
                # --- Use SceneManager to find reference page --- #
                best_ref_page = self.scene_manager.find_reference_page(page_num, self.original_image_files)
                logger.info(f"Using reference page {best_ref_page} for consistency in regeneration")
                
                # Fallback strategy if needed (this might be redundant now? Check SceneManager logic)
                if best_ref_page is None and page_num > 1:
                    # Try to find the closest preceding page with a saved image
                    for prev_page in range(page_num-1, 0, -1):
                        if prev_page in self.original_image_files:
                           best_ref_page = prev_page
                           logger.info(f"Found fallback reference page {best_ref_page} for regeneration (closest previous)")
                           break
                # --- End reference finding --- #
                
                # Temporarily ensure reference page info exists if needed
                if best_ref_page and best_ref_page not in self.original_image_files:
                     # This case might indicate an issue, as find_reference_page should only return pages from original_image_files
                     logger.warning(f"Reference page {best_ref_page} chosen but not found in original_image_files dictionary. Re-adding temporarily if it exists in backup.")
                     if best_ref_page in original_image_files: # Check the backup copy
                         self.original_image_files[best_ref_page] = original_image_files[best_ref_page]
                         self.checkpoint_manager.add_original_image_file(best_ref_page, original_image_files[best_ref_page])
                         # We might not need pages_with_images anymore if we rely on original_image_files
                         # self.pages_with_images.add(best_ref_page)
                     else:
                         logger.error(f"Could not restore original image file path for reference page {best_ref_page}. Proceeding without reference.")
                         best_ref_page = None # Cannot use this reference
                
                # Set a flag to indicate we're regenerating (for stronger consistency guidance)
                # This flag might be better handled inside PromptManager now
                # self.is_regenerating = True 
                
                # Generate the page (will use the logic updated above)
                self.generate_page(page_num)
                
                # Clear the regeneration flag
                # self.is_regenerating = False
                
                # Add delay between pages to avoid rate limits
                if page_num != page_numbers[-1]:
                    logger.info(f"Waiting 8 seconds before next page...")
                    time.sleep(8)
                    
                # Clean up temporary reference if added? (Maybe not necessary if state is managed correctly)
                # if best_ref_page and best_ref_page not in original_pages_with_images:
                #     self.pages_with_images.remove(best_ref_page)
            
            logger.info(f"Finished regenerating pages: {page_numbers}")
            
            # Save checkpoint
            self.checkpoint_manager.save()
            
        except Exception as e:
            logger.error(f"Error during regeneration: {str(e)}")
            # In case of error, restore original state
            self.completed_pages = original_completed_pages
            self.pages_with_images = original_pages_with_images
            self.previous_descriptions = original_previous_descriptions
            # self.scene_manager.existing_characters = original_existing_characters
            self.original_image_files = original_image_files
            raise

    def _generate_style_requirements(self, scene_requirements: dict) -> str:
        style_parts = []
        
        # Add art style
        if art_style := scene_requirements.get('art_style'):
            style_parts.append(f"Art style: {art_style}.")
        
        # Add time period
        if time_period := scene_requirements.get('time_period'):
            style_parts.append(f"Time period: {time_period}.")
        
        # Add location style
        if location := scene_requirements.get('location'):
            style_parts.append(f"Location style: {location}.")
        
        return " ".join(style_parts)

    def _generate_backup_story_text(self, page_number: int, context_text: str) -> Optional[str]:
        """Generate a backup story text when extraction fails or text is too short."""
        try:
            # Create backup prompt using PromptManager
            prompt = self.prompt_manager.generate_backup_text_prompt(
                page_number=page_number,
                context_text=context_text,
                previous_descriptions=self.previous_descriptions
            )
             
            # Calculate temperature (might use a different one for backup?)
            backup_temp = self._calculate_temperature(page_number) # Or a fixed higher/lower value?
            
            # Call API Client
            backup_text, success = self.api_client.generate_backup_story(
                prompt=prompt,
                temperature=backup_temp,
                page_number=page_number # Pass page number for extraction hint
            )
            
            if success:
                logger.info(f"Generated backup story text for page {page_number}")
                return backup_text # APIClient.generate_backup_story now extracts
            else:
                logger.error("Failed to generate backup story text via API")
                return None
            
        except Exception as e:
            logger.error(f"Error generating backup story for page {page_number}: {str(e)}")
            return None

def handle_rate_limit_retry(max_retries=3, initial_wait=20):
    """Try to resume book generation with exponential backoff for rate limits."""
    retry_count = 0
    wait_time = initial_wait
    config_path = "config.yaml" # Define config path here
    
    # Load config once outside the loop
    try:
        config = load_config(config_path)
    except Exception as e:
        logger.error(f"Failed to load configuration {config_path} for retry logic: {e}")
        return # Cannot proceed without config

    while retry_count < max_retries:
        try:
            # Instantiate managers
            api_client = APIClient(config.get('generation', {}))
            checkpoint_manager = CheckpointManager()
            text_overlay_manager = TextOverlayManager(Path("assets/fonts"), config.get('image_settings', {}), config.get('cover', {}))
            # Instantiate TransitionManager first as SceneManager needs it
            transition_manager = TransitionManager(
                settings=config.get('settings', {}),
                environment_types=config.get('environment_types', {}),
                transition_rules=config.get('transition_rules', {}),
                environment_transitions=config.get('environment_transitions', {}),
                page_emotions=config.get('page_emotions', {}),
                story_progression=config.get('story_progression', {})
            )
            # Instantiate SceneManager with specific config sections and TransitionManager
            scene_manager = SceneManager(
                settings=config.get('settings', {}),
                characters=config.get('characters', {}),
                story_progression=config.get('story_progression', {}),
                page_emotions=config.get('page_emotions', {}),
                environment_types=config.get('environment_types', {}),
                scene_management=config.get('scene_management', {}),
                story_beats=config.get('story', {}).get('story_beats', {}),
                transition_manager=transition_manager
            )
            # Instantiate PromptManager with SceneManager, TransitionManager and specific config sections
            prompt_manager = PromptManager(
                book_config=config.get('book', {}),
                characters_config=config.get('characters', {}),
                generation_config=config.get('generation', {}),
                image_settings=config.get('image_settings', {}),
                cover_config=config.get('cover', {}),
                metadata_config=config.get('metadata', {}),
                scene_manager=scene_manager,
                transition_manager=transition_manager # Pass transition_manager
            )

            # Instantiate BookGenerator with injected managers
            generator = BookGenerator(
                config_path=config_path, 
                api_client=api_client,
                checkpoint_manager=checkpoint_manager,
                text_overlay_manager=text_overlay_manager,
                scene_manager=scene_manager,
                transition_manager=transition_manager,
                prompt_manager=prompt_manager
            )
            # Scene manager needs previous descriptions set after generator init loads checkpoint
            # This happens inside BookGenerator.__init__ now

            generator.generate_book()
            # If successful, exit the loop
            break
        except Exception as e:
            error_str = str(e).lower()
            if "rate limit" in error_str or "quota" in error_str:
                retry_count += 1
                if retry_count >= max_retries:
                    logger.error(f"Maximum retries ({max_retries}) exceeded. Giving up.")
                    break
                    
                logger.warning(f"Rate limit hit. Waiting {wait_time} seconds before retry {retry_count}/{max_retries}...")
                time.sleep(wait_time)
                # Exponential backoff - double the wait time for next attempt
                wait_time *= 2
            else:
                # If it's not a rate limit error, don't retry
                logger.error(f"Error not related to rate limits: {str(e)}")
                break

def main():
    """Main entry point for the book generation script."""
    config_path = "config.yaml"
    
    if not os.path.exists(config_path):
        logger.error(f"Configuration file not found: {config_path}")
        return
        
    # Load config first
    try:
        config = load_config(config_path)
    except Exception as e:
        logger.error(f"Failed to load configuration {config_path}: {e}")
        return # Cannot proceed without config
    
    parser = argparse.ArgumentParser(description='Generate a children\'s book with text and illustrations.')
    parser.add_argument('--retry', action='store_true', help='Auto-retry on rate limits')
    parser.add_argument('--regenerate', type=str, help='Regenerate specific pages (comma-separated)')
    parser.add_argument('--apply-text', type=str, nargs='*', help='Apply text overlay to existing images. Optional arguments: [position] [page_num|cover]. Position: top, middle, bottom (default: bottom). Target: specific page number, "cover", or blank for all pages.')
    args = parser.parse_args()
    
    # Instantiate managers before BookGenerator
    api_client = APIClient(config.get('generation', {}))
    checkpoint_manager = CheckpointManager()
    text_overlay_manager = TextOverlayManager(Path("assets/fonts"), config.get('image_settings', {}), config.get('cover', {}))
    # Instantiate TransitionManager first as SceneManager needs it
    transition_manager = TransitionManager(
        settings=config.get('settings', {}),
        environment_types=config.get('environment_types', {}),
        transition_rules=config.get('transition_rules', {}),
        environment_transitions=config.get('environment_transitions', {}),
        page_emotions=config.get('page_emotions', {}),
        story_progression=config.get('story_progression', {})
    )
    # Instantiate SceneManager with specific config sections and TransitionManager
    scene_manager = SceneManager(
        settings=config.get('settings', {}),
        characters=config.get('characters', {}),
        story_progression=config.get('story_progression', {}),
        page_emotions=config.get('page_emotions', {}),
        environment_types=config.get('environment_types', {}),
        scene_management=config.get('scene_management', {}),
        story_beats=config.get('story', {}).get('story_beats', {}),
        transition_manager=transition_manager
    )
    # Instantiate PromptManager with SceneManager, TransitionManager and specific config sections
    prompt_manager = PromptManager(
        book_config=config.get('book', {}),
        characters_config=config.get('characters', {}),
        generation_config=config.get('generation', {}),
        image_settings=config.get('image_settings', {}),
        cover_config=config.get('cover', {}),
        metadata_config=config.get('metadata', {}),
        scene_manager=scene_manager,
        transition_manager=transition_manager # Pass transition_manager
    )

    # Instantiate BookGenerator with injected managers
    generator = BookGenerator(
        config_path=config_path, 
        api_client=api_client,
        checkpoint_manager=checkpoint_manager,
        text_overlay_manager=text_overlay_manager,
        scene_manager=scene_manager,
        transition_manager=transition_manager,
        prompt_manager=prompt_manager
    )
    # Scene manager needs previous descriptions set after generator init loads checkpoint
    # This happens inside BookGenerator.__init__ now
    
    if args.apply_text:
        # Parse text placement options
        position = "bottom"  # default position
        target = "all"  # default to all pages
        
        if args.apply_text:  # args.apply_text is a list of optional arguments
            for arg in args.apply_text:
                if arg in ["top", "middle", "bottom"]:
                    position = arg
                else:
                    target = arg # Can be a page number or "cover"
        
        logger.info(f"Applying text overlays with position: {position} to target: {target}")

        # --- Handle Cover Application --- #
        if target == "cover":
            cover_original_path = generator.output_dir / "cover_original.png"
            cover_final_path = generator.output_dir / "cover_final.png"
            if cover_original_path.exists():
                logger.info(f"Applying text overlay to cover at {position}")
                # Get cover title/author from config
                book_config = generator.config.get('book', {})
                cover_config = generator.config.get('cover', {})
                meta_config = generator.config.get('metadata', {})
                title = cover_config.get('cover_title') or book_config.get('title', 'My Book')
                author = cover_config.get('cover_author') or meta_config.get('author') or 'Generated by AI'
                cover_text = f"{title}\n{author}"

                # Copy original to final path first
                import shutil
                shutil.copy2(cover_original_path, cover_final_path)
                
                # Apply overlay using cover style
                try:
                    generator.text_overlay_manager.apply_text_overlay(
                        image_path=cover_final_path, 
                        text=cover_text, 
                        page_number=0, # Using 0 to denote cover
                        position=position,
                        is_cover=True 
                    )
                    logger.info(f"Applied text overlay to {cover_final_path}")
                except Exception as e:
                     logger.error(f"Failed to apply text overlay to cover: {e}")
            else:
                logger.error(f"Original cover image not found at {cover_original_path}. Cannot apply text.")
            
            logger.info("Finished applying text to cover.")
            return # Exit after processing cover

        # --- Handle Page Application (Existing Logic Adapted) --- #
        target_page_num = None
        if target != "all":
            try:
                target_page_num = int(target)
            except ValueError:
                logger.error(f"Invalid target specified: {target}. Must be a page number, 'cover', or blank for all.")
                return

        logger.info(f"Applying text to pages" + (f" (specifically page {target_page_num})" if target_page_num is not None else " (all pages)"))

        # Find all existing page directories in the generator's output dir
        for page_dir in sorted(generator.output_dir.glob("page_*")):
            try:
                # Extract page number from directory name
                page_num = int(page_dir.name.split('_')[1])
                
                # Skip if not the target page
                if target_page_num is not None and page_num != target_page_num:
                    continue
                
                # Check if original image exists
                original_image = page_dir / "image_original_1.png"
                if not original_image.exists():
                    logger.warning(f"Original image not found for page {page_num}, skipping")
                    continue
                
                # Check if story text exists
                story_text_file = page_dir / "story_text.txt"
                if not story_text_file.exists():
                    logger.warning(f"Story text not found for page {page_num}, skipping")
                    continue
                
                # Read the story text
                with open(story_text_file, 'r') as f:
                    story_text = f.read().strip()
                
                logger.info(f"Applying text overlay to page {page_num} at {position}")
                
                # Copy original image to both locations before applying overlay
                image_with_text = page_dir / "image_1.png"
                processed_dir = page_dir.parent / "processed_book"
                processed_file = processed_dir / f"page_{page_num:02d}.png"
                
                # Ensure processed directory exists
                processed_dir.mkdir(exist_ok=True)
                
                # Copy original image to both locations
                import shutil
                shutil.copy2(original_image, image_with_text)
                shutil.copy2(original_image, processed_file)
                
                # Apply text overlay to both copies
                generator.text_overlay_manager.apply_text_overlay(image_with_text, story_text, page_num, position=position)
                generator.text_overlay_manager.apply_text_overlay(processed_file, story_text, page_num, is_final=True, position=position)
                
            except Exception as e:
                logger.error(f"Error processing page {page_dir.name}: {str(e)}")
                continue
        
        logger.info("Finished applying text overlays to pages.")
        return # Exit after processing pages
    
    # --- Regular Generation Flow (If no special flags) --- #
    if args.retry:
        logger.info("Starting with auto-retry for rate limits")
        handle_rate_limit_retry()
    else:
        try:
            if args.regenerate:
                # Handle cover regeneration separately
                if args.regenerate.strip().lower() == 'cover':
                    logger.info("Regenerating cover...")
                    generator.generate_cover()
                    logger.info("Cover regeneration complete.")
                else:
                    # Convert comma-separated string to list of integers for page numbers
                    try:
                        pages_to_regenerate = [int(x.strip()) for x in args.regenerate.split(',')]
                        generator.regenerate_pages(pages_to_regenerate)
                    except ValueError:
                         logger.error(f"Invalid page number found in --regenerate argument: {args.regenerate}. Please provide comma-separated page numbers or 'cover'.")
                         raise # Re-raise the error to stop execution gracefully
            else:
                generator.generate_book()
        except Exception as e:
            logger.error(f"Failed to generate book: {str(e)}")
            logger.info("Tip: Run with --retry flag to automatically retry after rate limits")
            logger.info("Tip: Run with --regenerate 1,2,3 to regenerate specific pages")
            logger.info("Tip: Run with --apply-text to only apply text overlay to existing images")

if __name__ == "__main__":
    main() 