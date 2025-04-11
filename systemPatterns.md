# System Patterns

## Architecture

The system employs a **Monolithic Script-Based Pipeline** architecture. The core logic is orchestrated primarily within the `generate_book.py` script, which executes a sequence of tasks to generate the book. Dependency Injection is used to provide manager instances to the main `BookGenerator` class.

## Key Components & Modules

- **`src/generate_book.py`**: Main entry point and orchestrator. Initializes and injects manager dependencies (`APIClient`, `SceneManager`, `PromptManager`, etc.) into the `BookGenerator` class. The `BookGenerator` then coordinates the pipeline steps by calling methods on these managers.
- **`src/prompt_manager.py`**: Constructs the detailed prompts sent to the Gemini API for text, image, and backup text generation. Incorporates context, configuration, scene requirements, and reference image guidance (obtained via `TransitionManager`) into prompts.
- **`src/image_processor.py`**: Handles the processing of generated images (decoding, resizing, saving variations).
- **`src/api_client.py`**: Handles all communication with the external Google Gemini API. It also processes API responses to extract relevant content, such as the main story text from text generation calls.
- **`src/text_overlay_manager.py`**: Responsible for applying generated text onto the processed images using specified fonts and positioning.
- **`src/scene_manager.py`**: Manages rules and consistency for characters and scenes. Determines required characters for a page and finds the optimal reference image page number based on context and available image files.
- **`src/transition_manager.py`**: Focuses on generating guidance for smooth visual transitions between consecutive pages, used by `PromptManager` when incorporating reference images.
- **`src/book_formatter.py`**: Takes the generated assets (text, images) and formats them into various output files (PDF, EPUB, HTML, TXT).
- **`src/checkpoint_manager.py`**: Implements the saving and loading of generation progress to allow for resumption.
- **`config.yaml`**: Central configuration file defining book parameters, API settings, and other options.

## Design Patterns

- **Dependency Injection:** Key manager components (`APIClient`, `SceneManager`, `PromptManager`, etc.) are instantiated separately and passed into the `BookGenerator` constructor, promoting loose coupling and testability.
- **Manager Pattern:** Several components (`prompt_manager`, `image_processor` (functionally), `text_overlay_manager`, `scene_manager`, `transition_manager`, `checkpoint_manager`) encapsulate specific areas of responsibility, promoting modularity and separation of concerns. `generate_book.py` acts as the primary coordinator.
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
