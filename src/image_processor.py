import base64
import os
from io import BytesIO
from pathlib import Path
from typing import Optional, List, Dict, Tuple

from PIL import Image
from loguru import logger

from .text_overlay_manager import TextOverlayManager # Assuming TextOverlayManager is in the same directory
from .checkpoint_manager import CheckpointManager # Assuming CheckpointManager is in the same directory

def process_and_save_images(
    image_data_list: Optional[List[str]],
    page_number: int,
    text: str,
    output_dir: Path,
    processed_dir: Path,
    # Required manager instances first
    text_overlay_manager: TextOverlayManager,
    checkpoint_manager: CheckpointManager,
    # Optional settings parameters with defaults last
    target_width: int = 1024,
    target_height: int = 1024,
    image_format: str = 'RGB',
    resize_method_name: str = 'LANCZOS',
    maintain_aspect: bool = True,
    smart_crop: bool = False,
    bg_color: str = 'white'
) -> Tuple[int, Optional[str]]:
    """
    Processes and saves images from a list of base64 encoded strings.

    Decodes images, resizes/crops according to settings, saves original
    and text-overlay versions, updates checkpoint, and returns the count
    of processed images and the path to the first original image saved.

    Args:
        image_data_list: List of base64 encoded image strings.
        page_number: The current page number.
        text: The story text to overlay on the image.
        output_dir: The main output directory Path object.
        processed_dir: The directory Path for the final processed book images.
        target_width: Target image width.
        target_height: Target image height.
        image_format: Target image format (e.g., 'RGB').
        resize_method_name: Name of the PIL resize method (e.g., 'LANCZOS').
        maintain_aspect: Whether to maintain aspect ratio (letterboxing).
        smart_crop: Whether to crop to fill dimensions if maintain_aspect is True.
        bg_color: Background color for letterboxing.
        text_overlay_manager: Instance of TextOverlayManager.
        checkpoint_manager: Instance of CheckpointManager.

    Returns:
        A tuple containing:
        - The number of images successfully processed.
        - The relative path (string) to the first original image saved, or None if no images were processed.
    """
    if not image_data_list:
        logger.warning(f"No image data list provided for page {page_number}.")
        return 0, None

    image_count = 0
    first_original_image_path_str = None
    page_dir = output_dir / f"page_{page_number:02d}"
    page_dir.mkdir(exist_ok=True)

    # Get image settings from function parameters directly
    # target_width = image_settings.get('width', 1024)
    # target_height = image_settings.get('height', 1024)
    # image_format = image_settings.get('format', 'RGB')
    try:
        # Uppercase the method name for getattr
        # resize_method_str = image_settings.get('resize_method', 'LANCZOS').upper()
        # Use the parameter directly
        resize_method = getattr(Image.Resampling, resize_method_name.upper())
    except AttributeError:
        logger.warning(f"Invalid resize_method '{resize_method_name}'. Falling back to LANCZOS.")
        resize_method = Image.Resampling.LANCZOS # Fallback to LANCZOS

    # Use parameters directly
    # maintain_aspect = image_settings.get('maintain_aspect_ratio', True)
    # smart_crop = image_settings.get('smart_crop', False)
    # bg_color = image_settings.get('background_color', 'white')

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
            processed_dir.mkdir(exist_ok=True) # Ensure processed dir exists
            processed_image_path = processed_dir / f"page_{page_number:02d}.png"
            final_img.save(processed_image_path, "PNG")

            # Store original image file path (only store the first generated image for reference)
            if image_count == 0:
                first_original_image_path_str = str(original_image_path.relative_to(output_dir)) # Store relative path
                # Update checkpoint via the passed manager
                checkpoint_manager.add_original_image_file(page_number, str(original_image_path))

            # Apply text overlay to the copies (not the original)
            text_overlay_manager.apply_text_overlay(image_with_text_path, text, page_number)
            text_overlay_manager.apply_text_overlay(processed_image_path, text, page_number, is_final=True)

            image_count += 1
            logger.info(f"Saved image {idx} for page {page_number}")

        except Exception as e:
            logger.error(f"Error processing image {idx} for page {page_number}: {str(e)}")
            continue

    if image_count == 0:
        logger.error(f"Failed to process any valid image data for page {page_number}.")

    return image_count, first_original_image_path_str
