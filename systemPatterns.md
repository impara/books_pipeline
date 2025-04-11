# System Patterns

## Architecture

The system employs a **Monolithic Script-Based Pipeline** architecture. The core logic is orchestrated primarily within the `generate_book.py` script, which executes a sequence of tasks to generate the book.

## Key Components & Modules

- **`src/generate_book.py`**: Main entry point and orchestrator of the generation pipeline. Delegates tasks to various managers.
- **`src/prompt_manager.py`**: Constructs the detailed prompts sent to the Gemini API for both text and image generation, based on configuration and context.
- **`src/image_processor.py`**: Handles the processing of generated images (decoding, resizing, saving variations).
- **`src/api_client.py`**: Handles all communication with the external Google Gemini API for text and image generation.
- **`src/text_overlay_manager.py`**: Responsible for applying generated text onto the processed images using specified fonts and positioning.
- **`src/scene_manager.py`**: Manages rules and consistency for characters and scenes across the book's pages.
- **`src/transition_manager.py`**: Focuses on generating guidance for smooth visual transitions between consecutive pages, especially when environments change.
- **`src/book_formatter.py`**: Takes the generated assets (text, images) and formats them into various output files (PDF, EPUB, HTML, TXT).
- **`src/checkpoint_manager.py`**: Implements the saving and loading of generation progress to allow for resumption.
- **`config.yaml`**: Central configuration file defining book parameters, API settings, and other options.

## Design Patterns

- **Manager Pattern:** Several components (`prompt_manager`, `image_processor` (functionally), `text_overlay_manager`, `scene_manager`, `transition_manager`, `checkpoint_manager`) encapsulate specific areas of responsibility, promoting modularity and separation of concerns. The `generate_book.py` script acts as the primary coordinator.
- **Configuration Pattern:** Externalizes configuration into `config.yaml`, allowing for easy customization without code changes.
- **API Client/Gateway:** `api_client.py` acts as a gateway to the external Gemini service, abstracting the details of the API interaction.
- **Procedural Pipeline:** The overall flow follows a defined sequence of steps executed by the main script, coordinated through the `BookGenerator` class.

## Technologies

- **Language:** Python (3.8+)
- **AI Model:** Google Gemini API
- **Image Processing:** Pillow
- **PDF Generation:** ReportLab
- **EPUB Generation:** EbookLib
- **HTML/Text Processing:** BeautifulSoup4, html2text
- **Configuration:** PyYAML
- **Environment Management:** python-dotenv
- **Logging:** Loguru
- **HTTP Requests:** requests
