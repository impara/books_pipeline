from loguru import logger
import yaml
from typing import Dict, Optional
from transition_manager import TransitionManager

class SceneManager:
    def __init__(self, config: dict):
        """Initialize the scene manager with configuration."""
        self.config = config
        self.settings = config.get('settings', {})
        self.scene_progression = self.settings.get('scene_progression', {})
        self.page_emotions = config.get('page_emotions', {})
        self.environment_types = config.get('environment_types', {})
        
        # Initialize managers
        self.transition_manager = TransitionManager(config)
        
        # Initialize caches
        self.scene_cache = {}
        self.character_cache = {}
        self.existing_characters = set()  # Initialize the set to track existing characters
        
    def detect_new_characters(self, page_number: int, text: str) -> list:
        """Detect new characters mentioned in the text."""
        new_characters = []
        
        # Only check for character introductions on their specific introduction pages
        for char_type, char_info in self.config['characters'].items():
            intro_info = char_info.get('introduction', {})
            char_name = char_info['name']
            intro_page = intro_info.get('page')
            
            # Skip if this isn't the character's introduction page
            if page_number != intro_page:
                continue
            
            # Check for special character introductions from config
            special_intros = self.config.get('scene_management', {}).get('special_character_introductions', {})
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
        for char_type, char_data in self.config['characters'].items():
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
        
        for char_type, char_info in self.config['characters'].items():
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
            
        # Add character information
        characters = self._get_required_characters(page_number, content_text)
        if characters:
            scene_info['characters'] = characters
            # Fetch and add appearance rules for each character
            char_rules = {}
            for char_name in characters:
                rules = self.get_character_appearance_rules(char_name)
                if rules: # Only add if rules are found
                    char_rules[char_name] = rules
            if char_rules: # Only add the key if there are any rules
                scene_info['character_appearance_rules'] = char_rules
            
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
        for phase, info in self.config.get('story_progression', {}).get('phase_mapping', {}).items():
            if info.get('start_page') <= page_number <= info.get('end_page'):
                scene_info = self.scene_progression.get(phase, {}).copy()
                self.scene_cache[page_number] = scene_info
                return scene_info
                
        return {}
        
    def _get_required_characters(self, page_number: int, content_text: str = None) -> list:
        """Determine required characters for a page based on content and configuration."""
        # Check cache first
        if page_number in self.character_cache and not content_text:
            return self.character_cache[page_number].copy()
            
        characters = []
        
        # Get characters from scene progression
        scene_info = self._get_base_scene_info(page_number)
        if scene_characters := scene_info.get('characters', []):
            characters.extend(scene_characters)
            
        # Analyze content text if provided
        if content_text:
            # Get all character names from config
            all_characters = self.config['characters'].keys()
            
            # Check for character mentions in content
            for character in all_characters:
                if character.lower() in content_text.lower():
                    if character not in characters:
                        characters.append(character)
                        
        # Cache result if no content text was used
        if not content_text:
            self.character_cache[page_number] = characters.copy()
            
        return characters
        
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
            similarity_threshold = self.config.get('scene_management', {}).get('reference_page', {}).get('similarity_threshold', 0.7)
            
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
            
        phase_details = self.config.get('settings', {}).get('scene_progression', {}).get(story_phase, {})
        
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
        basic_action = self.config['story']['story_beats'].get(story_phase, '')
        
        # Construct enhanced action description with character emotions
        character_emotions = self.get_character_emotions(page_number)
        if character_emotions:
            character_emotion_texts = []
            
            # Add emotional state for all characters present on this page
            for char_name, emotion in character_emotions.items():
                char_emotion = f"{char_name} is {emotion}"
                character_emotion_texts.append(char_emotion)
            
            # Combine with basic action
            if character_emotion_texts:
                emotionally_enhanced_action = basic_action + " " + " ".join(character_emotion_texts)
                return emotionally_enhanced_action
        
        return basic_action

    def get_character_emotions(self, page_number: int) -> dict:
        """Get character emotions for a specific page by retrieving them from 
           each character's configuration in config['characters']."""
        page_str = str(page_number)
        character_emotions = {}
        
        # Get characters required for this page to avoid unnecessary lookups
        # Note: This might require _get_required_characters to be efficient
        #       or potentially passing the characters list as an argument.
        #       For simplicity now, we iterate through all characters in config.
        required_characters_on_page = self._get_required_characters(page_number)

        for char_type, char_data in self.config.get('characters', {}).items():
            char_name = char_data.get('name')
            if not char_name or char_name not in required_characters_on_page:
                continue # Skip if no name or not on this page
                
            # Get the emotional states defined for this character
            emotional_states = char_data.get('emotional_states', {})
            
            # Check if an emotion is defined for the current page (using page number as string key)
            if page_str in emotional_states:
                character_emotions[char_name] = emotional_states[page_str]
            # else: # Optionally log if no emotion is found for an active character
            #    logger.debug(f"No specific emotion found for character '{char_name}' on page {page_number}.")

        return character_emotions

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
        """Map page number to story phase using configuration."""
        # Use phase mapping from config
        phase_mapping = self.config.get('story_progression', {}).get('phase_mapping', {})
        
        # Log story phase lookup for debugging
        logger.debug(f"Looking up story phase for page {page_number}")
        
        phase_found = None
        
        if not phase_mapping:
            # Use fallback mapping from config
            fallback_mapping = self.config.get('scene_management', {}).get('story_phase_fallback', {})
            
            if not fallback_mapping:
                logger.warning("No phase mapping found in config, using hardcoded fallback mapping")
                return 'conclusion'  # Last resort fallback
            
            # Find the phase for the current page number
            for phase, page_range in fallback_mapping.items():
                start_page = page_range.get('start_page', 1)
                end_page = page_range.get('end_page', float('inf'))
                
                if start_page <= page_number <= end_page:
                    phase_found = phase
                    break
        
        # Find the phase for the current page number from main phase mapping
        if not phase_found:
            for phase, page_range in phase_mapping.items():
                start_page = page_range.get('start_page', 1)
                end_page = page_range.get('end_page', 10)
                
                if start_page <= page_number <= end_page:
                    phase_found = phase
                    break
        
        # Return default phase from config if still not found
        if not phase_found:
            phase_found = self.config.get('scene_management', {}).get('default_phase', 'conclusion')
            
        logger.info(f"Page {page_number} story phase: {phase_found}")
        
        # Log which characters are active in this phase
        logger.info(f"=== CHARACTER ANALYSIS FOR PAGE {page_number} ===")
        for char_type, char_info in self.config.get('characters', {}).items():
            char_name = char_info.get('name', char_type)
            intro_page = char_info.get('introduction', {}).get('page', 1)
            
            if page_number >= intro_page:
                # Check if this character has actions for this phase
                if phase_found in char_info.get('actions', {}):
                    action = char_info['actions'][phase_found]
                    emotion = char_info.get('emotional_states', {}).get(str(page_number), "No emotion specified")
                    logger.info(f"  CHARACTER: {char_name} - ACTIVE for phase {phase_found}")
                    logger.info(f"    Action: {action}")
                    logger.info(f"    Emotion: {emotion}")
                    
                    # Check for identical actions/emotions that might cause duplication
                    for other_char_type, other_char_info in self.config.get('characters', {}).items():
                        if char_type != other_char_type and page_number >= other_char_info.get('introduction', {}).get('page', 1):
                            if phase_found in other_char_info.get('actions', {}):
                                other_action = other_char_info['actions'][phase_found]
                                if action == other_action:
                                    logger.warning(f"  DUPLICATE ACTION DETECTED: {char_name} and {other_char_info.get('name')} have identical actions!")
                else:
                    logger.info(f"  CHARACTER: {char_name} - No action for phase {phase_found}")
            else:
                logger.info(f"  CHARACTER: {char_name} - Not yet introduced (intro page: {intro_page})")
        logger.info(f"=== END CHARACTER ANALYSIS ===")
            
        return phase_found 