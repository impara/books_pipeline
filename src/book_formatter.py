import os
from pathlib import Path
from typing import Dict, List, Optional
from loguru import logger
from PIL import Image
import reportlab
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import html2text
from datetime import datetime

class BookFormatter:
    """Handles different book formats and their generation."""
    
    def __init__(self, 
                 output_dir: Path, 
                 book_config: dict,
                 characters_config: dict,
                 print_settings: dict,
                 metadata_config: dict,
                 cover_config: dict,
                 output_formats_config: dict):
        """Initialize the book formatter with specific configs."""
        self.output_dir = output_dir
        # Store specific configs
        self.book_config = book_config
        self.characters_config = characters_config
        self.print_settings = print_settings
        self.metadata_config = metadata_config
        self.cover_config = cover_config
        self.output_formats_config = output_formats_config # Store output formats config
        
        self.processed_dir = output_dir / "processed_book"
        self.processed_dir.mkdir(exist_ok=True)
        
        # Register fonts for PDF generation
        self._register_fonts()
    
    def _register_fonts(self):
        """Register fonts for PDF generation."""
        fonts_dir = Path("assets/fonts")
        if fonts_dir.exists():
            for font_file in fonts_dir.glob("*.ttf"):
                try:
                    font_name = font_file.stem
                    pdfmetrics.registerFont(TTFont(font_name, str(font_file)))
                except Exception as e:
                    logger.warning(f"Could not register font {font_file}: {e}")
    
    def create_html_book(self) -> Path:
        """Create an HTML version of the book.
        
        Returns:
            Path to the generated HTML file
        """
        html_file = self.processed_dir / "book.html"
        
        html_content = """<!DOCTYPE html>
<html>
<head>
    <title>%s</title>
    <style>
        body { font-family: "Arial", sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        .page { margin-bottom: 30px; page-break-after: always; }
        .page-number { text-align: center; font-size: 12px; color: #888; margin-top: 10px; }
        img { max-width: 100%%; display: block; margin: 20px auto; border-radius: 5px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
        .text { font-size: 18px; line-height: 1.6; margin: 20px 0; }
        @media print {
            .page { page-break-after: always; }
            body { margin: 0; padding: 0; }
        }
    </style>
</head>
<body>""" % self.book_config['title']
        
        # Add cover page
        html_content += f"""
    <div class="page cover">
        <h1 style="text-align:center;margin-top:100px;font-size:32px;">{self.book_config['title']}</h1>
        <div style="text-align:center;margin-top:20px;font-style:italic;">Generated by Amer-DK</div>
        <div style="text-align:center;margin-top:80px;">
            <p>A story about {self.characters_config['main_character']['name']} and {self.characters_config['supporting_character']['name']}</p>
        </div>
    </div>"""
        
        # Add each page
        for page_num in range(1, self.book_config['page_count'] + 1):
            story_text_file = self.output_dir / f"page_{page_num:02d}" / "story_text.txt"
            image_file_rel = f"page_{page_num:02d}.png"
            
            if story_text_file.exists():
                with open(story_text_file, 'r') as f:
                    story_text = f.read().strip()
            else:
                story_text = f"[Text for page {page_num} not available]"
            
            html_content += f"""
    <div class="page">
        <div class="text">{story_text}</div>
        <img src="{image_file_rel}" alt="Illustration for page {page_num}">
        <div class="page-number">{page_num}</div>
    </div>"""
        
        # Close HTML
        html_content += """
</body>
</html>"""
        
        with open(html_file, 'w') as f:
            f.write(html_content)
            
        logger.info(f"Created HTML book file at {html_file}")
        return html_file
    
    def create_pdf_book(self) -> Path:
        """Create a PDF version of the book, formatted for KDP."""
        
        # --- Read Print Settings --- #
        print_settings = self.print_settings
        trim_w = print_settings.get('trim_width', 6.0)
        trim_h = print_settings.get('trim_height', 9.0)
        unit = print_settings.get('unit', 'inch').lower()
        has_bleed = print_settings.get('has_bleed', False)
        bleed = print_settings.get('bleed_amount', 0.125) if has_bleed else 0.0
        target_dpi = print_settings.get('target_dpi', 300)

        # Convert dimensions to points (ReportLab unit)
        units = {'inch': inch, 'mm': 2.83465} # Conversion factors
        if unit not in units:
            logger.warning(f"Unsupported unit '{unit}'. Defaulting to inches.")
            unit_factor = inch
        else:
            unit_factor = units[unit]
            
        trim_w_pts = trim_w * unit_factor
        trim_h_pts = trim_h * unit_factor
        bleed_pts = bleed * unit_factor
        
        # Calculate final page size including bleed
        page_w_pts = trim_w_pts + (2 * bleed_pts)
        page_h_pts = trim_h_pts + (2 * bleed_pts)
        page_size = (page_w_pts, page_h_pts)
        
        logger.info(f"PDF Settings: Trim={trim_w}x{trim_h} {unit}, Bleed={bleed} {unit}, PageSize={page_w_pts:.2f}x{page_h_pts:.2f} pts")

        # --- Initialize PDF --- #
        pdf_file = self.processed_dir / "book_kdp.pdf" # New name to avoid overwriting old one
        c = canvas.Canvas(str(pdf_file), pagesize=page_size)
        
        # --- Read and Set Metadata (Keep existing logic) --- #
        meta = self.metadata_config
        book_details = self.book_config
        cover_config = self.cover_config
        book_title = book_details.get('title', 'Generated Book')
        author = meta.get('author') or cover_config.get('cover_author') or 'Generated by AI'
        keywords = meta.get('keywords', '')
        subject_text = f"{book_title}. Keywords: {keywords}"
        c.setTitle(book_title)
        c.setAuthor(author)
        c.setSubject(subject_text)
        logger.info("Set basic PDF metadata (Title, Author, Subject).")
        # --- End Metadata --- #

        # --- Handle Cover (KDP Requires Separate Cover PDF) --- #
        logger.info("Skipping cover page embedding in manuscript PDF (KDP requires separate cover file).")

        # --- Calculate Margins in Points --- #
        margin_top_pts = print_settings.get('margin_top', 0.5) * unit_factor
        margin_bottom_pts = print_settings.get('margin_bottom', 0.5) * unit_factor
        margin_inside_pts = print_settings.get('margin_inside', 0.75) * unit_factor
        margin_outside_pts = print_settings.get('margin_outside', 0.5) * unit_factor

        # --- Add each story page --- #
        total_pages = self.book_config['page_count']
        for page_num in range(1, total_pages + 1):
            
            # --- Determine Page-Specific Margins --- #
            is_odd_page = (page_num % 2 != 0)
            if is_odd_page:
                # Right-hand page (odd)
                margin_left_pts = margin_outside_pts
                margin_right_pts = margin_inside_pts
            else:
                # Left-hand page (even)
                margin_left_pts = margin_inside_pts
                margin_right_pts = margin_outside_pts
            
            # Define content box (area within margins relative to trim box)
            # Note: Coordinates are from bottom-left
            content_x_start_pts = bleed_pts + margin_left_pts 
            content_y_start_pts = bleed_pts + margin_bottom_pts
            content_w_pts = trim_w_pts - margin_left_pts - margin_right_pts
            content_h_pts = trim_h_pts - margin_top_pts - margin_bottom_pts
            content_x_end_pts = content_x_start_pts + content_w_pts
            content_y_end_pts = content_y_start_pts + content_h_pts

            # --- Get Page Content --- #
            story_text_file = self.output_dir / f"page_{page_num:02d}" / "story_text.txt"
            image_file = self.processed_dir / f"page_{page_num:02d}.png" # Use the overlayed image
            
            story_text = f"[Text for page {page_num} not available]"
            if story_text_file.exists():
                with open(story_text_file, 'r') as f:
                    story_text = f.read().strip()
            
            # --- Draw Text (within content box) --- # 
            # TODO: Implement text flow within the content box (content_x_start_pts, content_y_start_pts, content_w_pts, content_h_pts)
            # This requires more complex text flow logic than just beginText/textLines if text is long.
            # For simplicity now, just place it near the top of the content box.
            c.setFont("Helvetica", 12) # TODO: Make font/size configurable?
            text_object = c.beginText(content_x_start_pts, content_y_end_pts - 12) # Start near top-left of content box
            # Basic wrapping attempt (might need improvement with Paragraph)
            available_width = content_w_pts
            lines = self._simple_text_wrap(story_text, c._fontname, c._fontsize, available_width)
            for line in lines:
                text_object.textLine(line)
            # text_object.textLines(story_text) # Old method - no wrapping
            c.drawText(text_object)
            
            # --- Draw Image --- #
            if image_file.exists():
                try:
                    # Draw image, handling bleed
                    self._draw_page_image_kdp(
                        c,
                        str(image_file),
                        page_w_pts,
                        page_h_pts,
                        bleed_pts,
                        has_bleed,
                        target_dpi,
                        content_x_start_pts, 
                        content_y_start_pts,
                        content_w_pts,
                        content_h_pts
                    )
                except Exception as e:
                    logger.error(f"Error drawing image for page {page_num}: {e}")
            
            # --- Add Page Number (within bottom margin) --- # 
            page_num_y = bleed_pts + (margin_bottom_pts / 2)
            c.setFont("Helvetica", 9)
            if is_odd_page:
                c.drawRightString(page_w_pts - bleed_pts - margin_right_pts, page_num_y, str(page_num))
            else:
                c.drawString(bleed_pts + margin_left_pts, page_num_y, str(page_num))
            
            c.showPage()
        
        c.save()
        logger.info(f"Created KDP PDF book file at {pdf_file}")
        return pdf_file

    def _simple_text_wrap(self, text: str, font_name: str, font_size: int, max_width: float) -> List[str]:
        """Very basic text wrapper based on character estimate."""
        # This is rudimentary. ReportLab's Paragraph is much better.
        avg_char_width = font_size * 0.5 # Rough estimate
        chars_per_line = int(max_width / avg_char_width) if avg_char_width > 0 else 50
        
        lines = []
        words = text.split()
        current_line = ""
        for word in words:
            if not current_line:
                current_line = word
            else:
                test_line = current_line + " " + word
                # Estimate length - again, very rough
                if len(test_line) <= chars_per_line:
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = word
        if current_line:
            lines.append(current_line)
        return lines

    def _draw_page_image_kdp(self, c, image_path, page_w_pts, page_h_pts, bleed_pts, has_bleed, target_dpi, cx, cy, cw, ch):
        """Draws the page image, handling bleed and scaling for KDP."""
        img = Image.open(image_path)
        img_w_px, img_h_px = img.size
        
        # Check source image resolution against target
        # For full bleed, image needs to cover page_w_pts x page_h_pts at target_dpi
        required_w_px = (page_w_pts / inch) * target_dpi
        required_h_px = (page_h_pts / inch) * target_dpi
        
        if has_bleed and (img_w_px < required_w_px or img_h_px < required_h_px):
            logger.warning(f"Image {os.path.basename(image_path)} ({img_w_px}x{img_h_px}px) may be too small for full bleed at {target_dpi} DPI (needs ~{int(required_w_px)}x{int(required_h_px)}px). Quality may suffer.")
        
        # Determine target drawing area and position
        if has_bleed:
            # Image covers the entire page including bleed area
            target_x = 0
            target_y = 0
            target_w = page_w_pts
            target_h = page_h_pts
        else:
            # Image fits within the content box (margins)
            target_x = cx
            target_y = cy 
            target_w = cw
            target_h = ch
            # Check resolution for non-bleed image size
            required_w_px_nb = (target_w / inch) * target_dpi
            required_h_px_nb = (target_h / inch) * target_dpi
            if img_w_px < required_w_px_nb or img_h_px < required_h_px_nb:
                 logger.warning(f"Image {os.path.basename(image_path)} ({img_w_px}x{img_h_px}px) may be too small for target print size within margins at {target_dpi} DPI (needs ~{int(required_w_px_nb)}x{int(required_h_px_nb)}px). Quality may suffer.")

        # Draw the image using reportlab's drawImage
        # preserveAspectRatio=False + anchor='c' + mask='auto' might achieve cover/fill scaling if needed,
        # but default scaling (preserveAspectRatio=True) is usually safer.
        # Let's scale to fit the target area while preserving aspect ratio.
        c.drawImage(
            image_path, 
            target_x, 
            target_y, 
            width=target_w, 
            height=target_h, 
            preserveAspectRatio=True, 
            anchor='c' # Center the image within the target box
        )

    def create_epub_book(self) -> Path:
        """Create an EPUB version of the book.
        
        Returns:
            Path to the generated EPUB file
        """
        epub_file = self.processed_dir / "book.epub"
        book = epub.EpubBook()
        
        # --- Read and Set Metadata --- #
        meta = self.metadata_config
        book_details = self.book_config
        cover_config = self.cover_config
        
        book_title = book_details.get('title', 'Generated Book')
        # Use metadata author, fallback to cover author, then default
        author = meta.get('author') or cover_config.get('cover_author') or 'Generated by AI'
        language = meta.get('language', 'en')
        publisher = meta.get('publisher', 'Self-Published')
        isbn = meta.get('isbn', '')
        description = meta.get('description', '')
        keywords = [k.strip() for k in meta.get('keywords', '').split(',') if k.strip()]
        pub_year = meta.get('publication_year') or datetime.now().year
        rights = meta.get('rights', f'Copyright © {pub_year} {author}')

        # Set core metadata
        book.set_identifier(f"urn:uuid:{self.output_dir.name}_{book_title.lower().replace(' ', '_')}") # Unique ID
        book.set_title(book_title)
        book.set_language(language)
        book.add_author(author)
        book.add_metadata('DC', 'publisher', publisher)
        book.add_metadata('DC', 'description', description)
        book.add_metadata('DC', 'rights', rights)
        book.add_metadata('DC', 'date', str(pub_year), {'event': 'publication'})
        
        # Add ISBN if provided
        if isbn:
            book.set_identifier(f'urn:isbn:{isbn}') # Also set as primary identifier if available
            book.add_metadata('DC', 'identifier', isbn, {'scheme': 'ISBN'})
        
        # Add keywords/subjects
        for keyword in keywords:
            book.add_metadata('DC', 'subject', keyword)
        
        # --- End Metadata --- #

        # Initialize chapters list and spine
        chapters = []
        book.spine = ['nav'] # Start spine with nav

        # Check for and add generated cover image
        cover_image_path = self.output_dir / "cover_final.png"
        if cover_image_path.exists():
            try:
                with open(cover_image_path, 'rb') as f:
                    cover_content = f.read()
                # Use a standard name like cover.png or cover.jpg internally in the EPUB
                cover_ext = cover_image_path.suffix.lstrip('.') # e.g., 'png'
                cover_item_name = f'cover.{cover_ext}'
                book.set_cover(cover_item_name, cover_content, create_page=False) # create_page=False avoids auto HTML page
                logger.info("Added generated cover image to EPUB.")
                # Although set_cover adds it, we might need it in the spine explicitly for some readers
                # Let ebooklib handle the spine logic related to the cover for now.
            except Exception as e:
                logger.error(f"Failed to add cover image {cover_image_path} to EPUB: {e}. Skipping cover image.")
        else:
            logger.warning("Cover image file not found for EPUB.")
            # Optionally, add a simple text title page if no cover image
            title_html = f'''<html><head><title>Title</title></head><body><h1>{self.book_config["title"]}</h1><p>{author}</p></body></html>'''
            title_page = epub.EpubHtml(title='Title Page', file_name='title.xhtml', content=title_html)
            book.add_item(title_page)
            chapters.append(title_page) # Add to content list
            book.spine.append(title_page) # Add to spine

        # Add page images to the book items first
        page_images = []
        for page_num in range(1, self.book_config['page_count'] + 1):
            image_file = self.processed_dir / f"page_{page_num:02d}.png"
            if image_file.exists():
                try:
                    with open(image_file, 'rb') as f:
                        image_content = f.read()
                    img_item_name = f'images/page_{page_num:02d}.png'
                    epub_image = epub.EpubImage(uid=f'img_{page_num}', file_name=img_item_name, media_type='image/png', content=image_content)
                    book.add_item(epub_image)
                    page_images.append(img_item_name) # Keep track of the item name
                except Exception as e:
                    logger.warning(f"Failed to add page image {image_file} to EPUB: {e}")
            else:
                 page_images.append(None) # Placeholder if image is missing

        # Add each page content (HTML chapter referencing the image)
        for page_num in range(1, self.book_config['page_count'] + 1):
            story_text_file = self.output_dir / f"page_{page_num:02d}" / "story_text.txt"
            
            if story_text_file.exists():
                with open(story_text_file, 'r') as f:
                    story_text = f.read().strip()
            else:
                story_text = f"[Text for page {page_num} not available]"
            
            # Get corresponding image item name
            img_item_name = page_images[page_num-1] if page_num <= len(page_images) else None
            img_tag = f'<img src="{img_item_name}" alt="Illustration for page {page_num}"/>' if img_item_name else "<!-- Image not available -->"

            # Create chapter HTML containing only the image
            chapter_html = f"""
            <?xml version='1.0' encoding='utf-8'?>
            <!DOCTYPE html>
            <html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
            <head>
                <title>Page {page_num}</title>
                <style>
                    /* Basic styling for image-only pages */
                    body {{ margin: 0; padding: 0; }}
                    img {{ display: block; max-width: 100%; max-height: 98vh; margin: auto; /* Centered, fills most of the view height */ }}
                </style>
            </head>
            <body>
                {img_tag}
                <!-- Text paragraph removed as text is overlaid on the image -->
                <!-- Page number can be added if desired, but often omitted in picture books -->
                <!-- <div style="text-align: center; font-size: 0.8em; color: #888;">{page_num}</div> -->
            </body>
            </html>
            """
            
            # Use first few words of text for a more meaningful TOC title
            toc_title = ' '.join(story_text.split()[:5]) + '...' if story_text else f'Page {page_num}'
            chapter = epub.EpubHtml(title=toc_title, file_name=f'page_{page_num:02d}.xhtml', content=chapter_html, lang='en')
            book.add_item(chapter)
            chapters.append(chapter)
            book.spine.append(chapter) # Add chapter to spine
        
        # Define Table of Contents using the generated chapters with better titles
        book.toc = chapters
        
        # Add default NCX and Nav file
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        
        # Define CSS style
        style = 'BODY {color: black;}'
        nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style)
        book.add_item(nav_css)
        
        # Set the spine order (cover handled by set_cover, nav, then pages)
        # book.spine = ['nav'] + chapters # Let ebooklib handle cover placement
        
        # Write the EPUB file
        epub.write_epub(epub_file, book, {})
        logger.info(f"Created EPUB book file at {epub_file}")
        return epub_file
    
    def create_text_book(self) -> Path:
        """Create a text-only version of the book.
        
        Returns:
            Path to the generated text file
        """
        text_file = self.processed_dir / "full_story.txt"
        text_content = f"# {self.book_config['title']}\n\n"
        
        for page_num in range(1, self.book_config['page_count'] + 1):
            story_text_file = self.output_dir / f"page_{page_num:02d}" / "story_text.txt"
            
            if story_text_file.exists():
                with open(story_text_file, 'r') as f:
                    story_text = f.read().strip()
            else:
                story_text = f"[Text for page {page_num} not available]"
            
            text_content += f"\n## Page {page_num}\n\n{story_text}\n"
        
        with open(text_file, 'w') as f:
            f.write(text_content)
            
        logger.info(f"Created full story text file at {text_file}")
        return text_file

    @staticmethod
    def calculate_and_log_spine_width(config: Dict):
        """Calculates and logs the KDP spine width based on config."""
        page_count = config.get('book', {}).get('page_count', 0)
        print_settings = config.get('print_settings', {})
        paper_type = print_settings.get('paper_type', 'white').lower()
        unit = print_settings.get('unit', 'inch').lower()

        spine_mult = 0.0 # Multiplier in inches
        if paper_type == "white":
            spine_mult = 0.002252
        elif paper_type == "cream":
            spine_mult = 0.0025
        elif paper_type == "color":
            spine_mult = 0.002347
        else:
            logger.warning(f"Unknown paper type '{paper_type}'. Using 'white' for spine calculation.")
            spine_mult = 0.002252

        spine_width_inch = page_count * spine_mult
        
        # Convert to configured unit if not inches
        spine_width = spine_width_inch
        unit_label = "inches"
        if unit == 'mm':
            spine_width = spine_width_inch * 25.4
            unit_label = "mm"
        elif unit != 'inch':
             logger.warning(f"Spine width calculation assumes inches or mm. Outputting in inches due to unknown unit: {unit}")
             unit_label = "inches"
             spine_width = spine_width_inch # Default back to inches
            
        logger.info(f"--- KDP Print Cover Info (for Cover Creator Tool) ---")
        logger.info(f"Page Count: {page_count}")
        logger.info(f"Paper Type: {paper_type}")
        logger.info(f"==> Calculated Spine Width: {spine_width:.4f} {unit_label}")
        if page_count < 80: # KDP minimum for spine text
             logger.info("    (Note: Spine text is not supported by KDP for books under 80 pages.)")
        logger.info(f"---------------------------------------------------------")
        return spine_width
    
    def create_all_formats(self) -> Dict[str, Path]:
        """Generate all selected output formats for the book.
        
        Returns:
            Dictionary mapping format names to their file paths
        """
        formats = {}
        # Use the specific output_formats_config attribute
        output_config = self.output_formats_config
  
        try:
            if output_config.get('html', False):
                formats['html'] = self.create_html_book()
            if output_config.get('pdf', False):
                formats['pdf'] = self.create_pdf_book()
            if output_config.get('epub', False):
                formats['epub'] = self.create_epub_book()
            if output_config.get('text', False):
                formats['text'] = self.create_text_book()
        except Exception as e:
            logger.error(f"Error creating requested book formats: {e}")
            raise
        
        return formats 