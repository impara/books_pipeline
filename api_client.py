import os
import base64
import json
import requests
from loguru import logger
from typing import Dict, Any, Optional, Tuple, List
from dotenv import load_dotenv

class APIClient:
    def __init__(self, config: Dict[str, Any]):
        """Initialize the API client with configuration."""
        # Load environment variables
        load_dotenv()
        
        # Load model configuration from environment variables
        self.model = os.getenv('GEMINI_MODEL', 'gemini-2.0-flash-exp')
        self.fallback_model = os.getenv('GEMINI_FALLBACK_MODEL', 'gemini-2.0-flash-exp-image-generation')
        
        # Load debug settings from environment variables
        self.debug_enable_prompt = os.getenv('DEBUG_ENABLE_PROMPT', 'true').lower() == 'true'
        self.debug_enable_response = os.getenv('DEBUG_ENABLE_RESPONSE', 'true').lower() == 'true'
        self.debug_verbose_level = int(os.getenv('DEBUG_VERBOSE_LEVEL', '2'))
        
        # Store config for later use
        self.config = config
        
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
            import re
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
        config = self.config.get('generation', {}).get('config', {})
        
        generation_config = {
            "temperature": temperature,
            "topP": config.get('top_p', 0.9),
            "topK": config.get('top_k', 40),
            "maxOutputTokens": config.get('max_output_tokens', 8192),
        }
        
        if seed is not None:
            generation_config["seed"] = seed
        
        # Different models support different responseModalities
        model_name = self.model.lower()
        
        # Add responseModalities for models that support image generation
        if "gemini" in model_name and ("image-generation" in model_name or "-flash-exp" in model_name or "-1.5" in model_name):
            generation_config["responseModalities"] = ["Text", "Image"]
        
        return generation_config 

    def generate_story_text(self, prompt: str, conversation_history: Optional[list] = None) -> Tuple[str, bool]:
        """Generate story text using the API.
        
        Returns:
            Tuple[str, bool]: (generated_text, success)
        """
        # Use conversation history for context if available
        generation_input = conversation_history.copy() if conversation_history else []
        generation_input.append(prompt)
        
        # Prepare the request data
        data = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": self.get_generation_config()
        }
        
        # Make the API request
        url = self.get_api_url()
        response = self.make_request(url, data)
        
        # Extract text from response
        if response and 'candidates' in response and response['candidates']:
            text_content = response['candidates'][0]['content']['parts'][0]['text'].strip()
            return text_content, True
        else:
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

    def generate_image(self, prompt_text: str, safety_settings: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """Generate an image using the Gemini API.
        
        Args:
            prompt_text: The prompt text for image generation
            safety_settings: Optional safety settings for content filtering
            
        Returns:
            Dict containing the API response with base64-encoded image
        """
        # Prepare the data for the API request
        data = {
            "contents": [{
                "role": "user",
                "parts": [{
                    "text": prompt_text
                }]
            }],
            "generationConfig": {
                "temperature": 0.4,
                "top_p": 1,
                "top_k": 32,
                "responseModalities": ["Text", "Image"]  # Include both text and image modalities
            }
        }
        
        # Add safety settings if provided
        if safety_settings:
            data["safetySettings"] = safety_settings
        
        # Use the model from environment variables
        url = self.get_api_url(self.model)
        try:
            response = self.make_request(url, data)
            if self._has_valid_image(response):
                return response
            
            # If primary model fails, try fallback
            logger.info("Primary model failed to generate image, trying fallback model")
            url = self.get_api_url(self.fallback_model)
            
            # Ensure fallback request has the correct responseModalities
            data["generationConfig"]["responseModalities"] = ["Text", "Image"]
            
            return self.make_request(url, data)
            
        except Exception as e:
            logger.error(f"Image generation failed: {str(e)}")
            raise

    def _has_valid_image(self, response: Dict[str, Any]) -> bool:
        """Check if the response contains a valid image."""
        if not response or 'candidates' not in response:
            return False
            
        for candidate in response['candidates']:
            content = candidate.get('content', {})
            for part in content.get('parts', []):
                if 'inlineData' in part and part['inlineData'].get('mimeType', '').startswith('image/'):
                    if len(part['inlineData'].get('data', '')) > 0:
                        return True
        return False 