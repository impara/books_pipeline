from pathlib import Path
from loguru import logger
import yaml
from typing import Dict, Optional, List
from .transition_manager import TransitionManager

class SceneManager:
    def __init__(self, 
                 settings: dict, 
                 characters: dict,
                 story_progression: dict,
                 page_emotions: dict,
                 environment_types: dict,
                 scene_management: dict,
                 story_beats: dict,
                 transition_manager: TransitionManager):
        """Initialize the scene manager with specific configuration sections and injected TransitionManager."""
        # Store specific config sections
        self.settings = settings
        self.characters = characters
        self.story_progression = story_progression
        self.page_emotions = page_emotions
        self.environment_types = environment_types
        self.scene_management = scene_management
        self.story_beats = story_beats
        
        # Store injected manager
        self.transition_manager = transition_manager
        
        # Derive values from specific settings
        self.scene_progression = self.settings.get('scene_progression', {})
        # self.page_emotions is already passed directly
        # self.environment_types is already passed directly
        
        # Initialize caches
        self.scene_cache = {}
        self.character_cache = {}
        self.existing_characters = set()  # Initialize the set to track existing characters
        
    def detect_new_characters(self, page_number: int, text: str) -> list:
        """Detect new characters mentioned in the text."""
        new_characters = []
        
        # Only check for character introductions on their specific introduction pages
        for char_type, char_info in self.characters.items():
            intro_info = char_info.get('introduction', {})
            char_name = char_info['name']
            intro_page = intro_info.get('page')
            
            # Skip if this isn't the character's introduction page
            if page_number != intro_page:
                continue
            
            # Check for special character introductions from config
            special_intros = self.scene_management.get('special_character_introductions', {})
            if (char_type in special_intros and 
                page_number == special_intros[char_type].get('page') and 
                char_name not in self.existing_characters):
                new_characters.append(char_name)
                self.existing_characters.add(char_name)
                logger.info(f"Detected {special_intros[char_type].get('character_type')} character on page {page_number}")
                continue
                
            # Check if character hasn't been introduced yet and trigger word is present
            if (char_name not in self.existing_characters and 
                intro_info.get('trigger', '').lower() in text.lower()):
                new_characters.append(char_name)
                self.existing_characters.add(char_name)
                logger.info(f"Detected new character: {char_name} on page {page_number}")
        
        return new_characters

    def set_previous_descriptions(self, descriptions):
        """Set previous page descriptions for consistency."""
        self.previous_descriptions = descriptions

    def get_character_appearance_rules(self, character_name: str) -> dict:
        """Get character appearance rules from config."""
        for char_type, char_data in self.characters.items():
            if char_data['name'] == character_name:
                appearance_rules = {}
                # Get appearance and features from character config
                if 'appearance' in char_data:
                    appearance_rules['appearance'] = char_data['appearance']
                if 'outfit' in char_data:
                    appearance_rules['outfit'] = char_data['outfit']
                if 'features' in char_data:
                    appearance_rules['features'] = char_data['features']
                return appearance_rules
        return {}

    def get_character_action(self, character_name: str, page_number: int, text: str = None) -> str:
        """Get character action based on story progression."""
        story_phase = self._get_story_phase(page_number)
        
        for char_type, char_info in self.characters.items():
            if char_info['name'] == character_name:
                if story_phase in char_info.get('actions', {}):
                    return char_info['actions'][story_phase]
        return ""

    def get_scene_requirements(self, page_number: int, content_text: str = None) -> dict:
        """Get scene requirements for a specific page."""
        # Get base scene info
        scene_info = self._get_base_scene_info(page_number)
        if not scene_info:
            return {}
            
        # Add character information using the new method which returns full details
        required_characters_details = self.get_required_characters(page_number, content_text)
        if required_characters_details:
            scene_info['characters'] = required_characters_details # Store the full details
            
            # Extract names just for logging if needed (optional)
            # character_names = [char['name'] for char in required_characters_details]
            # logger.debug(f"Characters for page {page_number}: {', '.join(character_names)}")

            # REMOVE redundant fetching of appearance rules, as they are now 
            # included in required_characters_details returned by get_required_characters.
            # char_rules = {}
            # for char_name in characters: # This 'characters' was previously just names
            #     rules = self.get_character_appearance_rules(char_name)
            #     if rules: # Only add if rules are found
            #         char_rules[char_name] = rules
            # if char_rules: # Only add the key if there are any rules
            #     scene_info['character_appearance_rules'] = char_rules
            
        # Get transition requirements if not the first page
        if page_number > 1:
            transition_reqs = self.transition_manager.analyze_transition(
                page_number,
                page_number - 1
            )
            if transition_reqs:
                scene_info['transition_requirements'] = transition_reqs
                
        # Get reference handling if using a reference
        if reference_page := self._get_reference_page(page_number):
            reference_handling = self.transition_manager.get_reference_handling(
                page_number,
                reference_page
            )
            if reference_handling:
                scene_info['reference_handling'] = reference_handling
                
        # Add emotional and visual cues
        page_emotion = self.get_page_emotions(page_number)
        if page_emotion:
            scene_info.update({
                'emotion': page_emotion.get('emotion', ''),
                'lighting': page_emotion.get('lighting', ''),
                'mood': page_emotion.get('mood', ''),
                'visual_focus': page_emotion.get('visual_focus', ''),
                'color_palette': page_emotion.get('color_palette', '')
            })
            
        # Add environment information
        env_type = self._get_environment_type(scene_info)
        if env_type and env_type in self.environment_types:
            env_data = self.environment_types[env_type]
            scene_info.update({
                'environment_type': env_type,
                'environment_characteristics': env_data.get('characteristics', []),
                'lighting_defaults': env_data.get('lighting_defaults', [])
            })
                
        logger.info(f"Generated scene requirements for page {page_number}")
        return scene_info
        
    def _get_base_scene_info(self, page_number: int) -> dict:
        """Get base scene information for a specific page."""
        # Check cache first
        if page_number in self.scene_cache:
            return self.scene_cache[page_number].copy()
            
        # Find the phase for this page
        for phase, info in self.story_progression.get('phase_mapping', {}).items():
            if info.get('start_page') <= page_number <= info.get('end_page'):
                scene_info = self.scene_progression.get(phase, {}).copy()
                self.scene_cache[page_number] = scene_info
                return scene_info
                
        return {}
        
    def get_required_characters(self, page_number: int, content_text: str) -> List[dict]:
        """Get required characters for the current page with full details."""
        # (Note: content_text is currently unused in this logic but kept for potential future use)
        required_characters = []
        story_phase = self._get_story_phase(page_number) # Use internal method
        
        for char_type, char_info in self.characters.items():
            intro_page = char_info.get('introduction', {}).get('page', 1)
            if page_number < intro_page: continue
                
            has_action = char_info.get('actions', {}).get(story_phase) is not None
            has_emotion = str(page_number) in char_info.get('emotional_states', {})
            
            if has_action or has_emotion:
                char_action = char_info.get('actions', {}).get(story_phase)
                char_emotion = char_info.get('emotional_states', {}).get(str(page_number))
                
                include_reason = []
                if has_action: include_reason.append(f"action for '{story_phase}'")
                if has_emotion: include_reason.append(f"emotion for page {page_number}")
                logger.debug(f"Including '{char_info['name']}' for page {page_number}: {', '.join(include_reason)}")

                appearance = {attr: char_info[attr] for attr in ['appearance', 'outfit', 'features'] if attr in char_info}
                
                character = {
                    'name': char_info['name'], 'type': char_type, 
                    'description': char_info.get('description', ''),
                    'action': char_action, 'emotion': char_emotion, **appearance
                }
                required_characters.append(character)
        
        char_names = [char['name'] for char in required_characters]
        logger.info(f"Required characters for page {page_number}: {', '.join(char_names) if char_names else 'None'}")
        return required_characters
        
    def _get_reference_page(self, page_number: int) -> Optional[int]:
        """Determine if a reference page should be used for this page."""
        # Check for scene similarity with previous pages
        current_scene = self._get_base_scene_info(page_number)
        if not current_scene:
            return None
            
        # Look at previous pages for similar scenes
        for prev_page in range(page_number - 1, 0, -1):
            prev_scene = self._get_base_scene_info(prev_page)
            if not prev_scene:
                continue
                
            # Check if scenes share significant elements
            current_elements = set(current_scene.get('elements', []))
            prev_elements = set(prev_scene.get('elements', []))
            
            # Get similarity threshold from config
            similarity_threshold = self.scene_management.get('reference_page', {}).get('similarity_threshold', 0.7)
            
            # If scenes share more than threshold elements, use as reference
            if len(current_elements & prev_elements) / len(current_elements | prev_elements) > similarity_threshold:
                return prev_page
                
        return None
        
    def get_page_emotions(self, page_number: int) -> dict:
        """Get emotional and visual cues for a page by looking up the page's phase 
           and retrieving data from settings.scene_progression."""
        story_phase = self._get_story_phase(page_number)
        if not story_phase:
            logger.warning(f"Could not determine story phase for page {page_number}. Returning empty emotions.")
            return {}
            
        phase_details = self.scene_progression.get(story_phase, {})
        
        # Extract the relevant keys
        emotion_data = {
            'emotion': phase_details.get('emotion', ''),
            'lighting': phase_details.get('lighting', ''),
            'mood': phase_details.get('mood', ''),
            'visual_focus': phase_details.get('visual_focus', ''),
            'color_palette': phase_details.get('color_palette', ''),
            'transition_from_previous': phase_details.get('transition_from_previous', '') # Keep this if used
        }
        
        # Filter out empty values if desired, but usually better to return the structure
        # emotion_data = {k: v for k, v in emotion_data.items() if v}
        
        return emotion_data
        
    def _get_environment_type(self, scene_info: dict) -> str:
        """Get environment type for a scene using TransitionManager's logic."""
        return self.transition_manager._get_environment_type(scene_info)

    def extract_story_specific_actions(self, page_number: int, text: str = None) -> str:
        """Extract story-specific actions enriched with emotional states from config."""
        # Get the basic action from story beats
        story_phase = self._get_story_phase(page_number)
        action = self.story_beats.get(story_phase, "")
        
        # Get character emotions for the current page
        character_emotions = self.get_character_emotions(page_number)
        
        # If there are emotional states, incorporate them
        if character_emotions:
            action += " while feeling " + " and ".join(character_emotions.values())
        
        return action

    def get_character_emotions(self, page_number: int) -> dict:
        """Get emotions for all characters present on a specific page."""
        emotions = {}
        for char_type, char_info in self.characters.items():
            char_name = char_info['name']
            if str(page_number) in char_info.get('emotional_states', {}):
                emotions[char_name] = char_info['emotional_states'][str(page_number)]
        return emotions

    def get_visual_transition(self, from_page: int, to_page: int) -> str:
        """Get visual transition between two pages."""
        transition_key = f"{from_page}_to_{to_page}"
        
        # Check if visual transitions are defined in the config
        if 'visual_transitions' in self.config:
            return self.config['visual_transitions'].get(transition_key, "")
        elif 'story' in self.config and 'visual_transitions' in self.config['story']:
            return self.config['story']['visual_transitions'].get(transition_key, "")
        return ""

    def get_emotional_guidance(self, page_number: int, reference_page: int = None) -> str:
        """Get formatted emotional guidance text for a page, optionally with reference page comparison."""
        current_emotions = self.get_page_emotions(page_number)
        character_emotions = self.get_character_emotions(page_number)
        
        # Format character emotions
        char_emotions_text = []
        for char_name, emotion in character_emotions.items():
            char_emotions_text.append(f"- {char_name}: {emotion}")
        
        # If no reference page, just return current page emotions
        if not reference_page:
            guidance = f"""EMOTIONAL AND VISUAL GUIDANCE:
- Emotion: {current_emotions.get('emotion', 'Not specified')}
- Lighting: {current_emotions.get('lighting', 'Not specified')}
- Mood: {current_emotions.get('mood', 'Not specified')}
- Visual Focus: {current_emotions.get('visual_focus', 'Not specified')}
- Color Palette: {current_emotions.get('color_palette', 'Not specified')}

CHARACTER EMOTIONAL STATES:
{chr(10).join(char_emotions_text) if char_emotions_text else "- No specific emotional states defined"}"""
            return guidance
        
        # If reference page provided, include transition information
        reference_emotions = self.get_page_emotions(reference_page)
        # visual_transition = self.get_visual_transition(reference_page, page_number) # Removed as visual_transitions config is removed
        
        # Get story phases for context
        current_phase = self._get_story_phase(page_number)
        reference_phase = self._get_story_phase(reference_page)
        
        # Determine relationship between pages
        relationship = "continuing directly from"
        if page_number - reference_page > 1:
            relationship = "progressing from"
        if current_phase != reference_phase:
            relationship = f"transitioning from {reference_phase} phase to {current_phase} phase after"
        
        # Build reference-based guidance
        guidance = f"""EMOTIONAL TRANSITION:
- Previous page emotion: {reference_emotions.get('emotion', 'Not specified')}
- Current page emotion: {current_emotions.get('emotion', 'Not specified')}
- Emotional progression: {current_emotions.get('transition_from_previous', 'N/A')}
- Relationship: {relationship} page {reference_page}

LIGHTING AND ATMOSPHERE:
- Previous lighting: {reference_emotions.get('lighting', 'Not specified')}
- Current lighting: {current_emotions.get('lighting', 'Not specified')}
- Visual mood: {current_emotions.get('mood', 'Not specified')}

COLOR GUIDANCE:
- Previous palette: {reference_emotions.get('color_palette', 'Not specified')}
- Current palette: {current_emotions.get('color_palette', 'Not specified')}

VISUAL FOCUS:
- Key focus elements: {current_emotions.get('visual_focus', 'Not specified')}

CHARACTER EMOTIONAL STATES:
{chr(10).join(char_emotions_text) if char_emotions_text else "- No specific emotional states defined"}

# REMOVED SPECIFIC VISUAL TRANSITION section
# SPECIFIC VISUAL TRANSITION:
# {visual_transition}"""
        
        return guidance

    def _get_story_phase(self, page_number: int) -> str:
        """Get the story phase for a given page number."""
        for phase, info in self.story_progression.get('phase_mapping', {}).items():
            if info.get('start_page') <= page_number <= info.get('end_page'):
                return phase
        
        # Check fallback phases
        for phase, info in self.story_progression.get('fallback_phases', {}).items():
            if page_number <= info.get('end_page'):
                return phase
        
        # Return default phase if nothing else matches
        return self.story_progression.get('default_phase', 'conclusion')

    def find_reference_page(self, current_page_number: int, available_original_files: Dict[int, str]) -> Optional[int]:
        """Find the most suitable reference image page for consistency.
        
        Checks for character introduction pages first, then falls back to the most recent page.
        Requires access to the currently available original image files.
        
        Args:
            current_page_number: The page number for which a reference is needed.
            available_original_files: A dictionary mapping page numbers to their saved original image file paths.
                                       This comes from BookGenerator's state.
                                       
        Returns:
            The page number of the best reference image, or None if none found.
        """
        # Filter available files to only include pages before the current one
        valid_reference_pages = {p: path for p, path in available_original_files.items() if p < current_page_number}
        
        if not valid_reference_pages:
            logger.info(f"No preceding pages with images found to use as reference for page {current_page_number}")
            return None

        # Sort available pages by number, descending (most recent first)
        sorted_available_pages = sorted(valid_reference_pages.keys(), reverse=True)
        
        try:
            # Get scene requirements to determine characters present on the current page
            # Pass None for content_text as we only need character info here
            scene_reqs = self.get_scene_requirements(current_page_number, None) 
            
            # Extract just the names of characters required for the current page
            # Handle the case where scene_reqs['characters'] might be None or empty
            current_char_details = scene_reqs.get('characters', [])
            current_chars_names = [char['name'] for char in current_char_details] if current_char_details else []
            
            intro_pages_with_images = []
            if current_chars_names:
                logger.debug(f"Checking intro pages for current characters: {current_chars_names}")
                for char_name in current_chars_names:
                    # Find the character type (key in self.characters dict) based on name
                    char_type = next((ct for ct, cd in self.characters.items() if cd.get('name') == char_name), None)
                    if char_type:
                        intro_page = self.characters[char_type].get('introduction', {}).get('page')
                        # Check if the intro page exists, is not the current page, and has an image file saved
                        if intro_page and intro_page != current_page_number and intro_page in valid_reference_pages:
                            intro_pages_with_images.append(intro_page)
                            logger.debug(f"Found potential reference: Intro page {intro_page} for character '{char_name}'")

            # If any relevant character intro pages with images were found, use the earliest one
            if intro_pages_with_images:
                earliest_intro_page = min(intro_pages_with_images)
                logger.info(f"Using earliest character introduction page {earliest_intro_page} as reference for page {current_page_number}")
                return earliest_intro_page
                
        except Exception as e:
             # Log the error but allow fallback to most recent page
             logger.warning(f"Could not determine character introduction page for reference due to error: {e}. Falling back to most recent.")

        # Fallback: If no intro pages found or error occurred, use the most recent available page
        if sorted_available_pages:
            most_recent_page = sorted_available_pages[0]
            logger.info(f"Using most recent page {most_recent_page} as reference for page {current_page_number} (fallback)")
            return most_recent_page
            
        # Should theoretically not be reached if valid_reference_pages was not empty initially,
        # but added for completeness.
        logger.info(f"Could not find any suitable reference page for page {current_page_number}")
        return None