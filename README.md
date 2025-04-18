# AI Children's Book Generation Pipeline

This project uses Google's Gemini 2.0 Flash Experimental model to automatically generate children's books with text and illustrations. The text is applied as an overlay on the generated images, ensuring consistent typography and layout.

## Features

- High-quality image generation using Gemini 2.0
- Separate text overlay system for consistent typography
- Multiple output formats supported:
  - PDF with professional typesetting
  - EPUB for e-readers
  - HTML for web viewing
  - Plain text for accessibility
- Configurable book parameters (age range, theme, characters, etc.)
- Structured output organization
- Scene transition management for story coherence
- Comprehensive logging and checkpoint system
- Error handling and retry mechanisms
- Support for regenerating specific pages
- Flexible text overlay positioning (top, middle, bottom)

## Prerequisites

- Python 3.8 or higher
- Gemini API key
- Required Python packages (installed via pip):
  - google-generativeai>=0.3.0
  - pyyaml>=6.0.1
  - python-dotenv>=1.0.0
  - loguru>=0.7.2
  - pillow>=10.0.0
  - requests>=2.31.0
  - reportlab>=4.0.4
  - ebooklib>=0.18
  - beautifulsoup4>=4.12.2
  - html2text>=2020.1.16

## Setup

1. Clone this repository:

```bash
git clone <repository-url>
cd books_pipeline
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set up your Gemini API key:
   - Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

- Edit the `.env` file and replace `your_api_key_here` with your actual Gemini API key

Alternatively, you can set the API key directly in `config.yaml`

4. Configure your book parameters:
   - Edit `config.yaml` with your desired book settings

## Usage

1. Run the book generation script:

```bash
python -m src.generate_book
```

2. The script will:

   - Create a unique output directory with timestamp
   - Generate illustrations for each page
   - Apply text overlays to the images
   - Create multiple book formats (PDF, EPUB, HTML, text)
   - Save all outputs in organized directories
   - Create a log file with generation details

3. Find your generated book in the `outputs` directory:
   - Original text-free images in `page_XX/image_original_1.png`
   - Images with text overlay in `page_XX/image_1.png`
   - Processed book formats in `processed_book/`:
     - `book.pdf` - PDF version with professional typesetting
     - `book.epub` - EPUB version for e-readers
     - `book.html` - Web-friendly HTML version
     - `book.txt` - Plain text version
   - Story text in `page_XX/story_text.txt`
   - Log file: `generation.log`

### Additional Commands

- Regenerate specific pages:

```bash
python -m src.generate_book --regenerate 1,2,3
```

- Apply text overlay to existing images:

```bash
python -m src.generate_book --apply-text [position] [page]
```

- `position` can be "top", "middle", or "bottom" (default: bottom)
- `page` is optional (default: all pages)

- Auto-retry on rate limits:

```bash
python -m src.generate_book --retry
```

## Configuration

Edit `config.yaml` to customize:

- Book title and theme
- Target age range
- Character descriptions and appearance rules
- Art style
- Page count
- API settings
- Image dimensions
- Output format preferences

## Project Structure

- `src/`: Contains all the core Python modules.
  - `__init__.py`: Marks the directory as a Python package.
  - `generate_book.py`: Main script orchestrating the book generation pipeline via the `BookGenerator` class, utilizing injected managers.
  - `prompt_manager.py`: Manages the construction of prompts for AI text, image, and backup text generation, incorporating reference image guidance.
  - `image_processor.py`: Handles image decoding, resizing, saving, and text overlay preparation.
  - `text_overlay_manager.py`: Handles applying text overlays onto images.
  - `scene_manager.py`: Manages scene consistency, character rules, and finding reference image pages.
  - `transition_manager.py`: Provides guidance for smooth story transitions between pages, used by `PromptManager`.
  - `book_formatter.py`: Generates different book formats (PDF, EPUB, HTML).
  - `api_client.py`: Handles API communication with Gemini and extracts story text from responses.
  - `checkpoint_manager.py`: Handles saving and loading generation progress.
- `config.yaml`: Configuration file for the book and API settings.
- `assets/fonts/`: Directory for required fonts.
- `outputs/`: Contains all generated content.
  - `page_XX/`: Individual page directories.
  - `processed_book/`: Final processed book in multiple formats.
- `checkpoints/`: Stores generation checkpoints for recovery.
- `requirements.txt`: Lists Python dependencies.
- `.env`: Environment variables (API key).
- `README.md`: This file.

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is licensed under the MIT License - see the LICENSE file for details.
