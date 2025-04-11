import os
import base64
import json
import requests
import re
from loguru import logger
from typing import Dict, Any, Optional, Tuple, List
from dotenv import load_dotenv

class APIClient:
    def __init__(self, generation_settings: Dict[str, Any]):
        """Initialize the API client with generation-specific configuration."""
        # Load environment variables
        load_dotenv()
        
        # Load model configuration from environment variables
        self.model = os.getenv('GEMINI_MODEL', 'gemini-2.0-flash-exp')
        self.fallback_model = os.getenv('GEMINI_FALLBACK_MODEL', 'gemini-2.0-flash-exp-image-generation')
        
        # Load debug settings from environment variables
        self.debug_enable_prompt = os.getenv('DEBUG_ENABLE_PROMPT', 'true').lower() == 'true'
        self.debug_enable_response = os.getenv('DEBUG_ENABLE_RESPONSE', 'true').lower() == 'true'
        self.debug_verbose_level = int(os.getenv('DEBUG_VERBOSE_LEVEL', '2'))
        
        # Store generation-specific config for later use
        self.generation_settings = generation_settings
        
        # Initialize API key
        self.api_key = self._initialize_api_key()
        
    def _initialize_api_key(self) -> str:
        """Initialize and validate the API key."""
        api_key = os.getenv("GEMINI_API_KEY")
        
        # Validate API key
        if not api_key:
            raise ValueError("API key not found. Please set it as GEMINI_API_KEY environment variable.")
        
        if not isinstance(api_key, str) or len(api_key) < 10:
            raise ValueError("API key appears to be invalid. Please check your API key format.")
        
        # Validate API key with Google Gemini format
        if not api_key.startswith("AI") and not (len(api_key) > 30):
            logger.warning("API key doesn't match typical Google Gemini API key format. This might cause authentication issues.")
        
        return api_key

    def make_request(self, url: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make an API request with proper error handling."""
        # Log the exact prompt being sent to the API (for debugging)
        if self.debug_enable_prompt and 'contents' in data and len(data['contents']) > 0:
            self._log_prompt_debug(data)
        
        # Make the API request
        try:
            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key
            }
            
            response = requests.post(url, headers=headers, json=data)
            
            # Check if the request was successful
            if response.status_code == 200:
                response_json = response.json()
                
                # Debug the response if enabled
                if self.debug_enable_response:
                    self._log_response_debug(response_json)
                
                return response_json
            else:
                self._handle_error_response(response)
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            raise Exception(f"API request failed: {str(e)}")
        except Exception as e:
            logger.error(f"Error making API request: {str(e)}")
            raise

    def _log_prompt_debug(self, data: Dict[str, Any]) -> None:
        """Log prompt debugging information."""
        logger.info("===== PROMPT DEBUGGING =====")
        
        # Log all prompt parts
        for i, part in enumerate(data['contents'][0]['parts']):
            if 'text' in part:
                logger.info(f"PROMPT TEXT PART {i}:\n{part['text']}\n")
            elif 'inlineData' in part:
                logger.info(f"PROMPT PART {i}: [INLINE DATA - {part['inlineData']['mimeType']}]")
        
        # If this is an image generation request
        if 'generation_config' in data and data.get('model', '').startswith('gemini'):
            logger.info("===== CHARACTER COUNT ANALYSIS =====")
            # Extract character info for debugging
            text_parts = [part['text'] for part in data['contents'][0]['parts'] if 'text' in part]
            full_prompt = "\n".join(text_parts)
            
            # Find character count sections
            char_count_match = re.search(r"TOTAL CHARACTERS: EXACTLY (\d+)", full_prompt)
            if char_count_match:
                logger.info(f"Specified character count: {char_count_match.group(1)}")
            
            # Find character names
            char_names = re.findall(r"Character: ([^\|]+)", full_prompt)
            if char_names:
                logger.info(f"Characters in prompt: {', '.join(char_names)}")
                logger.info(f"Total characters found in prompt: {len(char_names)}")
            
            # Find anti-duplication rules
            anti_dup_section = re.search(r"ANTI-DUPLICATION INSTRUCTIONS.*?(?=ART STYLE|\Z)", full_prompt, re.DOTALL)
            if anti_dup_section:
                logger.info(f"Anti-duplication section exists: {len(anti_dup_section.group(0))} characters")
        
        logger.info("===== END PROMPT DEBUGGING =====")

    def _log_response_debug(self, response_json: Dict[str, Any]) -> None:
        """Log response debugging information."""
        logger.info("===== RESPONSE DEBUGGING =====")
        
        # Check for candidates
        if 'candidates' in response_json:
            logger.info(f"Number of candidates: {len(response_json['candidates'])}")
            
            # Check each candidate
            for idx, candidate in enumerate(response_json['candidates']):
                logger.info(f"Candidate {idx + 1}:")
                
                # Check for content in candidate
                if 'content' in candidate:
                    content = candidate['content']
                    
                    # Check for parts in content
                    if 'parts' in content:
                        parts = content['parts']
                        logger.info(f"  Number of parts: {len(parts)}")
                        
                        # Check each part
                        for part_idx, part in enumerate(parts):
                            logger.info(f"  Part {part_idx + 1} type: {list(part.keys())}")
                            
                            # For text parts, log the text
                            if 'text' in part and self.debug_verbose_level >= 2:
                                text_preview = part['text'][:100] + "..." if len(part['text']) > 100 else part['text']
                                logger.info(f"    Text preview: {text_preview}")
                            
                            # For inline data, log mime type and data length
                            if 'inlineData' in part:
                                mime_type = part['inlineData'].get('mimeType', 'unknown')
                                data_length = len(part['inlineData'].get('data', ''))
                                logger.info(f"    Inline data: {mime_type}, length: {data_length}")
                                
                                # For image data, log additional info
                                if mime_type.startswith('image/') and data_length == 0:
                                    logger.error(f"    Empty image data detected! MIME type is {mime_type} but data length is 0")
                    else:
                        logger.info("  No parts found in content")
                else:
                    logger.info("  No content found in candidate")
        else:
            logger.warning("No candidates found in response")
        
        # Check for other response elements
        for key in response_json:
            if key != 'candidates':
                logger.info(f"Response contains '{key}'")
        
        # If response has a specific structure, check for other expected fields
        if self.debug_verbose_level >= 2:
            logger.info(f"Full response structure: {json.dumps(response_json, indent=2, default=str)[:500]}...")
        
        logger.info("===== END RESPONSE DEBUGGING =====")

    def _handle_error_response(self, response: requests.Response) -> None:
        """Handle error responses from the API."""
        if response.status_code == 403:
            # Specific handling for authorization issues
            error_msg = f"API request failed with status code 403: Authentication failed. Please verify your API key has the correct permissions for this API and model."
            try:
                error_json = response.json()
                if 'error' in error_json:
                    error_msg = f"API request failed with status code 403: {error_json['error']['message']}"
            except:
                pass
            logger.error(error_msg)
            raise Exception(error_msg)
        else:
            # Handle other API errors
            error_msg = f"API request failed with status code {response.status_code}"
            try:
                error_json = response.json()
                if 'error' in error_json:
                    error_msg = f"{error_msg}: {error_json['error']['message']}"
            except:
                error_msg = f"{error_msg}: {response.text}"
            
            logger.error(error_msg)
            raise Exception(error_msg)

    def get_api_url(self, model_name: Optional[str] = None) -> str:
        """Get the API URL for the specified model."""
        model = model_name or self.model
        return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def get_generation_config(self, temperature: float = 0.7, seed: Optional[int] = None) -> Dict[str, Any]:
        """Get generation configuration."""
        # Use the stored generation_settings 
        gen_config_section = self.generation_settings.get('config', {})
        
        generation_config = {
            "temperature": temperature,
            "topP": gen_config_section.get('top_p', 0.9),
            "topK": gen_config_section.get('top_k', 40),
            "maxOutputTokens": gen_config_section.get('max_output_tokens', 8192),
        }
        
        if seed is not None:
            generation_config["seed"] = seed
        
        # Different models support different responseModalities
        model_name = self.model.lower()
        
        # Add responseModalities for models that support image generation
        if "gemini" in model_name and ("image-generation" in model_name or "-flash-exp" in model_name or "-1.5" in model_name):
            generation_config["responseModalities"] = ["Text", "Image"]
        
        return generation_config 

    def _extract_story_text_from_response(self, full_text: str, page_number: Optional[int] = None) -> str:
        """Extract just the story text from the full API response using heuristics."""
        # Heuristic 1: Check for specific markers
        if "TEXT START" in full_text and "TEXT END" in full_text:
            start_idx = full_text.find("TEXT START") + len("TEXT START")
            end_idx = full_text.find("TEXT END")
            if start_idx < end_idx:
                extracted_text = full_text[start_idx:end_idx].strip()
                if extracted_text: 
                    logger.debug(f"Extracted text using START/END markers (Page {page_number or 'N/A'}).")
                    return extracted_text

        lines = full_text.split('\\n')
        story_lines = []
        in_story_section = False

        # Heuristic 2: Look for lines after "text:" marker
        for line in lines:
            line_lower = line.strip().lower()
            if not line_lower: continue
            # Allow variations like "Story Text:" or "Page Text:"
            if any(marker in line_lower for marker in ["text:", "story text:", "page text:"]):
                in_story_section = True
                # Check if the text follows immediately on the same line after the marker
                marker_pos = -1
                for marker in ["text:", "story text:", "page text:"]:
                    if marker in line_lower:
                        marker_pos = line_lower.find(marker) + len(marker)
                        break
                if marker_pos != -1 and len(line) > marker_pos:
                    potential_text = line[marker_pos:].strip()
                    if potential_text:
                       story_lines.append(potential_text)
                continue # Move to the next line after finding the marker

            # Stop if we hit common markers indicating the end of the story part
            if any(stop_marker in line_lower for stop_marker in ["illustration:", "image prompt:", "visual description:", "scene description:"]):
                 # If we were in a story section, stop collecting
                 if in_story_section:
                     break 
                 # Otherwise, continue scanning in case the text marker appears later

            if in_story_section: 
                story_lines.append(line.strip())

        if story_lines:
            logger.debug(f"Extracted text using 'text:' marker heuristic (Page {page_number or 'N/A'}).")
            return "\\n".join(story_lines).strip()

        # Heuristic 3: Try lines enclosed in double quotes
        quoted_lines = [l.strip().strip('"') for l in lines if l.strip().count('"') >= 2 and len(l.strip()) > 2]
        if quoted_lines:
             # Filter out potential non-story quoted lines (like settings)
             filtered_quoted_lines = [ql for ql in quoted_lines if ':' not in ql and not ql.lower().startswith(("scene:", "character:", "setting:"))]
             if filtered_quoted_lines:
                 logger.debug(f"Extracted text using quote heuristic (Page {page_number or 'N/A'}).")
                 return "\\n".join(filtered_quoted_lines).strip()


        # Heuristic 4: Try lines after a page header (if page_number provided)
        if page_number is not None:
            page_marker_found_idx = -1
            for i, line in enumerate(lines):
                # Look for "page X" or "Page X" at the start or end of a line
                if re.search(rf'(^|\s)page {page_number}(\s|$)', line.lower()):
                    page_marker_found_idx = i
                    break
            
            if page_marker_found_idx != -1:
                # Look for plausible story lines in the next few lines
                candidate_lines = [l.strip() for l in lines[page_marker_found_idx+1 : page_marker_found_idx+6] 
                                   if l.strip() and 
                                   not l.startswith(('#', '**', '-')) and 
                                   ':' not in l and
                                   len(l.split()) > 2] # Avoid single-word lines or very short lines
                if candidate_lines:
                    logger.debug(f"Extracted text using page header heuristic (Page {page_number}).")
                    # Join first few plausible lines, but limit length
                    return "\\n".join(candidate_lines[:3]).strip() 

        # Fallback: Return the first 3 non-empty, non-heading lines if specific markers fail
        fallback_lines = [l.strip() for l in lines if l.strip() and not l.startswith(('#', '**', '-')) and ':' not in l][:3]
        if fallback_lines:
            logger.warning(f"Using fallback extraction (first 3 non-empty lines) for page {page_number or 'N/A'}.")
            return "\\n".join(fallback_lines).strip()

        # Ultimate fallback: Return the original text if no heuristics worked
        logger.error(f"Failed to extract structured story text for page {page_number or 'N/A'}. Returning full response.")
        return full_text.strip()

    def generate_story_text(self, prompt: str, conversation_history: Optional[list] = None, page_number: Optional[int] = None, temperature: Optional[float] = None) -> Tuple[str, bool]:
        """Generate story text using the API and extract the narrative part.
        
        Returns:
            Tuple[str, bool]: (extracted_story_text, success)
        """
        # Use conversation history for context if available
        generation_input = conversation_history.copy() if conversation_history else []
        generation_input.append(prompt)
        
        # Prepare the request data
        data = {
            "contents": [
                {"role": "user", "parts": [{"text": p}]} if i % 2 == 0 else {"role": "model", "parts": [{"text": p}]}
                for i, p in enumerate(generation_input)
            ],
            "generationConfig": self.get_generation_config(temperature=temperature if temperature is not None else 0.7), # Use provided temp or default
            "safetySettings": self.safety_settings
        }
        
        try:
            # Make the API request
            api_url = self.get_api_url()
            response_json = self.make_request(api_url, data)
            
            # Extract text from the response
            if 'candidates' in response_json and len(response_json['candidates']) > 0:
                candidate = response_json['candidates'][0]
                if 'content' in candidate and 'parts' in candidate['content'] and len(candidate['content']['parts']) > 0:
                    full_text_response = candidate['content']['parts'][0].get('text', '')
                    if full_text_response:
                        # Extract the story text using the new helper method
                        extracted_text = self._extract_story_text_from_response(full_text_response, page_number)
                        return extracted_text, True
                    else:
                        logger.error("API response candidate part contained no text.")
                        return "", False
                else:
                     logger.error("API response candidate structure invalid (missing content/parts).")
                     return "", False
            else:
                logger.error("API response did not contain valid candidates.")
                return "", False

        except Exception as e:
            logger.error(f"Error during text generation API call or processing: {str(e)}")
            return "", False

    def generate_backup_story(self, prompt: str, temperature: float = 0.7) -> Tuple[str, bool]:
        """Generate a backup story text using the API.
        
        Returns:
            Tuple[str, bool]: (generated_text, success)
        """
        # Prepare the request data
        data = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": self.get_generation_config(temperature=temperature)
        }
        
        # Make the API request
        url = self.get_api_url()
        response = self.make_request(url, data)
        
        if response and 'candidates' in response and response['candidates']:
            backup_text = response['candidates'][0]['content']['parts'][0]['text'].strip()
            # Clean up any markdown or other formatting
            backup_text = backup_text.replace('*', '').replace('#', '').replace('`', '')
            return backup_text, True
        else:
            return "", False

    def generate_image(self, prompt_text: str, safety_settings: Optional[List[Dict[str, str]]] = None, reference_image_b64: Optional[str] = None, page_number: Optional[int] = None, scene_requirements: Optional[dict] = None) -> Optional[List[str]]:
        """Generate an image using the Gemini API, optionally with a reference image.
        
        Args:
            prompt_text: The prompt text for image generation
            safety_settings: Optional safety settings for content filtering
            reference_image_b64: Optional base64 encoded string of the reference image (PNG format expected)
            page_number: Optional page number for logging/debugging purposes
            scene_requirements: Optional dictionary containing scene details, including potential reference_override rules.
            
        Returns:
            Optional[List[str]]: List of base64 encoded image strings, or None on failure.
        """
        logger.info(f"Generating image (Page: {page_number if page_number is not None else 'N/A'}) - Ref Image: {'Yes' if reference_image_b64 else 'No'}")

        # Prepare the parts for the API request contents
        parts = []
        # Add the text prompt first
        parts.append({"text": prompt_text})
        
        # Add the reference image and its specific handling instructions if provided
        if reference_image_b64:
            logger.debug(f"Adding reference image data (length: {len(reference_image_b64)}) to request parts.")
            
            # --- Add Reference Override Guidance --- #
            reference_override_guidance = []
            if scene_requirements and 'reference_override' in scene_requirements:
                override_rules = scene_requirements['reference_override']
                reference_override_guidance.append("\nREFERENCE OVERRIDE INSTRUCTIONS:")
                if ignore := override_rules.get('ignore_elements'):
                    reference_override_guidance.append("IGNORE these from reference image:")
                    reference_override_guidance.extend(f"- {item}" for item in ignore)
                if force := override_rules.get('force_elements'):
                    reference_override_guidance.append("FORCE these elements (override reference if needed):")
                    reference_override_guidance.extend(f"- {item}" for item in force)
                # Potentially add maintain_only rules here too if needed

                if len(reference_override_guidance) > 1: # Only add if rules were found
                    parts.append({"text": "\n".join(reference_override_guidance)})
            # --- End Reference Override Guidance --- #

            # Add the generic consistency note (prioritizing text for character details)
            # This should come AFTER specific override rules but BEFORE the image data
            parts.append({"text": "\n**CRITICAL CONSISTENCY NOTE:** Use the text-based \"CHARACTER INSTRUCTIONS\" (especially rules marked with \"ALWAYS\") as the PRIMARY source for character appearance details (features, clothing, colors). Use the reference image below MAINLY for overall style, color palette, character placement, and general visual guidance. If the reference image contradicts a specific \"ALWAYS\" rule in the text, FOLLOW THE TEXT RULE."})

            # Add the image data itself
            parts.append({
                "inlineData": {
                    "mimeType": "image/png", # Assuming PNG reference images
                    "data": reference_image_b64
                }
            })
        
        # Prepare the data payload
        data = {
            "contents": [{
                "role": "user",
                "parts": parts # Use the dynamically created parts list
            }],
            "generationConfig": {
                "temperature": 0.4, # TODO: Consider making these configurable
                "top_p": 1,
                "top_k": 32,
                "responseModalities": ["Text", "Image"] # Expect both back
            }
        }
        
        # Add safety settings if provided
        if safety_settings:
            data["safetySettings"] = safety_settings
        
        # Attempt with primary model
        url = self.get_api_url(self.model)
        try:
            response = self.make_request(url, data)
            images = self._extract_images_from_response(response)
            if images:
                logger.info(f"Successfully generated image using primary model: {self.model}")
                return images
            
            # If primary model fails or returns no valid image, try fallback
            logger.warning(f"Primary model ({self.model}) failed to return a valid image. Trying fallback: {self.fallback_model}")
            url = self.get_api_url(self.fallback_model)
            
            # Ensure fallback request still has the correct parts and config
            # (Data dict is already prepared correctly above)
            response = self.make_request(url, data)
            images = self._extract_images_from_response(response)
            if images:
                 logger.info(f"Successfully generated image using fallback model: {self.fallback_model}")
                 return images
            else:
                logger.error(f"Fallback model ({self.fallback_model}) also failed to return a valid image.")
                return None # Return None if both fail
            
        except Exception as e:
            logger.error(f"Image generation failed critically: {str(e)}")
            # Optionally, re-raise the exception if needed upstream
            # raise e 
            return None # Return None on critical failure

    def _extract_images_from_response(self, response: Optional[Dict[str, Any]]) -> Optional[List[str]]:
        """Extracts base64 image data from the API response."""
        if not response or 'candidates' not in response:
            logger.warning("No candidates found in image generation response.")
            return None
            
        images = []
        for candidate in response['candidates']:
            content = candidate.get('content', {})
            for part in content.get('parts', []):
                if 'inlineData' in part and part['inlineData'].get('mimeType', '').startswith('image/'):
                    image_data = part['inlineData'].get('data')
                    if image_data and isinstance(image_data, str) and len(image_data) > 100: # Basic check for non-empty image data
                        images.append(image_data)
                    else:
                        logger.warning(f"Found image part but data seems invalid or empty. MimeType: {part['inlineData'].get('mimeType')}, Data Length: {len(image_data) if image_data else 0}")

        if not images:
            logger.warning("No valid image data found in any response candidates.")
            return None
            
        logger.debug(f"Extracted {len(images)} valid image(s) from response.")
        return images

    # Renamed from _has_valid_image to reflect it now extracts data
    # def _has_valid_image(self, response: Dict[str, Any]) -> bool: ... (Old function removed) 