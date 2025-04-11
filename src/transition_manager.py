from loguru import logger
from typing import Dict, List, Optional, Set
import re
from collections import defaultdict

class TransitionManager:
    def __init__(self, 
                 settings: dict,
                 environment_types: dict,
                 transition_rules: dict,
                 environment_transitions: dict,
                 page_emotions: dict,
                 story_progression: dict):
        """Initialize the transition manager with specific configuration sections."""
        # Store specific config sections
        self.settings = settings
        self.environment_types = environment_types
        self.transition_rules = transition_rules
        self.environment_transitions = environment_transitions
        self.page_emotions = page_emotions
        self.story_progression = story_progression
        
        # Derive scene_progression from settings
        self.scene_progression = self.settings.get('scene_progression', {})
        
        # Initialize environment cache
        self.environment_cache = {}
        
    def _get_environment_type(self, scene_info: dict) -> str:
        """Determine environment type from scene info using config-defined indicators."""
        description = scene_info.get('description', '').lower()
        elements = [elem.lower() for elem in scene_info.get('elements', [])]
        atmosphere = scene_info.get('atmosphere', '').lower()
        
        # Create a single text to analyze
        text_to_analyze = f"{description} {' '.join(elements)} {atmosphere}"
        
        # Count matches for each environment type
        env_scores = defaultdict(int)
        
        for env_type, env_data in self.environment_types.items():
            # Check indicators
            for indicator in env_data.get('indicators', []):
                if indicator.lower() in text_to_analyze:
                    env_scores[env_type] += 2  # Indicators are strong signals
                    
            # Check characteristics
            for characteristic in env_data.get('characteristics', []):
                if characteristic.lower() in text_to_analyze:
                    env_scores[env_type] += 1  # Characteristics are weaker signals
        
        if env_scores:
            # Return the environment type with highest score
            return max(env_scores.items(), key=lambda x: x[1])[0]
        
        return "default"
        
    def _get_transition_rules(self, from_env: str, to_env: str) -> dict:
        """Get transition rules for the environment change."""
        # Try to get specific rules
        rule_key = f"{from_env}_to_{to_env}"
        if rule_key in self.transition_rules:
            return self.transition_rules[rule_key]
            
        # Try reverse rules if available
        reverse_key = f"{to_env}_to_{from_env}"
        if reverse_key in self.transition_rules:
            rules = self.transition_rules[reverse_key].copy()
            # Reverse introduce and phase_out
            rules['introduce'], rules['phase_out'] = rules['phase_out'], rules['introduce']
            return rules
            
        # Use default rules
        return {
            'composition': self.environment_transitions['default']['blend_ratio'],
            'emphasis': to_env,
            'maintain': ['character_designs', 'art_style', 'color_harmony'],
            'introduce': [],
            'phase_out': []
        }
        
    def analyze_transition(self, current_page: int, previous_page: int) -> dict:
        """Analyze the transition between two pages and generate transition requirements."""
        # Get scene info for both pages
        current_scene = self._get_scene_info(current_page)
        previous_scene = self._get_scene_info(previous_page)
        
        if not current_scene or not previous_scene:
            return {}
            
        # Get environment types
        current_env = self._get_environment_type(current_scene)
        previous_env = self._get_environment_type(previous_scene)
        
        # Cache environments for future reference
        self.environment_cache[current_page] = current_env
        self.environment_cache[previous_page] = previous_env
        
        # If environments are different, get transition rules
        if current_env != previous_env:
            transition_rules = self._get_transition_rules(previous_env, current_env)
            
            # Get emotional transitions
            emotional_transition = self._get_emotional_transition(current_page, previous_page)
            
            # Combine transition rules with emotional guidance
            return self._generate_transition_requirements(
                current_env,
                previous_env,
                current_scene,
                previous_scene,
                transition_rules,
                emotional_transition
            )
            
        return {}
        
    def _get_emotional_transition(self, current_page: int, previous_page: int) -> dict:
        """Get emotional transition guidance between pages."""
        # Use the specific page_emotions attribute
        current_emotions = self.page_emotions.get(str(current_page), {})
        previous_emotions = self.page_emotions.get(str(previous_page), {})
        
        return {
            'from_emotion': previous_emotions.get('emotion', ''),
            'to_emotion': current_emotions.get('emotion', ''),
            'from_lighting': previous_emotions.get('lighting', ''),
            'to_lighting': current_emotions.get('lighting', ''),
            'transition_mood': current_emotions.get('transition_from_previous', '')
        }
        
    def _generate_transition_requirements(
        self,
        current_env: str,
        previous_env: str,
        current_scene: dict,
        previous_scene: dict,
        transition_rules: dict,
        emotional_transition: dict
    ) -> dict:
        """Generate transition requirements based on rules and emotional guidance."""
        # Get environment characteristics
        current_chars = self.environment_types.get(current_env, {}).get('characteristics', [])
        previous_chars = self.environment_types.get(previous_env, {}).get('characteristics', [])
        
        # Calculate composition ratio
        composition = transition_rules.get('composition', self._calculate_composition_ratio(current_chars, previous_chars))
        
        requirements = {
            'transition_type': f'{previous_env}_to_{current_env}',
            'composition_guide': composition,
            'emphasis': transition_rules.get('emphasis', current_env),
            'maintain': transition_rules.get('maintain', []),
            'introduce': transition_rules.get('introduce', []),
            'phase_out': transition_rules.get('phase_out', [])
        }
        
        # Add emotional transition guidance
        if emotional_transition:
            requirements['emotional_guidance'] = emotional_transition
            
        # Add lighting guidance
        requirements['lighting_guidance'] = self._get_lighting_guidance(
            current_env,
            previous_env,
            emotional_transition
        )
        
        logger.info(f"Generated transition requirements from {previous_env} to {current_env}")
        return requirements
        
    def _get_lighting_guidance(self, current_env: str, previous_env: str, emotional_transition: dict) -> str:
        """Generate lighting transition guidance."""
        current_lighting = self.environment_types.get(current_env, {}).get('lighting_defaults', [])
        previous_lighting = self.environment_types.get(previous_env, {}).get('lighting_defaults', [])
        
        # Combine with emotional lighting if available
        if emotional_transition.get('to_lighting'):
            current_lighting.append(emotional_transition['to_lighting'])
        if emotional_transition.get('from_lighting'):
            previous_lighting.append(emotional_transition['from_lighting'])
            
        return f"Transition lighting from {', '.join(previous_lighting)} to {', '.join(current_lighting)}"
        
    def get_reference_handling(self, current_page: int, reference_page: int) -> dict:
        """Get specific guidance for handling reference images based on scene analysis."""
        # Get environment types for both pages
        current_env = self.environment_cache.get(current_page)
        reference_env = self.environment_cache.get(reference_page)
        
        if not current_env or not reference_env:
            # Analyze environments if not in cache
            current_scene = self._get_scene_info(current_page)
            reference_scene = self._get_scene_info(reference_page)
            
            if not current_scene or not reference_scene:
                return {}
                
            current_env = self._get_environment_type(current_scene)
            reference_env = self._get_environment_type(reference_scene)
        
        # Get transition rules
        transition_rules = self._get_transition_rules(reference_env, current_env)
        
        # Generate reference handling guidance
        handling = {
            'maintain': transition_rules.get('maintain', ['character_designs', 'art_style', 'color_harmony']),
            'adapt': [],
            'ignore': transition_rules.get('phase_out', [])
        }
        
        # Add elements to adapt based on scene differences
        current_scene = self._get_scene_info(current_page)
        reference_scene = self._get_scene_info(reference_page)
        
        if current_scene and reference_scene:
            if current_scene.get('atmosphere') != reference_scene.get('atmosphere'):
                handling['adapt'].append('atmosphere')
            if current_scene.get('lighting') != reference_scene.get('lighting'):
                handling['adapt'].append('lighting')
            if current_scene.get('mood') != reference_scene.get('mood'):
                handling['adapt'].append('mood')
        
        return handling
        
    def _get_scene_info(self, page_number: int) -> Optional[dict]:
        """Get scene information for a specific page."""
        # Find the phase for this page
        # Use the specific story_progression attribute
        for phase, info in self.story_progression.get('phase_mapping', {}).items():
            if info.get('start_page') <= page_number <= info.get('end_page'):
                # Use the derived scene_progression attribute
                return self.scene_progression.get(phase, {})
        return None
        
    def _calculate_composition_ratio(self, current_chars: List[str], previous_chars: List[str]) -> str:
        """Calculate dynamic composition ratio based on environment characteristics."""
        # Default to balanced transition
        default_ratio = "50% previous, 50% current"
        
        # Handle empty lists safely
        if not current_chars or not previous_chars:
            return default_ratio
            
        # Calculate overlap between environments
        overlap = len(set(current_chars).intersection(set(previous_chars)))
        total_chars = len(set(current_chars).union(set(previous_chars)))
        
        if total_chars == 0:
            return default_ratio
            
        # Calculate how different the environments are
        difference_ratio = 1 - (overlap / total_chars)
        
        # More different environments need more dramatic transitions
        if difference_ratio > 0.7:
            return f"70% {current_chars[0]}, 30% {previous_chars[0]}"
        elif difference_ratio > 0.3:
            return f"60% {current_chars[0]}, 40% {previous_chars[0]}"
        else:
            return default_ratio 