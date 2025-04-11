from loguru import logger
from typing import List, Dict, Optional, Tuple

# Assuming SceneManager is appropriately imported or defined if needed elsewhere
# from .scene_manager import SceneManager 

class PromptManager:
    """Manages the generation of prompts for text and image generation."""

    def __init__(self, config: Dict, scene_manager):
        """Initialize the PromptManager."""
        self.config = config
        self.scene_manager = scene_manager
        # Store relevant sub-configs for easier access
        self.book_config = self.config.get('book', {})
        self.characters_config = self.config.get('characters', {})
        self.generation_config = self.config.get('generation', {})
        self.image_settings = self.config.get('image_settings', {})

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

    def generate_image_prompt(self, page_number: int, content_text: str, 
                              scene_requirements: Dict, required_characters: List[Dict], 
                              transition_requirements: Dict) -> str:
        """Generate the final prompt text for image generation."""
        
        # Get required components
        scene_analysis = self._create_scene_analysis(required_characters, scene_requirements, content_text)
        character_instructions = self._build_character_instructions(required_characters, scene_requirements)
        anti_duplication_rules = self._get_anti_duplication_rules(len(required_characters), required_characters)
        generation_steps = self._get_generation_steps()
        art_style_guidance = self._get_art_style_guidance()
        
        # Build the main prompt parts
        prompt_parts = [
            f"PROMPT TYPE: Children's book illustration for page {page_number}",
            f"TEXT CONTEXT: \"{content_text}\"", # Provide text for context
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
        ]

        # Add Transition Guidance if available
        if transition_requirements:
            prompt_parts.extend([
                "",
                "TRANSITION GUIDANCE (from previous page):"
            ])
            for key, value in transition_requirements.items():
                if isinstance(value, list):
                    prompt_parts.append(f"- {key.replace('_', ' ').title()}: {', '.join(value) if value else 'None'}")
                elif isinstance(value, dict):
                    prompt_parts.append(f"- {key.replace('_', ' ').title()}:")
                    for sub_key, sub_value in value.items():
                        prompt_parts.append(f"  - {sub_key.replace('_', ' ').title()}: {sub_value}")
                else:
                    prompt_parts.append(f"- {key.replace('_', ' ').title()}: {value}")

        prompt_parts.extend([
            "",
            "GENERATION STEPS:",
            generation_steps,
            "",
            "ART STYLE:",
            *art_style_guidance # Unpack the list
        ])
        
        final_prompt = "\n".join(prompt_parts)
        logger.debug(f"Final image prompt for page {page_number}: {final_prompt[:500]}...") # Log truncated prompt
        
        return final_prompt

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
        """Get anti-duplication rules from config and format them."""
        anti_dup_config = self.generation_config.get('anti_duplication_rules', {})
        rules = anti_dup_config.get('rules', [])
        consistency = anti_dup_config.get('consistency_rules', [])
        flexibility = anti_dup_config.get('flexibility_rules', [])
        verification = anti_dup_config.get('verification_rules', [])
        
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
        """Get generation steps from config or use defaults."""
        steps_list = self.generation_config.get('steps', [
            "Create the scene background based on requirements.",
            "Leave the scene EMPTY of characters initially.",
            "Add EACH character ONE at a time, ensuring NO duplication occurs.",
            "Position characters to clearly depict the story actions."
        ])
        formatted_steps = "SEQUENTIAL GENERATION PLAN:"
        for i, step in enumerate(steps_list, 1):
            formatted_steps += f"\nStep {i}: {step}"
        return formatted_steps

    def _get_art_style_guidance(self) -> List[str]:
        """Get art style guidance from config."""
        art_style_config = self.generation_config.get('art_style', {})
        width = self.image_settings.get('width', 1024)
        height = self.image_settings.get('height', 1024)
        return [
            f"- Tone: {art_style_config.get('tone', 'Child-friendly')}",
            f"- Quality: {art_style_config.get('quality', 'High detail')}",
            f"- Policy: {art_style_config.get('text_policy', 'NO text in image')}",
            f"- Format: {art_style_config.get('format', 'SQUARE image ({width}x{height} pixels)').format(width=width, height=height)}",
        ]

    # --- Cover Prompt Generation --- #

    def generate_cover_prompt(self) -> Tuple[str, str]:
        """Generate the prompt text components for the cover image."""
        cover_config = self.config.get('cover', {})
        
        # Use defaults if not specified
        prompt_template = cover_config.get('cover_prompt_template', "A vibrant book cover for '{title}'")
        title = cover_config.get('cover_title') or self.book_config.get('title', 'My Book')
        author = cover_config.get('cover_author', 'Generated by AI')
        theme = self.book_config.get('theme', "a children's story")
        art_style = self.book_config.get('art_style', 'illustration')
        characters_list = [c.get('name', f'Character {i+1}') for i, c in enumerate(self.characters_config.values())]
        characters = ", ".join(characters_list) if characters_list else "the main character"

        # Format the base prompt
        base_prompt = prompt_template.format(
            title=title, 
            characters=characters, # Keep names here for template compatibility
            theme=theme, 
            art_style=art_style,
            author=author
        )
        
        # Add Detailed Character Descriptions for Cover
        cover_char_details = self._build_cover_character_details(characters_list)
        
        # Combine into final prompt text
        # Note: The API client might handle combining text and reference image
        full_prompt_text = f"{base_prompt}\n\n{cover_char_details}\n\n**CONSISTENCY:** Ensure characters match details & reference style."

        logger.info(f"Cover prompt (base): {base_prompt}")
        logger.info(f"Cover character details added: {cover_char_details}")
        
        # Return the full text and the cover text separately for overlay
        cover_text_for_overlay = f"{title}\n{author}"
        return full_prompt_text, cover_text_for_overlay

    def _build_cover_character_details(self, characters_list: List[str]) -> str:
        """Builds the character details string specifically for the cover prompt."""
        details_list = ["CHARACTER DETAILS (MUST FOLLOW):"]
        for char_name in characters_list:
            char_config = next((cd for cd in self.characters_config.values() if cd.get('name') == char_name), None)
            if char_config:
                details = [f"- {char_name}:"]
                if appearance := char_config.get('appearance'):
                    details.append(f"  - Appearance: {appearance}")
                if outfit := char_config.get('outfit'):
                    details.append(f"  - Outfit: {outfit}")
                if features := char_config.get('features'):
                    details.append(f"  - Features: {features}")
                if details:
                     details_list.append("\n".join(details))
        return "\n".join(details_list) 