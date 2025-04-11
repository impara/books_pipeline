# Product Context

## Problem Domain

The core problem this project addresses is the time-consuming and potentially costly process of creating illustrated children's books. It aims to automate the generation of both the story text and corresponding illustrations.

## Functionality

- **Automated Content Generation:** Utilizes Google's Gemini AI model to generate age-appropriate story text and illustrations based on user-defined parameters.
- **Configurable Parameters:** Allows users to specify various aspects of the book, including:
  - Target age range
  - Book theme and title
  - Character descriptions and appearance rules
  - Desired art style
  - Number of pages
- **Text Overlay:** Implements a system to overlay the generated text directly onto the illustrations, ensuring consistent typography and visual integration. Text position is configurable (top, middle, bottom).
- **Multiple Output Formats:** Generates the final book in several standard formats:
  - PDF (with professional typesetting)
  - EPUB (for e-readers)
  - HTML (for web viewing)
  - Plain Text (for accessibility)
- **Pipeline Management:**
  - **Scene Management:** Ensures consistency in characters and settings across different scenes/pages (managed by `src/scene_manager.py`).
  - **Transition Management:** Helps create smooth narrative transitions between pages (managed by `src/transition_manager.py`).
  - **Checkpointing:** Saves generation progress, allowing users to resume or recover from interruptions (managed by `src/checkpoint_manager.py`).
  - **Error Handling:** Includes mechanisms to handle potential errors during API calls or processing, including retry logic for rate limits (part of `src/generate_book.py` and `src/api_client.py`).
  - **Page Regeneration:** Allows users to regenerate specific pages if needed (handled in `src/generate_book.py`).
- **Structured Output:** Organizes generated assets (original images, text-overlaid images, story text per page, final book formats, logs) into a clear directory structure.

## Intended Users

The primary users are likely developers, content creators, or individuals interested in quickly generating custom children's books using AI, potentially for prototyping, personal use, or small-scale publishing.
