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
from text_overlay_manager import TextOverlayManager
from scene_manager import SceneManager
from checkpoint_manager import CheckpointManager
from api_client import APIClient
from typing import Optional, List, Dict, Any
from book_formatter import BookFormatter

# Load environment variables
load_dotenv()

class BookGenerator:
    def __init__(self, config_path: str):
        """Initialize the book generator with configuration."""
        self.config = self._load_config(config_path)
        
        # Initialize API client
        self.api_client = APIClient(self.config)
        
        # Set target image dimensions
        image_settings = self.config.get('image_settings', {})
        self.image_width = image_settings.get('width', 1024)
        self.image_height = image_settings.get('height', 1024)
        
        # Initialize checkpoint manager
        self.checkpoint_manager = CheckpointManager()
        
        # Try to load checkpoint if it exists
        checkpoint_data = self.checkpoint_manager._load_checkpoint()
        
        if checkpoint_data:
            logger.info(f"Resuming from checkpoint: {checkpoint_data['output_dir']}")
            self.output_dir = Path(checkpoint_data['output_dir'])
            self.completed_pages = checkpoint_data['completed_pages']
            self.last_attempted_page = checkpoint_data.get('last_attempted_page', 0)
            # Load previous page descriptions for consistency
            self.previous_descriptions = checkpoint_data.get('previous_descriptions', {})
            self.conversation_history = checkpoint_data.get('conversation_history', [])
            # Load successful image pages
            self.pages_with_images = checkpoint_data.get('pages_with_images', set())
            # Track original text-free images for reference
            self.original_image_files = checkpoint_data.get('original_image_files', {})
        else:
            # Start fresh
            self.output_dir = self._create_output_directory()
            self.completed_pages = set()
            self.last_attempted_page = 0
            # Initialize empty description history and conversation history
            self.previous_descriptions = {}
            self.conversation_history = []
            self.pages_with_images = set()
            self.original_image_files = {}
            # Save initial checkpoint
            self.checkpoint_manager.set_output_dir(self.output_dir)
        
        # Configure logging
        logger.add(
            self.output_dir / "generation.log",
            rotation="500 MB",
            level="INFO"
        )
        
        # Create an outputs directory for the processed book
        self.processed_dir = self.output_dir / "processed_book"
        self.processed_dir.mkdir(exist_ok=True)
        
        # Initialize text overlay manager
        self.text_overlay_manager = TextOverlayManager(Path("assets/fonts"), self.config)
        
        # Initialize scene manager
        self.scene_manager = SceneManager(self.config)
        self.scene_manager.set_previous_descriptions(self.previous_descriptions)
        
        # Add font configuration
        self.fonts_dir = Path("assets/fonts")
        self.fonts_dir.mkdir(parents=True, exist_ok=True)
        self.text_styles = self.text_overlay_manager._initialize_text_styles()

    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file."""
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def _create_output_directory(self) -> Path:
        """Create a unique output directory for the book."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_name = self.config['book']['title'].lower().replace(" ", "_")
        output_dir = Path(f"outputs/{project_name}_{timestamp}")
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir
        
    def _get_consistency_context(self, page_number: int):
        """Generate context from previous pages for consistency."""
        context = []
        
        # Add character descriptions from config for initial context
        for char_type, char_data in self.config['characters'].items():
            name = char_data['name']
            desc = char_data['description']
            context.append(f"{name} ({desc})")
        
        # Add previous page descriptions for continuity
        # We'll use up to 5 previous pages for context to enhance consistency
        prev_pages = range(max(1, page_number-5), page_number)
        for prev_page in prev_pages:
            if prev_page in self.previous_descriptions:
                page_desc = self.previous_descriptions[prev_page]
                context.append(f"Previous page {prev_page}: {page_desc}")
                
        return "\n".join(context)

    def _find_most_recent_image_page(self, page_number: int) -> Optional[int]:
        """Find the most suitable reference image page for consistency.
        
        Selection criteria:
        1. Earliest introduction page of a character present in the current scene (if image exists).
        2. Otherwise, the most recent page with an image.
        """
        # Get all available pages with images before the current page
        available_pages = sorted([p for p in self.original_image_files.keys() if p < page_number], reverse=True)
        
        if not available_pages:
            logger.info(f"No reference pages found for page {page_number}")
            return None

        # Try to find the earliest introduction page with an image among current characters
        try:
            scene_reqs = self.scene_manager.get_scene_requirements(page_number)
            current_chars = scene_reqs.get('characters', [])
            intro_pages_with_images = []
            
            if current_chars:
                for char_name in current_chars:
                     # Find the character type key based on name
                    char_type = next((ct for ct, cd in self.config['characters'].items() if cd['name'] == char_name), None)
                    if char_type:
                        intro_page = self.config['characters'][char_type].get('introduction', {}).get('page')
                        if intro_page and intro_page != page_number and intro_page in self.original_image_files:
                            intro_pages_with_images.append(intro_page)

            if intro_pages_with_images:
                earliest_intro_page = min(intro_pages_with_images)
                logger.info(f"Using earliest character introduction page {earliest_intro_page} as reference for page {page_number}")
                return earliest_intro_page
                
        except Exception as e:
             logger.warning(f"Could not determine character introduction page for reference due to error: {e}. Falling back.")

        # Fallback: Use the most recent page with an image
        if available_pages:
            most_recent_page = available_pages[0]
            logger.info(f"Using most recent page {most_recent_page} as reference for page {page_number}")
            return most_recent_page
            
        logger.info(f"Could not find any suitable reference page for page {page_number}")
        return None

    def generate_prompt(self, page_number: int) -> str:
        """Generate a prompt for the Gemini model."""
        book_config = self.config['book']
        
        # Get consistency context
        consistency_context = self._get_consistency_context(page_number)
        
        # Get scene requirements from scene_manager
        scene_requirements = self.scene_manager.get_scene_requirements(page_number)
        
        # Build consistency rules from config
        consistency_rules = [
            "Important consistency instructions:"
        ]
        
        # Add character consistency rules if defined in config
        if 'character_consistency' in book_config:
            consistency_rules.extend(book_config['character_consistency'])
        else:
            # Default character consistency rules
            consistency_rules.append("- Keep all character appearances EXACTLY THE SAME across all pages")
        
        # Add style consistency rules if defined in config
        if 'style_consistency' in book_config:
            consistency_rules.extend(book_config['style_consistency'])
        else:
            # Default style consistency rules
            consistency_rules.append(f"- Maintain the same art style ({book_config['art_style']}) throughout")
            consistency_rules.append("- Use the same color palette and visual style for illustrations")
        
        # Add narrative flow if we have previous context
        if consistency_context:
            consistency_rules.append(f"- **Narrative Flow:** Ensure the text flows logically from previous events ({consistency_context})")
        
        # Build text instructions from config
        text_instructions = ["FORMAT AND CONTENT INSTRUCTIONS:"]
        if 'text_instructions' in book_config:
            text_instructions.extend(book_config['text_instructions'])
        else:
            # Default text instructions
            text_instructions.extend([
                "1. First, write the text for the page (2-3 child-friendly sentences) between \"TEXT START\" and \"TEXT END\"",
                "2. **Action:** The text MUST clearly describe what the main character(s) are *doing* in this scene",
                "3. **Progression:** The text should logically advance the story based on previous events",
                "4. After the text, you will generate a matching illustration"
            ])
        
        # Add final page instructions if needed
        final_instructions = []
        if page_number == book_config['page_count']:
            if 'final_page_instructions' in book_config:
                final_instructions = book_config['final_page_instructions']
            else:
                # Default final page instructions
                final_instructions = [
                    "FINAL PAGE INSTRUCTIONS:",
                    "- As this is the final page of the book, provide a satisfying conclusion to the story",
                    "- Do NOT end with a question or cliffhanger",
                    "- Wrap up the main storyline with a positive and clear ending"
                ]
        
        # Build the complete prompt dynamically
        prompt_parts = [
            f"Create a children's book page with text and illustration for page {page_number} of \"{book_config['title']}\".",
            ""
        ]
        
        # Add book details from config
        prompt_parts.extend([
            "Book Details:"
        ])
        for key, value in book_config.items():
            if isinstance(value, str) and key not in ['title', 'final_page_instructions', 'text_instructions']:
                prompt_parts.append(f"- {key.replace('_', ' ').title()}: {value}")
        
        # Add character information
        prompt_parts.append("\nCharacters:")
        for char_type, char_data in self.config['characters'].items():
            prompt_parts.append(f"- {char_data['name']} ({char_data['description']})")
        
        # Add scene requirements from scene_manager
        if scene_requirements:
            prompt_parts.extend([
                "\nSetting:",
                f"- Location: {scene_requirements.get('location', '')}",
                f"- Description: {scene_requirements.get('description', '')}",
                f"- Atmosphere: {scene_requirements.get('atmosphere', '')}"
            ])
            
            if 'elements' in scene_requirements:
                prompt_parts.append("- Elements:")
                for element in scene_requirements['elements']:
                    prompt_parts.append(f"  * {element}")
        
        # Add remaining sections
        prompt_parts.extend([
            "\nPrevious Context (for consistency):",
            consistency_context,
            "",
            *consistency_rules,
            "",
            *text_instructions
        ])
        
        if final_instructions:
            prompt_parts.extend(["", *final_instructions])
        
        # Add generation instructions
        if 'generation_instructions' in book_config:
            prompt_parts.extend(["", *book_config['generation_instructions']])
        else:
            # Default generation instructions
            prompt_parts.extend([
                "",
                "Please provide:",
                "1. Engaging text describing character actions and story progression (between TEXT START/END)",
                "2. A beautiful, colorful illustration matching the text and depicting the described actions",
                "",
                "Generate the image directly in your response."
            ])
        
        return "\n".join(prompt_parts)

    def generate_page_text(self, page_number: int):
        """Generate text for a single page of the book."""
        try:
            # Use predefined story text if available
            if 'story' in self.config and 'pages' in self.config['story']:
                story_pages = self.config['story']['pages']
                if 0 <= page_number - 1 < len(story_pages):
                    story_text = story_pages[page_number - 1]
                    
                    # Create page directory
                    page_dir = self.output_dir / f"page_{page_number:02d}"
                    page_dir.mkdir(exist_ok=True)
                    
                    # Save the story text
                    story_file = page_dir / "story_text.txt"
                    with open(story_file, 'w') as f:
                        f.write(story_text)
                    
                    # Store description for consistency in future pages
                    self.previous_descriptions[page_number] = story_text
                    self.checkpoint_manager.add_page_description(page_number, story_text)
                    
                    logger.info(f"Saved predefined text for page {page_number}")
                    return story_text
            
            # Fallback to generating text if no predefined text is available
            prompt = self.generate_prompt(page_number)
            
            # Generate the text content
            text_content, success = self.api_client.generate_story_text(prompt, self.conversation_history)
            
            if success:
                # Update conversation history
                self.conversation_history.append(prompt)
                if text_content:
                    self.conversation_history.append(text_content)
                    self.checkpoint_manager.add_to_conversation_history(text_content)
                
                # Limit conversation history
                if len(self.conversation_history) > 10:
                    self.conversation_history = self.conversation_history[-10:]
                
                # Create page directory
                page_dir = self.output_dir / f"page_{page_number:02d}"
                page_dir.mkdir(exist_ok=True)
                
                # Save the full text content
                text_file = page_dir / "text.txt"
                with open(text_file, 'w') as f:
                    f.write(text_content)
                
                # Extract the story text part
                story_text = self._extract_story_text(text_content, page_number)
                
                # Generate a backup story text if needed
                if not story_text or len(story_text.split()) < 5:
                    logger.warning(f"Story text extraction may be incomplete for page {page_number}. Using backup method.")
                    backup_story = self._generate_backup_story_text(page_number, text_content) 
                    if backup_story:
                        story_text = backup_story
                
                # Save the extracted story text
                story_file = page_dir / "story_text.txt"
                with open(story_file, 'w') as f:
                    f.write(story_text)
                
                # Store description for consistency
                self.previous_descriptions[page_number] = story_text
                self.checkpoint_manager.add_page_description(page_number, story_text)
                
                logger.info(f"Saved generated text for page {page_number}")
                return story_text
            else:
                raise Exception("No valid response from API")
            
        except Exception as e:
            logger.error(f"Error generating text for page {page_number}: {str(e)}")
            raise

    def _extract_story_text(self, full_text, page_number):
        """Extract just the story text from the full response."""
        # First look for TEXT START and TEXT END markers
        if "TEXT START" in full_text and "TEXT END" in full_text:
            start_idx = full_text.find("TEXT START") + len("TEXT START")
            end_idx = full_text.find("TEXT END")
            if start_idx < end_idx:
                extracted_text = full_text[start_idx:end_idx].strip()
                if extracted_text:
                    return extracted_text
        
        # If markers not found, try to find the actual story text by looking for patterns
        lines = full_text.split('\n')
        story_lines = []
        
        in_story_section = False
        for line in lines:
            # Skip empty lines
            if not line.strip():
                continue
                
            # Look for markers that might indicate story text
            line_lower = line.lower()
            
            # If we find a line with "text:" it's probably the start of the story text
            if "text:" in line_lower:
                in_story_section = True
                # Skip the line with "text:" itself
                continue
                
            # If we find a line with "illustration" it's probably the end of the story text
            if "illustration" in line_lower:
                in_story_section = False
                continue
                
            # If we're in the story section, add the line
            if in_story_section:
                story_lines.append(line)
        
        # If we couldn't find explicit markers, try with quotation marks
        if not story_lines:
            for line in lines:
                if line.count('"') >= 2 or (line.startswith('"') and line.endswith('"')):
                    story_lines.append(line)
                    
        # If still nothing, look for sections after page number headings
        if not story_lines:
            page_marker_found = False
            for i, line in enumerate(lines):
                if f"Page {page_number}" in line or f"**Page {page_number}**" in line:
                    page_marker_found = True
                    # Get the next few non-empty lines
                    candidate_lines = [l for l in lines[i+1:i+10] if l.strip()]
                    # Skip any headings and take the first 3 substantive lines
                    for cl in candidate_lines:
                        if not cl.startswith('#') and not cl.startswith('**') and not 'text:' in cl.lower():
                            story_lines.append(cl)
                        if len(story_lines) >= 3:
                            break
                    break
        
        # If still nothing, just return the first 3 non-empty lines
        if not story_lines:
            story_lines = [line for line in lines if line.strip() and not line.startswith('#') and not line.startswith('**')][:3]
            
        return "\n".join(story_lines)
    
    def _generate_backup_story_text(self, page_number: int, original_text: str) -> Optional[str]:
        """Generate a backup story text when extraction fails."""
        try:
            # Check if previous page text exists to use for context
            prev_context = ""
            if page_number > 1 and (page_number-1) in self.previous_descriptions:
                prev_context = f"Previous page: {self.previous_descriptions[page_number-1]}\n\n"
            
            # If the original text has some useful content, include it
            orig_context = ""
            if len(original_text) > 20:  # Arbitrary minimum length
                orig_context = f"Original partial text: {original_text[:200]}...\n\n"
            
            # Get book title from config
            book_title = self.config['book']['title']
            
            # Create a simple prompt to regenerate just the story text
            prompt = f"""Based on the provided context, please write 2-3 sentences ONLY for page {page_number} of the children's book "{book_title}".

{prev_context}{orig_context}
The text should be engaging for children, consistent with the story so far, and suitable for illustration.
ONLY provide the exact text for the page - no additional commentary or descriptions.
"""
            
            # Generate backup story
            backup_text, success = self.api_client.generate_backup_story(prompt)
            
            if success:
                logger.info(f"Generated backup story text for page {page_number}")
                return backup_text
            else:
                logger.error("Failed to generate backup story text")
                return None
            
        except Exception as e:
            logger.error(f"Error generating backup story: {str(e)}")
            return None

    def _calculate_temperature(self, page_number: int) -> float:
        """Calculate generation temperature based on position within story phase."""
        current_phase = self.scene_manager._get_story_phase(page_number)
        if current_phase and 'story_progression' in self.config:
            phase_mapping = self.config['story_progression']['phase_mapping'].get(current_phase, {})
            phase_start = phase_mapping.get('start_page', page_number)
            phase_end = phase_mapping.get('end_page', page_number)
            
            # Calculate position within phase (0 to 1)
            phase_length = phase_end - phase_start + 1
            phase_position = (page_number - phase_start) / max(1, phase_length - 1)
            
            # Get temperature settings from config
            temp_config = self.config.get('generation', {}).get('temperature', {})
            base_temp = temp_config.get('base', 0.2)
            phase_increment = temp_config.get('phase_increment', 0.3)
            max_temp = temp_config.get('max', 0.5)
            
            # Base temperature increases with position in phase
            temp = base_temp + (phase_position * phase_increment)
            logger.info(f"Using dynamic temperature {temp:.2f} for page {page_number} (position {phase_position:.2f} in phase '{current_phase}')")
            return min(temp, max_temp)
        
        # Get default base temperature from config
        return self.config.get('generation', {}).get('temperature', {}).get('base', 0.2)

    def generate_page_image(self, page_number: int, prompt_text: str, settings: dict, characters: dict) -> Optional[str]:
        """Generate an image for the given page and save it."""
        logger.info(f"Generating image for page {page_number}")
        
        try:
            # Build the complete prompt
            scene_requirements = self.scene_manager.get_scene_requirements(page_number, prompt_text)
            required_characters = self._get_required_characters(page_number, prompt_text)
            
            # Get character instructions and anti-duplication rules
            character_instructions = self._build_character_instructions(required_characters, scene_requirements)
            anti_duplication_rules = self._get_anti_duplication_rules(len(required_characters), required_characters)
            
            # Build the final prompt
            # NOTE: The core prompt text is built here. Reference image is added later by api_client if provided.
            final_prompt_text = self._build_final_image_prompt(
                page_number,
                self._create_scene_analysis(required_characters, scene_requirements, prompt_text, ""),
                self._get_generation_steps(),
                prompt_text,
                "",  # emotional guidance can be empty for now
                scene_requirements,
                character_instructions,
                anti_duplication_rules
            )

            # --- Determine and load reference image --- #
            reference_image_b64 = None
            reference_page_num = self._find_most_recent_image_page(page_number)
            if reference_page_num:
                ref_image_path = self.original_image_files.get(reference_page_num)
                if ref_image_path and os.path.exists(ref_image_path):
                    try:
                        with open(ref_image_path, 'rb') as f:
                            image_data = f.read()
                        reference_image_b64 = base64.b64encode(image_data).decode('utf-8')
                        logger.info(f"Loaded reference image from page {reference_page_num} for page {page_number}")
                    except Exception as e:
                        logger.warning(f"Failed to load reference image from {ref_image_path}: {e}")
                else:
                    logger.warning(f"Reference image path for page {reference_page_num} not found or file missing.")
            # --- End reference image loading --- #
            
            # Generate the image using the API client, passing the reference image data
            response = self.api_client.generate_image(
                prompt_text=final_prompt_text, 
                reference_image_b64=reference_image_b64,
                page_number=page_number,
                scene_requirements=scene_requirements
            )
            
            # Process and save the images
            image_count = self._process_and_save_images(response, page_number, prompt_text)
            
            # If images were generated, return the path to the first one
            if image_count > 0:
                image_files = list(self.output_dir.glob(f"page_{page_number:02d}/*.png"))
                if image_files:
                    image_files.sort()  # Sort to ensure consistent order
                    image_path = image_files[0]
                    logger.info(f"Successfully generated image for page {page_number}: {image_path}")
                    
                    # Return the relative path from the output directory
                    return str(image_path.relative_to(self.output_dir))
            
            logger.error(f"No images were generated for page {page_number}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to generate image for page {page_number}: {str(e)}")
            return None

    def _check_for_character_duplicates(self, prompt: str, required_characters: List[dict]) -> None:
        """Post-process check for potential character duplicates in the prompt."""
        import re
        
        # Get character names from required characters list
        required_char_names = [char['name'] for char in required_characters]
        
        # Get all character names from config
        all_char_names = [char_info['name'] for char_type, char_info in self.config.get('characters', {}).items()]
        
        # Find characters mentioned in the prompt that shouldn't be there
        non_required_chars = [name for name in all_char_names if name not in required_char_names]
        
        logger.info("DUPLICATE DETECTION POST-PROCESSING CHECK:")
        logger.info(f"Required characters: {', '.join(required_char_names)}")
        logger.info(f"Characters that should NOT appear: {', '.join(non_required_chars)}")
        
        # Check for required characters in the prompt
        for char_name in required_char_names:
            # Count character mentions in character instructions
            char_section_pattern = fr"Character: {re.escape(char_name)}.*?EXACTLY ONCE"
            char_sections = re.findall(char_section_pattern, prompt, re.IGNORECASE | re.DOTALL)
            
            if len(char_sections) > 1:
                logger.warning(f"POTENTIAL DUPLICATE ISSUE: Character '{char_name}' appears {len(char_sections)} times in character instructions!")
                
            # Check if character is emphasized at least once
            if len(char_sections) == 0:
                logger.warning(f"POTENTIAL ISSUE: Character '{char_name}' not properly defined with 'EXACTLY ONCE' instruction!")
        
        # Check for non-required characters that might have been included by mistake
        for char_name in non_required_chars:
            # Check if this non-required character is mentioned in the CHARACTER COUNT REQUIREMENTS section
            char_req_pattern = fr"{re.escape(char_name)}.*?MUST APPEAR EXACTLY ONCE"
            if re.search(char_req_pattern, prompt, re.IGNORECASE | re.DOTALL):
                logger.error(f"NON-REQUIRED CHARACTER INCLUDED: '{char_name}' shouldn't be in this page but is listed in character requirements!")
        
        # Check for total character count consistency
        total_char_pattern = r"TOTAL CHARACTERS: EXACTLY (\d+)"
        total_match = re.search(total_char_pattern, prompt)
        
        if total_match:
            specified_count = int(total_match.group(1))
            if specified_count != len(required_characters):
                logger.error(f"CHARACTER COUNT MISMATCH: Specified {specified_count} in prompt but actually have {len(required_characters)} characters!")
        else:
            logger.warning("No explicit total character count found in prompt!")
            
        logger.info("END DUPLICATE DETECTION CHECK")

    def _get_required_characters(self, page_number: int, content_text: str) -> List[dict]:
        """Get required characters for the current page based on story phase and text content."""
        required_characters = []
        
        # Get the story phase for this page
        story_phase = self.scene_manager._get_story_phase(page_number)
        
        # Process each character in config to determine if they should be in this page
        for char_type, char_info in self.config.get('characters', {}).items():
            # Get character introduction page
            intro_info = char_info.get('introduction', {})
            intro_page = intro_info.get('page', 1)
            
            # Skip character if they're introduced later
            if page_number < intro_page:
                continue
                
            # Check if character has actions for this phase OR emotion for this specific page
            has_action_for_phase = char_info.get('actions', {}).get(story_phase) is not None
            has_emotion_for_page = str(page_number) in char_info.get('emotional_states', {})
            
            if has_action_for_phase or has_emotion_for_page:
                # Get character action for this phase (if exists)
                char_action = char_info.get('actions', {}).get(story_phase) # Might be None if only emotion is present
                
                # Get character emotion for this page if available
                char_emotion = char_info.get('emotional_states', {}).get(str(page_number)) # Use .get() for safety
                
                # Log why the character is included (for debugging)
                include_reason = []
                if has_action_for_phase:
                    include_reason.append(f"action for phase '{story_phase}'")
                if has_emotion_for_page:
                    include_reason.append(f"emotion for page {page_number}")
                logger.debug(f"Including character '{char_info['name']}' for page {page_number} due to: {', '.join(include_reason)}")

                # Extract appearance details
                appearance = {}
                for attr in ['appearance', 'outfit', 'features']:
                    if attr in char_info:
                        appearance[attr] = char_info[attr]
                
                # Add character to required list with detailed information
                character = {
                    'name': char_info['name'],
                    'type': char_type,
                    'description': char_info.get('description', ''),
                    'action': char_action,
                    'emotion': char_emotion
                }
                
                # Add appearance details
                character.update(appearance)
                
                required_characters.append(character)
        
        # Log the required characters
        char_names = [char['name'] for char in required_characters]
        logger.info(f"Required characters for page {page_number}: {', '.join(char_names) if char_names else 'None'}")
        
        return required_characters
        
    def _create_scene_analysis(self, required_characters: List[dict], scene_requirements: dict,
                             content_text: str, story_actions: str) -> str:
        """Create scene analysis with character and environment details."""
        # Environment and scene details
        scene_desc = scene_requirements.get('description', 'A scene')
        atmosphere = scene_requirements.get('atmosphere', 'neutral')
        elements = scene_requirements.get('elements', [])
        
        # Format character list - each character appears exactly once
        character_list = ', '.join([f"{c['name']} (exactly 1)" for c in required_characters])
        
        # Format setting elements
        formatted_elements = []
        for elem in elements:
            formatted_elements.append(f"- {elem}")
        elements_text = "\n".join(formatted_elements) if formatted_elements else "No specific elements defined"
        
        # Build detailed scene analysis
        scene_analysis_parts = [
            f"1. Setting: {scene_desc}",
            f"2. Character list: {character_list}",
            f"3. Total character count: {len(required_characters)}",
            f"4. Atmosphere: {atmosphere}",
            f"5. Key elements:",
            elements_text,
            f"6. Story actions: {story_actions}"
        ]
        
        # Add emotional and visual guidance if available
        for visual_key in ['emotion', 'lighting', 'mood', 'visual_focus', 'color_palette']:
            if visual_key in scene_requirements:
                scene_analysis_parts.append(f"7. Visual {visual_key}: {scene_requirements[visual_key]}")
                
        # Add specific environment type info if available
        if 'environment_type' in scene_requirements:
            env_type = scene_requirements['environment_type']
            scene_analysis_parts.append(f"8. Environment type: {env_type}")
            
            # Add specific environment characteristics
            if 'environment_characteristics' in scene_requirements:
                characteristics = scene_requirements['environment_characteristics']
                scene_analysis_parts.append(f"9. Environment characteristics: {', '.join(characteristics)}")
                
        return "\n".join(scene_analysis_parts)
        
    def _build_character_instructions(self, required_characters: List[dict], scene_requirements: dict) -> str:
        """Build detailed instructions for each character, including appearance rules."""
        instructions = ["CHARACTER INSTRUCTIONS (FOLLOW CAREFULLY):"]
        char_names = set() # Track names to avoid duplicates if required_characters has them
        
        # Get appearance rules from scene_requirements if available
        all_char_rules = scene_requirements.get('character_appearance_rules', {})

        for i, char in enumerate(required_characters):
            char_name = char.get('name')
            if not char_name or char_name in char_names:
                continue # Skip if no name or already processed
            char_names.add(char_name)

            char_details = [
                f"{i+1}. Character: {char_name} | Description: {char.get('description', 'N/A')}"
            ]
            
            # --- Add Appearance Rules from Scene Requirements --- #
            char_rules = all_char_rules.get(char_name, {})
            if char_rules:
                char_details.append("   | APPEARANCE RULES (MUST FOLLOW):")
                for rule_type, rule_value in char_rules.items():
                     # Handle rules that might be strings or lists (like features)
                    if isinstance(rule_value, list):
                        char_details.append(f"     - {rule_type.capitalize()}: {', '.join(rule_value)}")
                    else:
                        char_details.append(f"     - {rule_type.capitalize()}: {rule_value}")
            else:
                 # Fallback to standard appearance attributes if rules not fetched
                 # Emphasize these as MANDATORY consistency rules
                 appearance_rules_added = False
                 for attr in ['appearance', 'outfit', 'features']:
                     if value := char.get(attr):
                         if not appearance_rules_added:
                              char_details.append("   | MANDATORY APPEARANCE RULES:")
                              appearance_rules_added = True
                         char_details.append(f"     - {attr.capitalize()} (ALWAYS): {value}") # Add emphasis
            # --- End Appearance Rules --- #

            # Add action and emotion
            if action := char.get('action'):
                char_details.append(f"   | Action: {action}")
            if emotion := char.get('emotion'):
                char_details.append(f"   | Emotion: {emotion}")
            else:
                 char_details.append(f"   | Emotion: None") # Explicitly state None if not specified
                 
            # char_details.append("   | IMPORTANT: This character must appear EXACTLY ONCE in the scene") # Moved to anti-duplication
            instructions.append("\n".join(char_details))
            
        return "\n\n".join(instructions)
        
    def _get_anti_duplication_rules(self, num_characters: int, required_characters: List[dict] = None) -> str:
        """Get anti-duplication rules from config and format them."""
        anti_dup_config = self.config.get('generation', {}).get('anti_duplication_rules', {})
        
        # Get raw rules from config
        rules = anti_dup_config.get('rules', [])
        consistency = anti_dup_config.get('consistency_rules', [])
        flexibility = anti_dup_config.get('flexibility_rules', [])
        verification = anti_dup_config.get('verification_rules', [])
        
        # Get character details ONLY for required characters
        characters_text = []
        if required_characters:
            for char in required_characters:
                char_name = char.get('name', '')
                char_desc = char.get('description', '')
                characters_text.append(f"- {char_name}: {char_desc} - MUST APPEAR EXACTLY ONCE")
        
        # Format the anti-duplication rules
        formatted_rules = ["ANTI-DUPLICATION INSTRUCTIONS (EXTREMELY IMPORTANT):"]
        
        # First section: Core rules
        formatted_rules.append("CORE RULES:")
        for rule in rules:
            formatted_rules.append(f"- {rule.format(num_characters=num_characters)}")
        
        # Add character-specific rules if available
        if characters_text:
            formatted_rules.append("\nCHARACTER COUNT REQUIREMENTS:")
            formatted_rules.extend(characters_text)
        
        # Add consistency rules
        if consistency:
            formatted_rules.append("\nCONSISTENCY REQUIREMENTS:")
            for rule in consistency:
                formatted_rules.append(f"- {rule}")
        
        # Add flexibility rules
        if flexibility:
            formatted_rules.append("\nALLOWED VARIATIONS:")
            for rule in flexibility:
                formatted_rules.append(f"- {rule}")
        
        # Add verification rules
        if verification:
            formatted_rules.append("\nFINAL VERIFICATION (BEFORE RENDERING):")
            for rule in verification:
                formatted_rules.append(f"- {rule.format(num_characters=num_characters)}")
        
        # Add extra emphasis on preventing duplication
        formatted_rules.append("\nWARNING: DUPLICATING CHARACTERS IS THE MOST COMMON ERROR.")
        formatted_rules.append("CAREFULLY CHECK YOUR SCENE AND REMOVE ANY DUPLICATE CHARACTERS BEFORE COMPLETING THE IMAGE.")
        
        return "\n".join(formatted_rules)
        
    def _build_final_image_prompt(self, page_number: int, scene_analysis: str,
                                generation_steps: str, content_text: str,
                                emotional_guidance: str, scene_requirements: dict,
                                character_instructions: str, anti_duplication_rules: str) -> str:
        """Build the final image prompt with all required components."""
        # Get art style configuration
        art_style_config = self.config.get('generation', {}).get('art_style', {})
        
        # Build the main prompt parts
        prompt_parts = [
            f"PROMPT TYPE: Children's book illustration for page {page_number}",
            f"TEXT: {content_text}",
            "",
            f"SCENE ANALYSIS:",
            scene_analysis,
            "",
            "CRITICAL REQUIREMENTS (FOLLOW THESE EXACTLY):",
            "- NO CHARACTER DUPLICATION: Each character must appear EXACTLY ONCE in the image",
            f"- CHARACTERS: {character_instructions}",
            anti_duplication_rules,
            "",
            "GENERATION STEPS:",
            generation_steps,
            "",
            emotional_guidance,
            "",
            "ART STYLE:",
            f"- Tone: {art_style_config.get('tone', 'Child-friendly')}",
            f"- Quality: {art_style_config.get('quality', 'High detail')}",
            f"- Policy: {art_style_config.get('text_policy', 'NO text in image')}",
            f"- Format: {art_style_config.get('format', 'SQUARE image')}".format(width=self.image_width, height=self.image_height),
        ]
        
        # Log the prompt for debugging
        logger.debug(f"Final prompt for page {page_number}: {' '.join(prompt_parts)}")
        
        return "\n".join(prompt_parts)
        
    def _get_generation_steps(self) -> str:
        """Get generation steps from config or use defaults."""
        # Get generation steps from config or use defaults
        generation_steps = self.config.get('generation', {}).get('steps', [
            "Create the scene background based on requirements.",
            "Leave the scene EMPTY of characters initially.",
            "Add EACH character ONE at a time, ensuring NO duplication occurs.",
            "Position characters to clearly depict the story actions."
        ])
        
        # Format steps with numbers
        formatted_steps = "SEQUENTIAL GENERATION PLAN:"
        for i, step in enumerate(generation_steps, 1):
            formatted_steps += f"\nStep {i}: {step}"
            
        return formatted_steps

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
            
            # Get required characters
            required_characters = self._get_required_characters(page_number, story_text)
            
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
            # Initialize book formatter
            formatter = BookFormatter(self.output_dir, self.config)
            
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
        original_existing_characters = self.scene_manager.existing_characters.copy()
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
                
                # Find best reference page using the scene manager method
                best_ref_page = self._find_most_recent_image_page(page_num)
                logger.info(f"Using reference page {best_ref_page} for consistency in regeneration")
                
                # If no reference page found and we need one, use fallback strategy
                if best_ref_page is None and page_num > 1:
                    # Try to find the closest preceding page
                    for prev_page in range(page_num-1, 0, -1):
                        # Check if this page exists and has an image
                        page_dir = self.output_dir / f"page_{prev_page:02d}"
                        original_image_path = page_dir / f"image_original_1.png"
                        if original_image_path.exists():
                            best_ref_page = prev_page
                            # Register this image path
                            self.original_image_files[prev_page] = str(original_image_path)
                            self.checkpoint_manager.add_original_image_file(prev_page, str(original_image_path))
                            self.pages_with_images.add(prev_page)
                            logger.info(f"Found fallback reference page {best_ref_page} for regeneration")
                            break
                
                # Temporarily add reference page back to pages_with_images if needed
                if best_ref_page and best_ref_page not in self.pages_with_images:
                    self.pages_with_images.add(best_ref_page)
                    # Restore the original image file for reference
                    if best_ref_page in original_image_files:
                        self.original_image_files[best_ref_page] = original_image_files[best_ref_page]
                        self.checkpoint_manager.add_original_image_file(best_ref_page, original_image_files[best_ref_page])
                
                # Set a flag to indicate we're regenerating (for stronger consistency guidance)
                self.is_regenerating = True
                
                # Generate the page
                self.generate_page(page_num)
                
                # Clear the regeneration flag
                self.is_regenerating = False
                
                # Add delay between pages to avoid rate limits
                if page_num != page_numbers[-1]:
                    logger.info(f"Waiting 8 seconds before next page...")
                    time.sleep(8)
                    
                # Clean up temporary reference if added
                if best_ref_page and best_ref_page not in original_pages_with_images:
                    self.pages_with_images.remove(best_ref_page)
            
            logger.info(f"Finished regenerating pages: {page_numbers}")
            
            # Save checkpoint
            self.checkpoint_manager.save()
            
        except Exception as e:
            logger.error(f"Error during regeneration: {str(e)}")
            # In case of error, restore original state
            self.completed_pages = original_completed_pages
            self.pages_with_images = original_pages_with_images
            self.previous_descriptions = original_previous_descriptions
            self.scene_manager.existing_characters = original_existing_characters
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

    def _process_and_save_images(self, image_data_list: Optional[List[str]], page_number: int, text: str) -> int:
        """Process and save images from a list of base64 encoded strings."""
        if not image_data_list:
            logger.warning(f"No image data list provided for page {page_number}.")
            return 0
            
        image_count = 0
        page_dir = self.output_dir / f"page_{page_number:02d}"
        page_dir.mkdir(exist_ok=True)
        
        # Get image settings from config
        image_settings = self.config.get('image_settings', {})
        target_width = image_settings.get('width', 1024)
        target_height = image_settings.get('height', 1024)
        image_format = image_settings.get('format', 'RGB')
        resize_method = getattr(Image.Resampling, image_settings.get('resize_method', 'LANCZOS').upper())
        maintain_aspect = image_settings.get('maintain_aspect_ratio', True)
        smart_crop = image_settings.get('smart_crop', False)
        bg_color = image_settings.get('background_color', 'white')
        
        for idx, image_data_base64 in enumerate(image_data_list, 1):
            if not image_data_base64 or len(image_data_base64) < 100: # Basic check
                logger.warning(f"Skipping invalid or empty image data string for image {idx} on page {page_number}.")
                continue

            try:
                # Decode base64 image
                image_data = base64.b64decode(image_data_base64)
                
                # Open and process image
                img = Image.open(BytesIO(image_data))
                logger.debug(f"Loaded image {idx} for page {page_number}: format={img.format}, mode={img.mode}, size={img.size}")
                
                # Convert to RGB if needed
                if img.mode != image_format:
                    img = img.convert(image_format)
                
                # Calculate dimensions while maintaining aspect ratio if required
                if maintain_aspect and not smart_crop:
                    # Create a blank background image
                    background = Image.new(image_format, (target_width, target_height), bg_color)
                    
                    # Calculate scaling factor to fit within target dimensions
                    width_ratio = target_width / img.width if img.width > 0 else 1
                    height_ratio = target_height / img.height if img.height > 0 else 1
                    scale_factor = min(width_ratio, height_ratio)
                    
                    # Calculate new dimensions
                    new_width = int(img.width * scale_factor)
                    new_height = int(img.height * scale_factor)
                    
                    # Resize image
                    img_resized = img.resize((new_width, new_height), resize_method)
                    
                    # Calculate position to center the image
                    x = (target_width - new_width) // 2
                    y = (target_height - new_height) // 2
                    
                    # Paste resized image onto background
                    background.paste(img_resized, (x, y))
                    final_img = background
                elif maintain_aspect and smart_crop:
                    # Smart crop: resize to fill the canvas completely and crop excess
                    width_ratio = target_width / img.width if img.width > 0 else 1
                    height_ratio = target_height / img.height if img.height > 0 else 1
                    
                    # Use the larger ratio to ensure the image fills the target dimensions
                    scale_factor = max(width_ratio, height_ratio)
                    
                    # Calculate new dimensions (larger than target dimensions)
                    new_width = int(img.width * scale_factor)
                    new_height = int(img.height * scale_factor)
                    
                    # Resize image (to larger than target dimensions)
                    img_resized = img.resize((new_width, new_height), resize_method)
                    
                    # Calculate crop box to center the image
                    left = (new_width - target_width) // 2
                    top = (new_height - target_height) // 2
                    right = left + target_width
                    bottom = top + target_height
                    
                    # Crop the image to the target dimensions
                    final_img = img_resized.crop((left, top, right, bottom))
                else:
                    # Direct resize to target dimensions
                    final_img = img.resize((target_width, target_height), resize_method)
                
                # Save original image without text
                original_image_path = page_dir / f"image_original_{idx}.png"
                final_img.save(original_image_path, "PNG")
                
                # Save copies for text overlay
                image_with_text_path = page_dir / f"image_{idx}.png"
                final_img.save(image_with_text_path, "PNG")
                
                # Save a copy in the processed directory
                processed_dir = self.processed_dir
                processed_dir.mkdir(exist_ok=True)
                processed_image_path = processed_dir / f"page_{page_number:02d}.png"
                final_img.save(processed_image_path, "PNG")
                
                # Store original image file path (only store the first generated image for reference)
                if image_count == 0: # Only store the path for the first image generated for this page
                    self.original_image_files[page_number] = str(original_image_path)
                    self.checkpoint_manager.add_original_image_file(page_number, str(original_image_path))
                
                # Apply text overlay to the copies (not the original)
                self.text_overlay_manager.apply_text_overlay(image_with_text_path, text, page_number)
                self.text_overlay_manager.apply_text_overlay(processed_image_path, text, page_number, is_final=True)
                
                image_count += 1
                logger.info(f"Saved image {idx} for page {page_number}")
                
            except Exception as e:
                logger.error(f"Error processing image {idx} for page {page_number}: {str(e)}")
                continue
        
        if image_count == 0:
            logger.error(f"Failed to process any valid image data for page {page_number}.")
                
        return image_count

    def _add_reference_image(self, prompt_parts: list, reference_page: int, current_page: int, content_text: str):
        """Add reference image to the prompt parts for consistency."""
        try:
            # Prevent self-reference - a page should never use itself as a reference
            if reference_page == current_page:
                logger.warning(f"Prevented page {current_page} from using itself as a reference")
                return
                
            # Get the reference image path
            ref_image_path = self.original_image_files.get(reference_page)
            if not ref_image_path or not os.path.exists(ref_image_path):
                logger.warning(f"Reference image not found for page {reference_page}")
                return
                
            # Get scene requirements for reference handling
            scene_requirements = self.scene_manager.get_scene_requirements(current_page, content_text)
            reference_handling = scene_requirements.get('reference_handling', {})
            
            # Read the image file
            with open(ref_image_path, 'rb') as f:
                image_data = f.read()
                
            # Convert to base64
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            # Add reference image guidance
            guidance = ["REFERENCE IMAGE GUIDANCE:"]
            if 'maintain' in reference_handling:
                guidance.append("Maintain these elements:")
                guidance.extend(f"- {item}" for item in reference_handling['maintain'])
            
            if 'adapt' in reference_handling:
                guidance.append("\nAdapt these elements:")
                guidance.extend(f"- {item}" for item in reference_handling['adapt'])
            
            if 'ignore' in reference_handling:
                guidance.append("\nIgnore these elements:")
                guidance.extend(f"- {item}" for item in reference_handling['ignore'])
                
            # Add the guidance text
            prompt_parts.append({"text": "\n".join(guidance)})
            
            # Add specific instruction on how to use the reference image vs. text rules
            prompt_parts.append({"text": "\n**CRITICAL CONSISTENCY NOTE:** Use the text-based \"CHARACTER INSTRUCTIONS\" (especially rules marked with \"ALWAYS\") as the PRIMARY source for character appearance details (features, clothing, colors). Use the reference image below MAINLY for overall style, color palette, character placement, and general visual guidance. If the reference image contradicts a specific \"ALWAYS\" rule in the text, FOLLOW THE TEXT RULE."})

            # Add the reference image
            prompt_parts.append({
                "inlineData": {
                    "mimeType": "image/png",
                    "data": image_base64
                }
            })
            
            logger.info(f"Added reference image from page {reference_page} for consistency")
            
        except Exception as e:
            logger.warning(f"Error adding reference image: {str(e)}")
            # Continue without reference image if there's an error

    def generate_cover(self):
        """Generate the book cover image and apply text overlay."""
        logger.info("Attempting to generate book cover...")
        
        # Check if cover generation is enabled in config
        cover_config = self.config.get('cover', {})
        if not cover_config.get('generate_cover', False):
            logger.info("Cover generation is disabled in config. Skipping.")
            return

        book_config = self.config.get('book', {})
        
        try:
            # Determine reference page and image path
            ref_page_num = cover_config.get('reference_page_for_style', 1)
            ref_image_path = self.output_dir / f"page_{ref_page_num:02d}" / "image_original_1.png"
            reference_image_b64 = None
            
            if ref_image_path.exists():
                logger.info(f"Using image from page {ref_page_num} as style reference for the cover.")
                with open(ref_image_path, "rb") as image_file:
                    reference_image_b64 = base64.b64encode(image_file.read()).decode('utf-8')
            else:
                logger.warning(f"Reference image not found at {ref_image_path}. Generating cover without style reference.")

            # Format the cover prompt
            prompt_template = cover_config.get('cover_prompt_template', "A vibrant book cover for '{title}'")
            title = cover_config.get('cover_title') or book_config.get('title', 'My Book')
            author = cover_config.get('cover_author', 'Generated by AI')
            theme = book_config.get('theme', "a children's story")
            art_style = book_config.get('art_style', 'illustration')
            characters_list = [c.get('name', f'Character {i+1}') for i, c in enumerate(self.config.get('characters', {}).values())]
            characters = ", ".join(characters_list) if characters_list else "the main character"

            # --- Add Detailed Character Descriptions for Cover --- #
            cover_char_details_list = ["CHARACTER DETAILS (MUST FOLLOW):"]
            for char_name in characters_list:
                char_config = next((cd for ct, cd in self.config.get('characters', {}).items() if cd.get('name') == char_name), None)
                if char_config:
                    details = [f"- {char_name}:"]
                    if appearance := char_config.get('appearance'):
                        details.append(f"  - Appearance: {appearance}")
                    if outfit := char_config.get('outfit'):
                        details.append(f"  - Outfit: {outfit}")
                    if features := char_config.get('features'):
                        details.append(f"  - Features: {features}")
                    cover_char_details_list.append("\n".join(details))
            cover_char_details = "\n".join(cover_char_details_list)
            # --- End Character Descriptions --- #

            final_prompt = prompt_template.format(
                title=title, 
                characters=characters, # Keep names here for template compatibility
                theme=theme, 
                art_style=art_style,
                author=author
            )
            
            # Add character details and consistency instruction to the prompt parts sent to API
            prompt_parts_for_api = [
                {"text": final_prompt},
                {"text": "\n" + cover_char_details},
                {"text": "\n**CONSISTENCY:** Ensure the characters depicted match the details above AND the overall style of the reference image."}
            ]

            logger.info(f"Cover prompt (base): {final_prompt}")
            logger.info(f"Cover character details added: {cover_char_details}")

            # Call API client to generate image
            # Modify API call to potentially handle structured prompt parts if needed
            # Assuming api_client.generate_image can handle a list of text parts or needs adjustment
            # For now, let's concatenate the prompt parts
            full_prompt_text = "\n".join(part["text"] for part in prompt_parts_for_api)
            
            image_data_list = self.api_client.generate_image(
                prompt_text=full_prompt_text, # Send the combined prompt
                page_number=0, # Using 0 for cover
                reference_image_b64=reference_image_b64
            )

            if not image_data_list:
                logger.error("API did not return image data for the cover.")
                return

            # Assuming the API returns a list of base64 encoded images, take the first one
            image_data_base64 = image_data_list[0]

            # Save the original cover image
            cover_original_path = self.output_dir / "cover_original.png"
            try:
                img_data = base64.b64decode(image_data_base64)
                img = Image.open(BytesIO(img_data))
                
                # Ensure image matches target dimensions (optional, but good practice)
                if img.size != (self.image_width, self.image_height):
                   logger.warning(f"Generated cover size {img.size} differs from target ({self.image_width}, {self.image_height}). Resizing.")
                   img = img.resize((self.image_width, self.image_height), Image.Resampling.LANCZOS)
                   
                img.save(cover_original_path)
                logger.info(f"Saved original cover image to {cover_original_path}")
            except Exception as e:
                logger.error(f"Failed to decode or save original cover image: {e}")
                return

            # Apply text overlay
            cover_final_path = self.output_dir / "cover_final.png"
            # Copy original to final path first, overlay manager might modify in-place
            import shutil
            shutil.copy2(cover_original_path, cover_final_path)

            cover_text = f"{title}\n{author}"
            position = cover_config.get('cover_text_position', 'middle')
            
            # NOTE: Assuming text_overlay_manager.apply_text_overlay can handle page_number=0 
            #       and potentially uses different logic/fonts for covers via an is_cover flag or similar.
            #       This might require modification in text_overlay_manager.py
            self.text_overlay_manager.apply_text_overlay(
                image_path=cover_final_path, 
                text=cover_text, 
                page_number=0, # Using 0 to denote cover
                position=position,
                is_cover=True # Added flag to signal this is a cover
            )
            logger.info(f"Applied text overlay and saved final cover to {cover_final_path}")

        except Exception as e:
            logger.error(f"Failed to generate cover: {e}")
            # Decide if we should raise the error or just log it and continue without a cover
            # For now, logging seems safer to allow book generation to complete.

def handle_rate_limit_retry(max_retries=3, initial_wait=20):
    """Try to resume book generation with exponential backoff for rate limits."""
    retry_count = 0
    wait_time = initial_wait
    
    while retry_count < max_retries:
        try:
            generator = BookGenerator("config.yaml")
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
    
    parser = argparse.ArgumentParser(description='Generate a children\'s book with text and illustrations.')
    parser.add_argument('--retry', action='store_true', help='Auto-retry on rate limits')
    parser.add_argument('--regenerate', type=str, help='Regenerate specific pages (comma-separated)')
    parser.add_argument('--apply-text', type=str, nargs='*', help='Apply text overlay to existing images. Optional arguments: [position] [page_num|cover]. Position: top, middle, bottom (default: bottom). Target: specific page number, "cover", or blank for all pages.')
    args = parser.parse_args()
    
    generator = BookGenerator(config_path)
    
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