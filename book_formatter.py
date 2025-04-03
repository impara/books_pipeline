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

class BookFormatter:
    """Handles different book formats and their generation."""
    
    def __init__(self, output_dir: Path, config: Dict):
        """Initialize the book formatter.
        
        Args:
            output_dir: Directory containing the book pages
            config: Book configuration dictionary
        """
        self.output_dir = output_dir
        self.config = config
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
<body>""" % self.config['book']['title']
        
        # Add cover page
        html_content += f"""
    <div class="page cover">
        <h1 style="text-align:center;margin-top:100px;font-size:32px;">{self.config['book']['title']}</h1>
        <div style="text-align:center;margin-top:20px;font-style:italic;">Generated by Amer-DK</div>
        <div style="text-align:center;margin-top:80px;">
            <p>A story about {self.config['characters']['main_character']['name']} and {self.config['characters']['supporting_character']['name']}</p>
        </div>
    </div>"""
        
        # Add each page
        for page_num in range(1, self.config['book']['page_count'] + 1):
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
        """Create a PDF version of the book.
        
        Returns:
            Path to the generated PDF file
        """
        pdf_file = self.processed_dir / "book.pdf"
        c = canvas.Canvas(str(pdf_file), pagesize=letter)
        
        # Add cover page
        c.setFont("Helvetica-Bold", 24)
        c.drawCentredString(letter[0]/2, letter[1]/2 + 50, self.config['book']['title'])
        
        c.setFont("Helvetica", 12)
        c.drawCentredString(letter[0]/2, letter[1]/2, "Generated by Amer-DK")
        c.drawCentredString(letter[0]/2, letter[1]/2 - 50, 
                          f"A story about {self.config['characters']['main_character']['name']} and "
                          f"{self.config['characters']['supporting_character']['name']}")
        c.showPage()
        
        # Add each page
        for page_num in range(1, self.config['book']['page_count'] + 1):
            story_text_file = self.output_dir / f"page_{page_num:02d}" / "story_text.txt"
            image_file = self.processed_dir / f"page_{page_num:02d}.png"
            
            if story_text_file.exists():
                with open(story_text_file, 'r') as f:
                    story_text = f.read().strip()
            else:
                story_text = f"[Text for page {page_num} not available]"
            
            # Add text
            c.setFont("Helvetica", 12)
            text_width = letter[0] - 2*inch
            text_height = letter[1] - 2*inch
            text = c.beginText(inch, text_height)
            text.textLines(story_text)
            c.drawText(text)
            
            # Add image if exists
            if image_file.exists():
                img = Image.open(image_file)
                img_width, img_height = img.size
                aspect = img_height / float(img_width)
                
                # Scale image to fit page width while maintaining aspect ratio
                max_width = letter[0] - 2*inch
                max_height = letter[1] - 4*inch
                
                if aspect > max_height/max_width:
                    img_width = max_height/aspect
                    img_height = max_height
                else:
                    img_width = max_width
                    img_height = max_width * aspect
                
                c.drawImage(str(image_file), inch, inch, width=img_width, height=img_height)
            
            # Add page number
            c.setFont("Helvetica", 10)
            c.drawString(letter[0]/2, 0.5*inch, str(page_num))
            
            c.showPage()
        
        c.save()
        logger.info(f"Created PDF book file at {pdf_file}")
        return pdf_file
    
    def create_epub_book(self) -> Path:
        """Create an EPUB version of the book.
        
        Returns:
            Path to the generated EPUB file
        """
        epub_file = self.processed_dir / "book.epub"
        book = epub.EpubBook()
        
        # Set metadata
        book.set_identifier(f"id_{self.config['book']['title'].lower().replace(' ', '_')}")
        book.set_title(self.config['book']['title'])
        book.set_language('en')
        book.add_author('Amer-DK')
        
        # Create chapters
        chapters = []
        
        # Add cover page
        cover_html = f"""
        <html>
        <head>
            <title>Cover</title>
            <style>
                body {{ text-align: center; padding: 2em; }}
                h1 {{ font-size: 2em; margin-bottom: 1em; }}
                p {{ font-style: italic; }}
            </style>
        </head>
        <body>
            <h1>{self.config['book']['title']}</h1>
            <p>Generated by Amer-DK</p>
            <p>A story about {self.config['characters']['main_character']['name']} and {self.config['characters']['supporting_character']['name']}</p>
        </body>
        </html>
        """
        cover_chapter = epub.EpubHtml(title='Cover', file_name='cover.xhtml', content=cover_html)
        book.add_item(cover_chapter)
        chapters.append(cover_chapter)
        
        # Add each page
        for page_num in range(1, self.config['book']['page_count'] + 1):
            story_text_file = self.output_dir / f"page_{page_num:02d}" / "story_text.txt"
            image_file = self.processed_dir / f"page_{page_num:02d}.png"
            
            if story_text_file.exists():
                with open(story_text_file, 'r') as f:
                    story_text = f.read().strip()
            else:
                story_text = f"[Text for page {page_num} not available]"
            
            # Create chapter HTML
            chapter_html = f"""
            <html>
            <head>
                <title>Page {page_num}</title>
                <style>
                    body {{ padding: 1em; }}
                    img {{ max-width: 100%; height: auto; margin: 1em 0; }}
                    .text {{ font-size: 1.2em; line-height: 1.6; }}
                    .page-number {{ text-align: center; color: #888; margin-top: 1em; }}
                </style>
            </head>
            <body>
                <div class="text">{story_text}</div>
                <img src="images/page_{page_num:02d}.png" alt="Illustration for page {page_num}"/>
                <div class="page-number">{page_num}</div>
            </body>
            </html>
            """
            
            chapter = epub.EpubHtml(
                title=f'Page {page_num}',
                file_name=f'page_{page_num:02d}.xhtml',
                content=chapter_html
            )
            book.add_item(chapter)
            chapters.append(chapter)
            
            # Add image if exists
            if image_file.exists():
                with open(image_file, 'rb') as f:
                    img_data = f.read()
                img_item = epub.EpubItem(
                    file_name=f'images/page_{page_num:02d}.png',
                    media_type='image/png',
                    content=img_data
                )
                book.add_item(img_item)
        
        # Create table of contents
        book.toc = chapters
        
        # Add default NCX and Nav file
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        
        # Create spine
        book.spine = ['nav'] + chapters
        
        # Generate EPUB file
        epub.write_epub(str(epub_file), book)
        logger.info(f"Created EPUB book file at {epub_file}")
        return epub_file
    
    def create_text_book(self) -> Path:
        """Create a text-only version of the book.
        
        Returns:
            Path to the generated text file
        """
        text_file = self.processed_dir / "full_story.txt"
        text_content = f"# {self.config['book']['title']}\n\n"
        
        for page_num in range(1, self.config['book']['page_count'] + 1):
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
    
    def create_all_formats(self) -> Dict[str, Path]:
        """Create all supported book formats.
        
        Returns:
            Dictionary mapping format names to their file paths
        """
        formats = {}
        
        try:
            formats['html'] = self.create_html_book()
            formats['pdf'] = self.create_pdf_book()
            formats['epub'] = self.create_epub_book()
            formats['text'] = self.create_text_book()
        except Exception as e:
            logger.error(f"Error creating book formats: {e}")
            raise
        
        return formats 