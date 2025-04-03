import os
import requests
import platform
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from loguru import logger

class TextOverlayManager:
    def __init__(self, fonts_dir: Path, config: dict):
        """Initialize the text overlay manager with fonts directory and config."""
        self.fonts_dir = fonts_dir
        self.config = config
        self.fonts_dir.mkdir(parents=True, exist_ok=True)
        self.text_styles = self._initialize_text_styles()

    def _initialize_text_styles(self):
        """Initialize text styles for children's books."""
        styles = {
            "story": {
                "font": "assets/fonts/children_book.ttf",
                "size": 55,  # Reduced size for better fit
                "color": (16, 69, 153),  # Deep blue color
                "stroke_width": 2,  # Thinner stroke for cleaner look
                "stroke_fill": (255, 255, 255),  # White outline
                "text_area_height_factor": 0.35,  # Significantly increased height for text area
                "background_color": (255, 255, 255, 230),  # More opaque white background
                "padding": 25  # Reduced padding
            },
            "title": {
                "font": "assets/fonts/children_book.ttf",
                "size": 70,  # Slightly reduced title size
                "color": (16, 69, 153),
                "stroke_width": 2,
                "stroke_fill": (255, 255, 255),
                "text_area_height_factor": 0.35,  # Match story height
                "background_color": (255, 255, 255, 230),
                "padding": 35
            }
        }
        
        self._ensure_fonts_available()
        return styles
    
    def _ensure_fonts_available(self):
        """Make sure required fonts are available."""
        required_fonts = [
            {
                "name": "children_book.ttf",
                "url": "https://github.com/google/fonts/raw/main/ofl/comicneue/ComicNeue-Regular.ttf"  # Placeholder URL
            }
        ]
        
        for font in required_fonts:
            font_path = self.fonts_dir / font["name"]
            if not font_path.exists():
                try:
                    logger.info(f"Downloading font: {font['name']}")
                    response = requests.get(font["url"])
                    response.raise_for_status()
                    
                    with open(font_path, "wb") as f:
                        f.write(response.content)
                    
                    logger.info(f"Font downloaded successfully: {font['name']}")
                except Exception as e:
                    logger.error(f"Failed to download font {font['name']}: {str(e)}")
                    self._configure_fallback_fonts()
    
    def _configure_fallback_fonts(self):
        """Configure fallback fonts if downloads fail."""
        system = platform.system()
        
        if system == "Windows":
            default_font = "C:\\Windows\\Fonts\\comic.ttf"
        elif system == "Darwin":  # macOS
            default_font = "/Library/Fonts/Comic Sans MS.ttf"
        else:  # Linux and others
            default_font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        
        # Update all styles to use the fallback font
        for style in self.text_styles.values():
            style["font"] = default_font

    def apply_text_overlay(self, image_path, text, page_number, is_final=False, position="bottom"):
        """Apply text overlay with background panel.
        
        Args:
            image_path: Path to the image file
            text: Text to overlay
            page_number: Page number
            is_final: Whether this is the final version for the processed book
            position: Text position ("top", "middle", or "bottom", default: "bottom")
        """
        try:
            # Open the image
            image = Image.open(image_path)
            image = image.convert("RGBA")
            
            # Get image settings from config
            image_settings = self.config.get('image_settings', {})
            target_width = image_settings.get('width', 1024)
            target_height = image_settings.get('height', 1024)
            image_format = image_settings.get('format', 'RGB')
            resize_method = getattr(Image.Resampling, image_settings.get('resize_method', 'LANCZOS').upper())
            
            # Ensure image dimensions match target dimensions
            if image.size != (target_width, target_height):
                logger.warning(f"Image dimensions {image.size} don't match target dimensions ({target_width}, {target_height}). Resizing...")
                image = image.resize((target_width, target_height), resize_method)
            
            width, height = image.size
            
            # Choose style based on page type
            style_name = "title" if page_number == 1 else "story"
            style = self.text_styles[style_name]
            
            # Calculate text area dimensions
            text_area_height = int(height * style["text_area_height_factor"])
            padding = style["padding"]
            
            # Create text area canvas
            text_area = Image.new('RGBA', (width, text_area_height + padding * 2), (0, 0, 0, 0))
            draw = ImageDraw.Draw(text_area)
            
            # Load font
            font_size = int(height * (style["size"] / 1024))
            try:
                font = ImageFont.truetype(style["font"], font_size)
            except Exception as e:
                logger.warning(f"Could not load font {style['font']}, using default")
                font = ImageFont.load_default()
            
            # Calculate Panel/Wrapping Width
            panel_margin = int(width * 0.1)  # Increased margin for better fit
            panel_width = width - (panel_margin * 2)
            max_wrap_width = panel_width - (padding * 2)
            
            # Add Text Wrapping
            wrapped_text = self._wrap_text(text, font, max_wrap_width)
            
            # Calculate Background Panel Dimensions
            text_height = 0
            line_spacing = font.size * 0.3  # Reduced line spacing
            max_line_width = 0
            
            # Pre-calculate text dimensions
            lines = wrapped_text.split('\\n')
            for line in lines:
                try:
                    bbox = font.getbbox(line)
                    text_height += (bbox[3] - bbox[1]) + line_spacing
                    max_line_width = max(max_line_width, bbox[2] - bbox[0])
                except AttributeError:
                    line_size = font.getsize(line)
                    text_height += line_size[1] + line_spacing
                    max_line_width = max(max_line_width, line_size[0])
            
            # Adjust panel dimensions
            rect_width = max_line_width + (padding * 2)
            rect_width = min(rect_width, panel_width)
            rect_height = text_height + (padding * 2)
            
            # Center the background rectangle
            rect_x = (width - rect_width) // 2
            rect_y = (text_area.height - rect_height) // 2
            
            # Draw rounded rectangle background
            radius = 20
            background_color = style["background_color"]
            self._draw_rounded_rectangle(
                draw,
                (rect_x, rect_y, rect_x + rect_width, rect_y + rect_height),
                radius,
                background_color
            )
            
            # Draw Wrapped Text
            text_x = width // 2
            current_y = rect_y + padding
            
            # Draw text with improved spacing
            for line in lines:
                try:
                    bbox = font.getbbox(line)
                    line_height = bbox[3] - bbox[1]
                except AttributeError:
                    line_height = font.getsize(line)[1]
                
                # Draw stroke
                if style["stroke_width"] > 0:
                    for dx in range(-style["stroke_width"], style["stroke_width"] + 1):
                        for dy in range(-style["stroke_width"], style["stroke_width"] + 1):
                            if dx == 0 and dy == 0:
                                continue
                            draw.text(
                                (text_x + dx, current_y + dy + line_height // 2),
                                line,
                                font=font,
                                fill=style["stroke_fill"],
                                anchor="mm"
                            )
                
                # Draw main text
                draw.text(
                    (text_x, current_y + line_height // 2),
                    line,
                    font=font,
                    fill=style["color"],
                    anchor="mm"
                )
                
                current_y += line_height + line_spacing
            
            # Create final image
            result = image.copy()
            
            # Position text area based on specified position
            if position == "top":
                paste_y = int(height * 0.02)  # Small margin from top
            elif position == "middle":
                paste_y = (height - text_area.height) // 2  # Center vertically
            else:  # bottom
                paste_y = height - text_area.height - int(height * 0.02)  # Small margin from bottom
                
            result.paste(text_area, (0, paste_y), text_area)
            
            # Convert to final format
            if image_format != "RGBA":
                result = result.convert(image_format)
            
            # Save the result
            result.save(image_path)
            logger.info(f"Applied text overlay to page {page_number} at {position}")
            
        except Exception as e:
            logger.error(f"Error applying text overlay to page {page_number}: {str(e)}")
            raise

    def _wrap_text(self, text, font, max_width):
        """Wrap text to fit within max_width."""
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            # Try adding the word to the current line
            test_line = current_line + [word]
            test_text = ' '.join(test_line)
            
            # Get width of test line
            try:
                bbox = font.getbbox(test_text)
                line_width = bbox[2] - bbox[0]
            except AttributeError:
                line_width = font.getsize(test_text)[0]
            
            if line_width <= max_width:
                # Word fits, add it to the current line
                current_line = test_line
            else:
                # Word doesn't fit, start a new line
                if current_line:  # Only append if we have words
                    lines.append(' '.join(current_line))
                current_line = [word]
        
        # Add the last line if there are words remaining
        if current_line:
            lines.append(' '.join(current_line))
        
        # Join lines with newline character
        return '\\n'.join(lines)

    def _draw_rounded_rectangle(self, draw, rect, radius, color):
        """Draw a rounded rectangle."""
        x1, y1, x2, y2 = rect
        width = x2 - x1
        height = y2 - y1
        
        # Ensure radius doesn't exceed half the width or height
        radius = min(radius, width // 2, height // 2)
        
        # Draw the rectangle
        draw.rectangle((x1 + radius, y1, x2 - radius, y2), fill=color)
        draw.rectangle((x1, y1 + radius, x2, y2 - radius), fill=color)
        
        # Draw the four corner arcs
        draw.pieslice((x1, y1, x1 + radius * 2, y1 + radius * 2), 180, 270, fill=color)
        draw.pieslice((x2 - radius * 2, y1, x2, y1 + radius * 2), 270, 360, fill=color)
        draw.pieslice((x1, y2 - radius * 2, x1 + radius * 2, y2), 90, 180, fill=color)
        draw.pieslice((x2 - radius * 2, y2 - radius * 2, x2, y2), 0, 90, fill=color) 