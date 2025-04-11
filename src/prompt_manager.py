from loguru import logger
from typing import List, Dict, Optional, Tuple
import base64
import os

# Assuming SceneManager and TransitionManager are appropriately imported or defined
from .scene_manager import SceneManager 
from .transition_manager import TransitionManager

class PromptManager:
    """Manages the generation of prompts for text and image generation."""

    def __init__(self, 
                 book_config: dict,
                 characters_config: dict,
                 generation_config: dict,
                 image_settings: dict,
                 cover_config: dict,
                 metadata_config: dict,
                 scene_manager: SceneManager, # Added type hint
                 transition_manager: TransitionManager): # Added TransitionManager
        """Initialize the PromptManager with specific configs and managers."""
        # Store specific config sections
        self.book_config = book_config
        self.characters_config = characters_config
        self.generation_config = generation_config
        self.image_settings = image_settings
        self.cover_config = cover_config
        self.metadata_config = metadata_config
        
        # Store injected managers
        self.scene_manager = scene_manager
        self.transition_manager = transition_manager # Store transition manager

    # --- Text Prompt Generation --- #

    def generate_text_prompt(self, page_number: int, previous_descriptions: Dict[int, str]) -> str:
        """Generate a prompt for the text generation model (e.g., for Gemini)."""
        
        # Get consistency context using previous descriptions
        consistency_context = self._get_consistency_context(page_number, previous_descriptions)
        
        # Get scene requirements from scene_manager
        # Note: Passing None for content_text as we are generating text, not image
        scene_requirements = self.scene_manager.get_scene_requirements(page_number, None) 
        
        # Build consistency rules from config
        consistency_rules = self._build_text_consistency_rules(consistency_context)
        
        # Build text instructions from config
        text_instructions = self._build_text_instructions()
        
        # Add final page instructions if needed
        final_instructions = self._build_final_page_instructions(page_number)
        
        # Build the complete prompt dynamically
        prompt_parts = [
            f"Create a children's book page with text for page {page_number} of \"{self.book_config.get('title', 'Untitled Book')}\".",
            ""
        ]
        
        # Add book details
        prompt_parts.extend(self._build_book_details())
        
        # Add character information
        prompt_parts.extend(self._build_character_summary())
        
        # Add scene requirements
        prompt_parts.extend(self._build_scene_summary(scene_requirements))
        
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
        
        # Add generation instructions from config
        prompt_parts.extend(self._build_text_generation_guidance())
        
        return "\n".join(prompt_parts)

    def _get_consistency_context(self, page_number: int, previous_descriptions: Dict[int, str]) -> str:
        """Generate context from previous pages for consistency."""
        context = []
        
        # Add character descriptions from config for initial context
        for char_data in self.characters_config.values():
            name = char_data.get('name', 'Unknown')
            desc = char_data.get('description', '')
            context.append(f"{name} ({desc})")
        
        # Add previous page descriptions for continuity (up to 5 previous)
        prev_pages = range(max(1, page_number - 5), page_number)
        for prev_page in prev_pages:
            if prev_page in previous_descriptions:
                page_desc = previous_descriptions[prev_page]
                context.append(f"Previous page {prev_page}: {page_desc}")
                
        return "\n".join(context) if context else "No previous context available."

    def _build_text_consistency_rules(self, consistency_context: str) -> List[str]:
        rules = ["Important consistency instructions:"]
        if 'character_consistency' in self.book_config:
            rules.extend(self.book_config['character_consistency'])
        else:
            rules.append("- Keep all character appearances EXACTLY THE SAME across all pages")
        
        if 'style_consistency' in self.book_config:
            rules.extend(self.book_config['style_consistency'])
        else:
            rules.append(f"- Maintain the same narrative tone throughout") # Text specific
            
        if consistency_context and "No previous context" not in consistency_context:
            rules.append(f"- **Narrative Flow:** Ensure the text flows logically from previous events.") # Simplified context reference
        return rules

    def _build_text_instructions(self) -> List[str]:
        instructions = ["FORMAT AND CONTENT INSTRUCTIONS:"]
        if 'text_instructions' in self.book_config:
            instructions.extend(self.book_config['text_instructions'])
        else:
            instructions.extend([
                "1. First, write the text for the page (2-3 child-friendly sentences) between \"TEXT START\" and \"TEXT END\"",
                "2. **Action:** The text MUST clearly describe what the main character(s) are *doing* in this scene",
                "3. **Progression:** The text should logically advance the story based on previous events",
            ])
        return instructions

    def _build_final_page_instructions(self, page_number: int) -> List[str]:
        final_instructions = []
        if page_number == self.book_config.get('page_count', 0):
            if 'final_page_instructions' in self.book_config:
                final_instructions = self.book_config['final_page_instructions']
            else:
                final_instructions = [
                    "FINAL PAGE INSTRUCTIONS:",
                    "- As this is the final page, provide a satisfying conclusion.",
                    "- Do NOT end with a question or cliffhanger.",
                    "- Wrap up the main storyline with a positive and clear ending."
                ]
        return final_instructions

    def _build_book_details(self) -> List[str]:
        details = ["Book Details:"]
        skip_keys = {'title', 'final_page_instructions', 'text_instructions', 'character_consistency', 'style_consistency'}
        for key, value in self.book_config.items():
            if isinstance(value, str) and key not in skip_keys:
                details.append(f"- {key.replace('_', ' ').title()}: {value}")
        return details
    
    def _build_character_summary(self) -> List[str]:
        summary = ["\nCharacters:"]
        for char_data in self.characters_config.values():
            summary.append(f"- {char_data.get('name', 'Unknown')} ({char_data.get('description', '')})")
        return summary

    def _build_scene_summary(self, scene_requirements: Optional[Dict]) -> List[str]:
        summary = []
        if scene_requirements:
            summary.extend([
                "\nSetting:",
                f"- Location: {scene_requirements.get('location', 'N/A')}",
                f"- Description: {scene_requirements.get('description', 'N/A')}",
                f"- Atmosphere: {scene_requirements.get('atmosphere', 'N/A')}"
            ])
            if elements := scene_requirements.get('elements'):
                summary.append("- Elements:")
                summary.extend([f"  * {element}" for element in elements])
        return summary

    def _build_text_generation_guidance(self) -> List[str]:
        guidance = []
        # Use default if not specified
        gen_instructions = self.book_config.get('generation_instructions', [
            "Please provide engaging text describing character actions and story progression.",
            "The text should be enclosed between \"TEXT START\" and \"TEXT END\" markers."
        ])
        if gen_instructions:
             guidance.extend(["", "Generation Guidance:"]) # Add header
             guidance.extend([f"- {inst}" for inst in gen_instructions]) # Format as list
        return guidance

    # --- Image Prompt Generation --- #

    def generate_image_prompt(self, 
                              page_number: int, 
                              story_text: str, 
                              scene_requirements: Dict, 
                              required_characters: List[Dict], 
                              reference_page_num: Optional[int], # Changed from transition_requirements
                              original_image_files: Dict[int, str] # Added original files dict
                              ) -> str:
        """Generate the final prompt string for image generation, incorporating reference image if applicable."""
        
        # Build the core prompt parts (scene, characters, rules, style)
        prompt_parts = self._build_core_image_prompt(page_number, story_text, scene_requirements, required_characters)
        
        # --- Handle Reference Image and Guidance --- #
        reference_image_part = None
        reference_guidance_part = None
        
        if reference_page_num:
            ref_image_path_str = original_image_files.get(reference_page_num)
            if ref_image_path_str and os.path.exists(ref_image_path_str):
                try:
                    # Load and encode image
                    with open(ref_image_path_str, 'rb') as f: image_data = f.read()
                    image_base64 = base64.b64encode(image_data).decode('utf-8')
                    
                    # Get reference handling guidance from TransitionManager
                    reference_handling = self.transition_manager.get_reference_handling(page_number, reference_page_num)
                    
                    # Format guidance text
                    guidance_lines = ["REFERENCE IMAGE GUIDANCE:"]
                    if maintain := reference_handling.get('maintain'): guidance_lines.extend([f"- Maintain: {item}" for item in maintain])
                    if adapt := reference_handling.get('adapt'): guidance_lines.extend([f"- Adapt: {item}" for item in adapt])
                    if ignore := reference_handling.get('ignore'): guidance_lines.extend([f"- Ignore: {item}" for item in ignore])
                    
                    # Create prompt parts for reference image and guidance
                    reference_guidance_part = "\n".join(guidance_lines)
                    reference_image_part = { # Store as dict for later processing if needed, though APIClient expects string now
                        "inlineData": {"mimeType": "image/png", "data": image_base64}
                    }
                    logger.info(f"Successfully added reference image from page {reference_page_num} and guidance to prompt for page {page_number}")
                    
                except Exception as e:
                    logger.warning(f"Error processing reference image from {ref_image_path_str}: {str(e)}")
            else:
                logger.warning(f"Reference image path for page {reference_page_num} not found or invalid.")

        # --- Assemble Final Prompt --- #
        # Insert reference guidance *before* critical requirements if it exists
        if reference_guidance_part:
            # Find the index of the critical requirements header
            try:
                critical_req_index = prompt_parts.index("CRITICAL REQUIREMENTS (FOLLOW THESE EXACTLY):")
                # Insert reference guidance and a separator before it
                prompt_parts.insert(critical_req_index, "") # Separator
                prompt_parts.insert(critical_req_index + 1, reference_guidance_part)
                prompt_parts.insert(critical_req_index + 2, "\n**CRITICAL CONSISTENCY NOTE:** Use text rules (marked 'ALWAYS') as primary source for appearance. Use reference image mainly for style, palette, placement. TEXT RULES OVERRIDE IMAGE CONFLICTS.")
                prompt_parts.insert(critical_req_index + 3, "") # Separator
            except ValueError:
                logger.warning("Could not find 'CRITICAL REQUIREMENTS' header to insert reference guidance before.")
                # Append at the end as a fallback
                prompt_parts.extend(["", reference_guidance_part, "\n**CRITICAL CONSISTENCY NOTE:** Use text rules (marked 'ALWAYS') as primary source for appearance. Use reference image mainly for style, palette, placement. TEXT RULES OVERRIDE IMAGE CONFLICTS."])

        # NOTE: The actual image data (reference_image_part) is NOT added to the text prompt string here.
        # The APIClient.generate_image method handles sending the reference_image_b64 separately.
        # This method now focuses on generating the *textual* part of the prompt, including guidance.

        final_prompt_string = "\n".join(prompt_parts)
        logger.debug(f"Final image prompt text for page {page_number}: {final_prompt_string[:500]}...")
        
        return final_prompt_string

    def _build_core_image_prompt(self, page_number: int, story_text: str, 
                                 scene_requirements: Dict, required_characters: List[Dict]) -> List[str]:
        """Builds the main list of prompt parts excluding reference image handling."""
        # Get required components
        scene_analysis = self._create_scene_analysis(required_characters, scene_requirements, story_text)
        character_instructions = self._build_character_instructions(required_characters, scene_requirements)
        anti_duplication_rules = self._get_anti_duplication_rules(len(required_characters), required_characters)
        generation_steps = self._get_generation_steps()
        art_style_guidance = self._get_art_style_guidance()

        # Build the main prompt parts list
        prompt_parts = [
            f"PROMPT TYPE: Children's book illustration for page {page_number}",
            f"TEXT CONTEXT: \"{story_text}\"",
            "",
            f"SCENE ANALYSIS:",
            scene_analysis,
            "",
            "CRITICAL REQUIREMENTS (FOLLOW THESE EXACTLY):",
            "- NO CHARACTER DUPLICATION: Each character must appear EXACTLY ONCE in the image",
            f"- CHARACTERS:",
            character_instructions,
            "",
            anti_duplication_rules,
            "",
            "GENERATION STEPS:",
            generation_steps,
            "",
            "ART STYLE:",
            *art_style_guidance
        ]
        return prompt_parts

    def _create_scene_analysis(self, required_characters: List[dict], scene_requirements: dict, 
                               content_text: str) -> str: # Removed story_actions as it was empty
        """Create scene analysis with character and environment details."""
        scene_desc = scene_requirements.get('description', 'A scene')
        atmosphere = scene_requirements.get('atmosphere', 'neutral')
        elements = scene_requirements.get('elements', [])
        character_list = ', '.join([f"{c['name']} (exactly 1)" for c in required_characters])
        elements_text = "\n".join([f"- {elem}" for elem in elements]) if elements else "No specific elements defined"
        
        scene_analysis_parts = [
            f"1. Scene Description: {scene_desc}",
            f"2. Character List: {character_list}",
            f"3. Total Characters: {len(required_characters)}",
            f"4. Atmosphere: {atmosphere}",
            f"5. Key Elements:",
            elements_text,
            f"6. Guiding Text Context: \"{content_text}\"" # Reference the page text
        ]
        
        # Add visual details from scene_requirements
        for visual_key in ['emotion', 'lighting', 'mood', 'visual_focus', 'color_palette']:
            if value := scene_requirements.get(visual_key):
                scene_analysis_parts.append(f"7. Visual {visual_key.replace('_', ' ').title()}: {value}")
                
        if env_type := scene_requirements.get('environment_type'):
            scene_analysis_parts.append(f"8. Environment Type: {env_type}")
            if characteristics := scene_requirements.get('environment_characteristics'):
                 scene_analysis_parts.append(f"9. Environment Characteristics: {', '.join(characteristics)}")
                
        return "\n".join(scene_analysis_parts)

    def _build_character_instructions(self, required_characters: List[dict], scene_requirements: dict) -> str:
        """Build detailed instructions for each character, including appearance rules."""
        instructions = [] # Start empty, will join later
        char_names = set()
        all_char_rules = scene_requirements.get('character_appearance_rules', {})

        for i, char in enumerate(required_characters):
            char_name = char.get('name')
            if not char_name or char_name in char_names:
                continue
            char_names.add(char_name)

            char_details = [
                f"{i+1}. Character: {char_name} | Description: {char.get('description', 'N/A')}"
            ]
            
            char_rules = all_char_rules.get(char_name, {})
            if char_rules:
                char_details.append("   | APPEARANCE RULES (MUST FOLLOW):")
                for rule_type, rule_value in char_rules.items():
                    rule_text = f"     - {rule_type.capitalize()}: {(', '.join(rule_value) if isinstance(rule_value, list) else rule_value)}"
                    char_details.append(rule_text)
            else:
                 # Fallback to standard appearance attributes from character definition
                 appearance_rules_added = False
                 for attr in ['appearance', 'outfit', 'features']:
                     if value := char.get(attr):
                         if not appearance_rules_added:
                              char_details.append("   | MANDATORY APPEARANCE RULES:")
                              appearance_rules_added = True
                         char_details.append(f"     - {attr.capitalize()} (ALWAYS): {value}")

            if action := char.get('action'):
                char_details.append(f"   | Action: {action}")
            if emotion := char.get('emotion'):
                char_details.append(f"   | Emotion: {emotion}")
            else:
                 char_details.append(f"   | Emotion: None specified")
                 
            instructions.append("\n".join(char_details))
            
        return "\n\n".join(instructions)

    def _get_anti_duplication_rules(self, num_characters: int, required_characters: Optional[List[dict]] = None) -> str:
        """Get anti-duplication rules from generation config."""
        # Use self.generation_config
        rules_config = self.generation_config.get('anti_duplication_rules', {})
        rules = rules_config.get('rules', [])
        consistency = rules_config.get('consistency_rules', [])
        flexibility = rules_config.get('flexibility_rules', [])
        verification = rules_config.get('verification_rules', [])
        
        characters_text = []
        if required_characters:
            characters_text = [
                f"- {char.get('name', '?')}: {char.get('description', '')} - MUST APPEAR EXACTLY ONCE"
                for char in required_characters
            ]
        
        formatted_rules = ["ANTI-DUPLICATION INSTRUCTIONS (EXTREMELY IMPORTANT):"]
        if rules:
             formatted_rules.append("\nCORE RULES:")
             formatted_rules.extend([f"- {rule.format(num_characters=num_characters)}" for rule in rules])
        if characters_text:
            formatted_rules.append("\nCHARACTER COUNT REQUIREMENTS:")
            formatted_rules.extend(characters_text)
        if consistency:
            formatted_rules.append("\nCONSISTENCY REQUIREMENTS:")
            formatted_rules.extend([f"- {rule}" for rule in consistency])
        if flexibility:
            formatted_rules.append("\nALLOWED VARIATIONS:")
            formatted_rules.extend([f"- {rule}" for rule in flexibility])
        if verification:
            formatted_rules.append("\nFINAL VERIFICATION (BEFORE RENDERING):")
            formatted_rules.extend([f"- {rule.format(num_characters=num_characters)}" for rule in verification])
        
        formatted_rules.append("\nWARNING: DUPLICATING CHARACTERS IS THE MOST COMMON ERROR.")
        formatted_rules.append("CAREFULLY CHECK YOUR SCENE AND REMOVE ANY DUPLICATE CHARACTERS.")
        
        return "\n".join(formatted_rules)

    def _get_generation_steps(self) -> str:
        """Get generation steps from generation config."""
        # Use self.generation_config
        steps = self.generation_config.get('steps', [
            "Analyze scene requirements.",
            "Place characters according to instructions.",
            "Ensure character appearance consistency.",
            "Render image in the specified art style."
        ])
        return "\n".join([f"- {step}" for step in steps])

    def _get_art_style_guidance(self) -> List[str]:
        """Get art style guidance from generation and image settings config."""
        # Use self.generation_config and self.image_settings
        art_style_config = self.generation_config.get('art_style', {})
        guidance = [
            f"- Overall Style: {self.book_config.get('art_style', 'Not specified')}", # Get base style from book config
            f"- Tone: {art_style_config.get('tone', 'Bright, child-friendly')}",
            f"- Quality: {art_style_config.get('quality', 'High detail, clean lines')}",
            f"- Text Policy: {art_style_config.get('text_policy', 'NO text elements in the image')}",
            f"- Format: {art_style_config.get('format', 'SQUARE image ({width}x{height} pixels)').format(width=self.image_settings.get('width', 1024), height=self.image_settings.get('height', 1024))}"
        ]
        return guidance

    # --- Cover Prompt Generation --- #

    def generate_cover_prompt(self) -> Tuple[str, str]:
        """Generates the prompt for the cover image and the text for overlay."""
        
        # Use specific config sections directly
        template = self.cover_config.get('cover_prompt_template', 
                                       "Children's book cover for '{title}'. Theme: {theme}. Art style: {art_style}. Featuring {characters}. NO text in the image.")
        characters_on_cover_names = self.cover_config.get('characters_on_cover', []) # Get names from cover config
        
        # Build character details string based on names
        character_details_str = self._build_cover_character_details(characters_on_cover_names)
        
        # Prepare context for the template
        context = {
            'title': self.book_config.get('title', 'My Book'),
            'theme': self.book_config.get('theme', 'Adventure'),
            'art_style': self.book_config.get('art_style', 'Whimsical'),
            'characters': character_details_str or "main characters"
        }
        
        full_prompt = template.format(**context)
        
        # Prepare text for overlay
        title = self.cover_config.get('cover_title') or self.book_config.get('title', 'My Book')
        author = self.cover_config.get('cover_author') or self.metadata_config.get('author') or 'Generated by AI'
        cover_text = f"{title}\n{author}"
        
        logger.info("Generated cover prompt and text overlay content.")
        return full_prompt, cover_text

    def _build_cover_character_details(self, characters_list: List[str]) -> str:
        """Build a string describing characters for the cover prompt."""
        details = []
        if not characters_list: # If list is empty, try to use first main character
            main_char_key = next(iter(self.characters_config), None)
            if main_char_key:
                 char_info = self.characters_config[main_char_key]
                 details.append(f"{char_info.get('name', 'the main character')} ({char_info.get('appearance', '')}, {char_info.get('outfit', '')})")
            else:
                 return "the main characters" # Fallback if no characters defined at all
        else:
            for char_name in characters_list:
                # Find the character info by name
                char_info = next((info for info in self.characters_config.values() if info.get('name') == char_name), None)
                if char_info:
                    details.append(f"{char_name} ({char_info.get('appearance', '')}, {char_info.get('outfit', '')})")
                else:
                    details.append(char_name) # Append name if details not found
                    
        return ", ".join(details) 

    # --- Backup Text Prompt Generation --- #

    def generate_backup_text_prompt(self, page_number: int, context_text: str, previous_descriptions: Dict[int, str]) -> str:
        """Generate a prompt specifically for creating backup story text when extraction fails or is too short."""
        
        # Get previous page context
        prev_context_str = ""
        if page_number > 1 and (page_number - 1) in previous_descriptions:
            prev_context_str = f"Previous page story: {previous_descriptions[page_number - 1]}"
        else:
            prev_context_str = "This is the first page."
            
        # Format the problematic context text
        orig_context_str = f"The previous attempt resulted in very short or unusable text: \"{context_text[:200]}{'...' if len(context_text) > 200 else ''}\""

        book_title = self.book_config.get('title', 'Untitled Book')

        prompt = f"""\nTASK: Rewrite story text for page {page_number} of the children's book "{book_title}".
        
CONTEXT:
- {prev_context_str}
- {orig_context_str}

INSTRUCTIONS:
- Write 2-3 engaging, child-friendly sentences ONLY for page {page_number}.
- Ensure the text is consistent with the previous page context and book theme.
- The text should be suitable for illustration, describing character actions or advancing the plot.
- **CRITICAL:** ONLY provide the story text for the page. Do NOT include any labels, headings (like 'TEXT:' or 'Page {page_number}:'), or explanations.
"""
        logger.debug(f"Generated backup text prompt for page {page_number}")
        return prompt 