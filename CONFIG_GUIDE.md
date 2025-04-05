# Comprehensive Guide: Configuring Your Book Generation (`config.yaml`)

This guide explains the various sections and parameters within the `config.yaml` file used by the AI Children's Book Generation Pipeline. Use this guide to understand how to customize your book generation and effectively use this file as a template for new projects.

## Overall Structure

The `config.yaml` file uses YAML syntax (a human-readable data serialization standard) to define the book's attributes, character details, story progression, scene descriptions, generation parameters, and output settings.

Key concepts:

- **Indentation Matters:** YAML uses indentation (typically 2 spaces) to define structure. Incorrect indentation will cause errors.
- **Key-Value Pairs:** Most settings are defined as `key: value`.
- **Lists:** Items starting with a hyphen (`-`) represent items in a list.
- **Comments:** Lines starting with `#` are comments and are ignored by the script.

## Core Configuration Sections

### 1. `book` - Basic Book Details

This section defines the high-level information about your book.

```yaml
book:
  title: "The Secret Meadow" # The title of the book.
  target_age_range: "4-8" # Target audience age range (e.g., "3-5", "6-8").
  theme: "Adventure and Friendship" # The main theme or topic of the story.
  page_count: 15 # Total number of pages in the book.
  art_style: "Whimsical and colorful, suitable for children" # Desired art style for illustrations (e.g., "Watercolor", "Cartoonish", "Photorealistic").
```

### 2. `image_settings` - Image Generation Parameters

Controls the technical aspects of the generated images.

```yaml
image_settings:
  # Target resolution for generated images.
  # IMPORTANT: If generating for print (e.g., KDP), calculate based on print_settings.
  # Formula: (Trim Size + Bleed) * Target DPI
  # Example (8.5" trim, 0.125" bleed, 300 DPI): (8.5 + 2*0.125) * 300 = 2625 pixels
  width: 2625
  height: 2625
  format: "RGB" # Image format (usually "RGB").
  resize_method: "lanczos" # Resizing method if needed (options: nearest, box, bilinear, hamming, bicubic, lanczos).
  maintain_aspect_ratio: true # Keep original aspect ratio, adding background color if needed.
  smart_crop: true # Attempt smart cropping to fill dimensions without empty space (if maintain_aspect_ratio is false or ratios match).
  background_color: "white" # Background color for letterboxing if needed.
```

### 3. `characters` - Character Definitions

Define each character that appears in the story. Use descriptive keys (e.g., `main_character`, `supporting_character`, `villain`).

```yaml
characters:
  main_character: # Use a meaningful key for the character
    name: "Nia" # Character's name.
    description: "..." # General description for the AI.

    # --- Appearance Rules (CRITICAL for Consistency) --- #
    # Use keywords like "Always" or "Must have" to enforce consistency.
    # These rules are heavily weighted in the image prompt.
    appearance: "Always has wavy brown hair, bright sparkling eyes..."
    outfit: "Always wears a simple yellow sundress..."
    features: "Distinctive feature: A small freckle..."

    # --- Introduction --- #
    introduction:
      page: 1 # Page number where the character first appears.
      trigger: "Nia" # Optional word in page text to confirm introduction.

    # --- Actions --- #
    # Define the character's primary action during each story phase.
    # The key (e.g., 'intro') MUST match a phase name in story_progression.phase_mapping.
    # The character will be included in the scene if an action is defined for the current phase OR an emotion for the specific page.
    actions:
      intro: "wandering through the sunlit meadow..."
      magical_encounter: "pausing as she hears a soft melody..."
      # ... other actions for other phases ...

    # --- Emotional States --- #
    # Define the character's emotion for specific page numbers.
    # The key MUST be the page number as a string (e.g., "1").
    # Helps guide character expression.
    emotional_states:
      "1": "curious and eager"
      "2": "intrigued and slightly cautious"
      # ... other emotions for other pages ...
  # --- Define other characters similarly --- #
  supporting_character:
    name: "Whisp"
    # ... (details for Whisp) ...
```

**Key Points for Characters:**

- **Consistency is Key:** Be detailed and use strong keywords (`Always`, `Must have`) in `appearance`, `outfit`, and `features`. These are added directly to the prompt with high priority.
- **Actions vs. Emotions:** A character is included in a page's image if they have _either_ an `action` defined for the corresponding story `phase` _or_ an `emotional_state` defined for that specific `page number`.
- **Exiting Scenes:** To make a character disappear, ensure they have _no_ action defined for the relevant phase _and_ no emotion defined for the specific page number onwards.

### 4. `story_progression` - Story Structure

Maps descriptive phase names to page ranges. These phase names link character actions and scene descriptions to the story flow.

```yaml
story_progression:
  # Map descriptive phase names to page ranges.
  # These phase names are used as keys in character actions and scene_progression.
  phase_mapping:
    intro:
      start_page: 1
      end_page: 1
    magical_encounter:
      start_page: 2
      end_page: 2
    # ... other phases mapped to page ranges ...
  # Fallback phases if specific mapping isn't found (optional).
  fallback_phases:
    introduction:
      end_page: 3
    # ... other fallback phases ...
  default_phase: "conclusion" # Phase used if no other match is found.
```

### 5. `settings` - Scene and Environment Details

Defines the overall setting and the visual details for each story phase.

```yaml
settings:
  location: "A secret, enchanted meadow..." # Overall location.
  time_period: "Present day" # Overall time period.

  # Define the visual details for each story phase.
  # Keys MUST match phase names in story_progression.phase_mapping.
  scene_progression:
    intro: # Phase name
      description: "A sunlit meadow..." # What the scene looks like.
      atmosphere: "Bright and inviting..." # The overall feeling.
      elements: # Specific objects or features present.
        - "Fields of colorful flowers..."
        - "A winding dirt path..."
      emotion: "curiosity and joy" # Primary emotion conveyed.
      lighting: "warm sunlight..." # Lighting conditions.
      mood: "peaceful and anticipatory" # Mood evoked.
      visual_focus: "Nia's excited face..." # Main subject or focal point.
      color_palette: "vivid yellows and greens..." # Dominant colors.
      transition_from_previous: "..." # Optional: Describe the transition.

    magical_bridge: # Another phase example
      description: "A shimmering, moonlit bridge..."
      # ... other settings ...
      elements:
        - "A crystal-clear stream..."
        - "glowing stepping stones..."
      # --- Reference Override (Use Strategically) --- #
      # Add this section ONLY when the reference image from the previous
      # page strongly conflicts with the current scene's requirements.
      reference_override:
        ignore_elements: # Tell AI to IGNORE these from the reference image
          - "forest path without stream"
          - "scene without water features"
        force_elements: # Tell AI it MUST include these in the new image
          - "prominent magical bridge"
          - "visible stream under bridge"

    # ... other phases defined similarly ...
```

**Using `reference_override` (Integrated from previous guide):**

- **Purpose:** To manage conflicts between the previous page's image (used as a reference) and the current page's required scene elements.
- **When to Use:** Primarily during major visual shifts between scenes (e.g., path -> bridge, outside -> inside) or when a specific scene consistently fails to render correctly due to reference conflicts.
- **How:** Use `ignore_elements` to list things from the reference that _shouldn't_ be in the new image. Use `force_elements` to list things that _must_ be in the new image, even if absent from the reference.
- **Strategy:** Be specific, focus on the conflicts, align with the main `elements` list, and use iteratively only when needed.

### 6. `story` - Narrative Content

Contains the actual text for each page.

```yaml
story:
  # Define the text for each page. List index = (page_number - 1).
  pages:
    - "Nia loved wandering..." # Page 1 text
    - "Following the path..." # Page 2 text
    # ... text for all pages ...
  # Optional: High-level summary of story beats for context.
  story_beats:
    intro: "Set the stage..."
    # ... other beats ...
```

### 7. `generation` - AI Generation Control

Parameters influencing the AI's generation process.

```yaml
generation:
  # Controls creativity vs. coherence (lower = more coherent).
  temperature:
    base: 0.2
    phase_increment: 0.3 # Optional increase in later phases.
    max: 0.5 # Maximum allowed temperature.
  # Internal steps AI follows (generally leave as default).
  steps: [...]
  # Rules for consistency and preventing duplicates (CRITICAL).
  anti_duplication_rules:
    rules: [...]
    consistency_rules: [...]
    flexibility_rules: [...]
    verification_rules: [...]
  # Overall art style parameters.
  art_style:
    tone: "Bright, child-friendly colors"
    quality: "High detail, clean lines"
    text_policy: "NO text elements in the image" # IMPORTANT!
    format: "SQUARE image ({width}x{height} pixels)"
```

**Key Points for Generation:**

- Leave `steps` and `anti_duplication_rules` as default unless experiencing specific issues like character duplication.
- Ensure `art_style.text_policy` is set to prevent the AI from drawing text directly onto the image.

### 8. `output_formats` - Output Selection

Choose which final book formats to generate.

```yaml
output_formats:
  pdf: true # PDF with ReportLab typesetting.
  epub: true # EPUB for e-readers.
  html: false # Simple HTML version.
  text: false # Plain text version of the story.
```

### 9. `metadata` - Book Metadata

Information embedded in the generated PDF and EPUB files.

```yaml
metadata:
  language: "en-US" # Language code (e.g., en-US, es-ES).
  author: "Amer DK" # Author name.
  publisher: "Self-Published" # Publisher name.
  isbn: "" # ISBN (optional).
  description: "..." # Book blurb/summary.
  keywords: "childrens book, story..." # Comma-separated keywords.
  publication_year: "" # Year (leave blank for current year).
  rights: "All rights reserved" # Copyright statement.
```

### 10. `print_settings` - KDP Formatting

Settings specifically for formatting PDF output for Amazon KDP paperback printing.

```yaml
print_settings:
  # Final page size after trimming.
  trim_width: 8.5
  trim_height: 8.5
  unit: "inch" # Unit for measurements ("inch" or "mm").
  # Bleed: Area outside trim line for images extending to the edge.
  has_bleed: true # True if images touch the edge.
  bleed_amount: 0.125 # Standard KDP bleed (0.125 inches or 3.2 mm).
  # Margins: Safe area inside trim line for text.
  margin_top: 0.5
  margin_bottom: 0.5
  margin_inside: 0.75 # Inner margin (gutter) - usually larger.
  margin_outside: 0.5 # Outer margin.
  # Paper Type: Affects spine width (used for cover generation - future).
  paper_type: "white" # "white", "cream", or "color".
  # Target DPI: For image dimension calculation reference.
  target_dpi: 300
```

### 11. `cover` - Cover Generation

Settings for generating the book cover (if enabled).

```yaml
cover:
  generate_cover: false # Set to true to attempt cover generation.
  cover_prompt_template: "... {characters} ... {theme} ... {art_style} ... NO text ..."
  cover_title: "" # Override book title (optional).
  cover_author: "By Amer" # Author name for cover.
  cover_text_position: "top" # Position for text overlay ("top", "middle", "bottom").
  reference_page_for_style: 1 # Use image from this page for style reference.
  cover_text_color: "#000000" # Color for text overlay (hex code).
```

## General Tips for Configuration

- **Start Simple:** Begin with the core `book`, `characters`, `story`, and `settings.scene_progression` sections.
- **Be Detailed:** Provide clear, unambiguous descriptions, especially for character appearances and scene elements.
- **Use Strong Keywords:** Employ terms like `Always` or `Must have` for critical consistency points.
- **Iterate:** Generate the book, review the output (text and images), and refine the `config.yaml` based on the results. Correcting character consistency or scene accuracy often requires tweaking the configuration and regenerating specific pages.
- **Test Strategically:** Use the `--regenerate` flag to test changes on specific pages without regenerating the entire book.
- **Consult This Guide:** Refer back here when unsure about a specific section or parameter.
